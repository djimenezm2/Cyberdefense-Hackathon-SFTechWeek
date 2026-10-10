"use agent";

import { type Task, agent, consoleTools, guildTools, pick, progressLogNotifyEvent, userInterfaceTools } from "@guildai/agents-sdk";
import { SensoMcpTools } from "@guildai-services/djimenezm2~senso-mcp";
import { RootlaneToolboxTools } from "@guildai-services/djimenezm2~rootlane-toolbox";
import { z } from "zod";
import { extractJson } from "./lib/json";
import {
  type AgentOutput, finalOutput, incidentFromRows, incidentQuery, isMissingEndpoint, isReproduced,
  proposalHash, resolveIncidentId, verifyPassed,
} from "./lib/outcome";
import {
  type SourceFile, asSourceFile, buildDiff, flaggedLines, hasTimeFor, missingPaths, numberedSource, stripFences, verifyErrorKind,
} from "./lib/patch";
import { SYSTEM, hypothesisPrompt, patchPrompt, queryPlanPrompt, reportPrompt, rulePrompt, sourcePlanPrompt } from "./lib/prompts";
import { REPRODUCE_REQUEST_FIELD, toolArgs } from "./lib/tool-args";

const LLM = [{ provider: "anthropic" as const, model: "claude-opus-5" }];
// Guild's turn ceiling (3,600 s) less a margin so no call is cut off.
const SESSION_BUDGET_MS = 3_600_000;
const SAFETY_MARGIN_MS = 30_000;
const MIN_STEP_MS = 120_000;

const inputSchema = z.object({ incident_id: z.string().optional(), text: z.string().optional() });
type Input = z.infer<typeof inputSchema>;
const outputSchema = z.object({
  incident_id: z.string(),
  outcome: z.enum(["not_reproduced", "fix_failed", "pending_approval", "rejected", "applied"]),
  summary: z.string(),
  proposal_hash: z.string().nullable(),
  pr_url: z.string().nullable(),
});

const QueryPlan = z.object({ queries: z.array(z.string()).max(3) });
const SourcePlan = z.object({ paths: z.array(z.string()).max(4) });
const Hypothesis = z.object({
  hypothesis: z.string(),
  evidence: z.array(z.object({ kind: z.string(), ref: z.string(), text: z.string() })),
  reproduction: z.object({
    method: z.string(), path: z.string(), headers: z.record(z.string(), z.string()),
    body: z.string().nullable(), expected_blocked_status: z.number().int(),
  }),
});
const Patch = z.object({
  edits: z.array(z.object({ path: z.string().min(1), old_text: z.string().min(1), new_text: z.string() })).min(1),
  rule_yaml: z.string().min(1),
});
const Rule = z.object({ rule_yaml: z.string().min(1) });

const tools = {
  ...RootlaneToolboxTools,
  ...pick(SensoMcpTools, ["senso_mcp_senso_search", "senso_mcp_senso_create_doc"]),
  ...guildTools,
  ...userInterfaceTools,
  ...consoleTools,
};
type Tools = typeof tools;

async function note(task: Task<Tools>, text: string): Promise<void> {
  await task.tools.ui_notify(progressLogNotifyEvent(text));
}

async function askJson<T>(task: Task<Tools>, schema: z.ZodType<T>, prompt: string): Promise<T | null> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const reply = await task.llm.generateText({ system: SYSTEM, prompt, llmPreferences: LLM });
    const parsed = schema.safeParse(extractJson(reply.text));
    if (parsed.success) return parsed.data;
  }
  return null;
}

async function readIncident(task: Task<Tools>, id: string): Promise<Record<string, unknown> | null> {
  const result = await task.tools.rootlane_toolbox_query_events(toolArgs({ sql: incidentQuery(id), incident_id: id }, task.sessionId) as never);
  return incidentFromRows(result);
}

async function run(input: Input, task: Task<Tools>): Promise<AgentOutput> {
  const deadline = Date.now() + SESSION_BUDGET_MS - SAFETY_MARGIN_MS;
  const id = resolveIncidentId(input);
  if (!id) throw new Error("input carries no valid incident_id");
  const sid = task.sessionId;
  const incident = await readIncident(task, id);
  if (!incident) throw new Error(`incident ${id} not found`);
  await note(task, `Investigating incident ${id}`);

  const plan = await askJson(task, QueryPlan, queryPlanPrompt(incident));
  const rows: unknown[] = [];
  for (const sql of plan?.queries ?? []) {
    try {
      rows.push({ sql, result: await task.tools.rootlane_toolbox_query_events(toolArgs({ sql, incident_id: id }, sid) as never) });
    } catch (error) {
      rows.push({ sql, error: String(error) });
    }
  }
  await note(task, `Ran ${rows.length} timeline queries`);

  let context: unknown = "Senso unavailable";
  try {
    const topic = String(incident.title ?? incident.summary ?? id);
    context = await task.tools.senso_mcp_senso_search({ query: `Security policy and past incidents relevant to: ${topic}`, mode: "answer", max_results: 5 });
    await note(task, "Senso: policy and past-incident context retrieved");
  } catch (error) {
    await note(task, `Senso search failed, continuing without policy context: ${String(error)}`);
  }

  const sourcePlan = await askJson(task, SourcePlan, sourcePlanPrompt(incident, rows, context));
  const paths = sourcePlan?.paths ?? [];
  const sources: unknown[] = [];
  for (const path of paths) {
    try {
      sources.push(await task.tools.rootlane_toolbox_read_source(toolArgs({ path, incident_id: id }, sid) as never));
    } catch (error) {
      sources.push({ path, error: String(error) });
    }
  }
  let findings: unknown = null;
  try {
    findings = await task.tools.rootlane_toolbox_semgrep_scan(toolArgs(paths.length ? { paths, incident_id: id } : { incident_id: id }, sid) as never);
  } catch (error) {
    findings = { error: String(error) };
  }
  await note(task, `Read ${sources.length} source files; Semgrep scan done`);

  const hyp = await askJson(task, Hypothesis, hypothesisPrompt(incident, rows, context, sources, findings));
  if (!hyp) return finalOutput(id, "not_reproduced", "No testable hypothesis could be formed from the evidence.");
  await note(task, `Hypothesis: ${hyp.hypothesis}`);

  let replay: unknown = null;
  try {
    replay = await task.tools.rootlane_toolbox_reproduce(toolArgs({ incident_id: id, [REPRODUCE_REQUEST_FIELD]: hyp.reproduction }, sid) as never);
  } catch (error) {
    replay = { error: String(error) };
  }
  if (!isReproduced(replay, hyp.reproduction)) {
    return finalOutput(id, "not_reproduced", `The exploit did not reproduce on a fresh replica: ${JSON.stringify(replay)}`);
  }
  await note(task, "Exploit reproduced on a fresh replica");

  const files: SourceFile[] = sources.map(asSourceFile).filter((f): f is SourceFile => f !== null);
  let failure: unknown = null;
  let candidate: { diff: string; rule_yaml: string } | null = null;
  let verified: { diff: string; rule_yaml: string; verification: unknown } | null = null;
  let attempts = 0;
  let longestStepMs = 0;
  while (!verified && hasTimeFor(Date.now(), deadline, longestStepMs, MIN_STEP_MS)) {
    const stepStart = Date.now();
    if (!candidate) {
      attempts++;
      const shown = files.map((f) => numberedSource(f, flaggedLines(findings, f.path)));
      const patch = await askJson(task, Patch, patchPrompt(hyp, shown, failure));
      if (!patch) {
        failure = "no valid edits/rule_yaml reply";
        longestStepMs = Math.max(longestStepMs, Date.now() - stepStart);
        continue;
      }
      for (const path of missingPaths(patch.edits, files)) {
        try {
          const file = asSourceFile(await task.tools.rootlane_toolbox_read_source(toolArgs({ path, incident_id: id }, sid) as never));
          if (file) files.push(file);
        } catch (error) {
          await note(task, `Could not read ${path}: ${String(error)}`);
        }
      }
      const built = buildDiff(files, patch.edits);
      if ("error" in built) {
        failure = { edits: patch.edits, edit_error: built.error };
        await note(task, `Patch attempt ${attempts}: edits rejected (${built.error})`);
        longestStepMs = Math.max(longestStepMs, Date.now() - stepStart);
        continue;
      }
      candidate = { diff: built.diff, rule_yaml: stripFences(patch.rule_yaml) };
    }
    let verification: unknown = null;
    try {
      verification = await task.tools.rootlane_toolbox_verify_patch(toolArgs({ incident_id: id, diff: candidate.diff, rule_yaml: candidate.rule_yaml }, sid) as never);
    } catch (error) {
      verification = { error: String(error) };
    }
    const passed = verifyPassed(verification);
    const errorKind = passed ? null : verifyErrorKind(verification);
    await note(task, `Verify attempt ${attempts}: ${passed ? "passed" : errorKind === "rule" ? "invalid Semgrep rule, fixing the rule only" : errorKind === "busy" ? "sandbox busy, retrying" : "failed"}`);
    if (passed) {
      verified = { ...candidate, verification };
    } else if (errorKind === "rule") {
      const fixed: z.infer<typeof Rule> | null = await askJson(task, Rule, rulePrompt(candidate.rule_yaml, verification, candidate.diff));
      if (fixed) candidate = { diff: candidate.diff, rule_yaml: stripFences(fixed.rule_yaml) };
      else {
        failure = { diff: candidate.diff, rule_yaml: candidate.rule_yaml, verify_patch: verification };
        candidate = null;
      }
    } else if (errorKind !== "busy") {
      failure = { diff: candidate.diff, rule_yaml: candidate.rule_yaml, verify_patch: verification };
      candidate = null;
    }
    longestStepMs = Math.max(longestStepMs, Date.now() - stepStart);
  }
  if (!verified) {
    return finalOutput(id, "fix_failed", `No patch passed verification in ${attempts} attempts before the session time budget ran out. Last failure: ${JSON.stringify(failure)}`);
  }

  const report = (await task.llm.generateText({ system: SYSTEM, prompt: reportPrompt(hyp, verified.verification), llmPreferences: LLM })).text;
  let proposal: unknown = null;
  let proposeError: unknown = null;
  try {
    proposal = await task.tools.rootlane_toolbox_propose(toolArgs({ incident_id: id, report, diff: verified.diff, rule_yaml: verified.rule_yaml }, sid) as never);
  } catch (error) {
    proposeError = error;
  }
  const hash = proposalHash(proposal);
  if (!hash) {
    const reason = proposeError && isMissingEndpoint(proposeError)
      ? "propose endpoint unavailable"
      : `propose did not return a proposal: ${proposeError ? String(proposeError) : JSON.stringify(proposal)}`;
    await note(task, `Patch verified, but no proposal was stored (${reason})`);
    return finalOutput(id, "fix_failed", `A patch passed verification, but no proposal could be stored for approval (${reason}). Nothing was applied.`);
  }
  await note(task, `Proposal ${hash} waiting for approval`);
  return finalOutput(id, "pending_approval", "Verified fix proposed; waiting for a human approval in the dashboard.", hash);
}

export default agent({
  description: "Investigates a Rootlane incident, reproduces it, verifies a fix and proposes it for human approval.",
  inputSchema,
  outputSchema,
  tools,
  run,
});
