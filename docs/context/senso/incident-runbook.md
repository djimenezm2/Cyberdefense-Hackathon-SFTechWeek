# Rootlane Incident Runbook

Status: approved · Owner: Rootlane security · Applies to: every incident Rootlane opens

## Purpose

How the Rootlane agent and the on-call human take an incident from detection to a reviewed fix,
and how what was learned is kept.

## Steps

1. **Evidence first.** Start from the telemetry that opened the incident: the analyzer window,
   the events, routes, status codes and sources involved. Search this knowledge base for the
   policy that covers the behaviour before reading code. Record every query and finding as an
   incident step.
2. **Locate the cause in code.** Read the source behind the affected routes and name the
   policy rule it breaks. A hypothesis without evidence is labelled as one.
3. **Reproduce on an isolated replica.** Confirm the behaviour on a disposable replica of the
   service, never on the live deployment and never against real user data.
4. **Fix, regression test and Semgrep rule.** Write a failing regression test that captures the
   behaviour, make the minimal fix that turns it green, and add a Semgrep rule that catches the
   pattern elsewhere. Re-run the replica check to show the behaviour is gone.
5. **Human approval.** The fix, test, rule and evidence are presented to a human. Nothing ships
   without an explicit approval.
6. **Pull request on the fork.** After approval the agent opens a pull request on the
   application fork with the evidence, the test and the rule in the description.
7. **Record the lesson.** Add or update the relevant policy or runbook in Senso with what was
   learned, so the next investigation finds it first.

## Rules

- Read-only tools during investigation; writes happen only on the replica and the fork.
- No secrets or user data in incident steps, pull requests or knowledge base documents.
- If the evidence does not support an attack, close the incident as a false positive and say
  why.
