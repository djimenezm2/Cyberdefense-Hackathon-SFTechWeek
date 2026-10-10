export interface SourceFile { path: string; content: string; truncated?: boolean }
export interface Edit { path: string; old_text: string; new_text: string }

type Loose = Record<string, any> | null | undefined

const CONTEXT_LINES = 3
const HEAD_LINES = 40
const WINDOW_LINES = 80
export const MAX_SOURCE_CHARS = 60000

export function verifyErrorKind(verification: unknown): "rule" | "busy" | null {
  const error = (verification as Loose)?.error
  if (typeof error !== "string") return null
  if (/rule could not run|rule is invalid/i.test(error)) return "rule"
  if (/another replica is running/i.test(error)) return "busy"
  return null
}

export function hasTimeFor(now: number, deadline: number, longestStepMs: number, minStepMs: number): boolean {
  return now + Math.max(longestStepMs, minStepMs) <= deadline
}

export function stripFences(text: string): string {
  const fenced = text.trim().match(/^```[\w-]*\n([\s\S]*?)\n?```$/)
  return fenced ? fenced[1] : text
}

export function asSourceFile(value: unknown): SourceFile | null {
  const v = value as Loose
  return typeof v?.path === "string" && typeof v?.content === "string" ? { path: v.path, content: v.content, truncated: v.truncated === true } : null
}

export function missingPaths(edits: { path: string }[], files: SourceFile[]): string[] {
  const known = new Set(files.map((f) => f.path))
  return [...new Set(edits.map((e) => e.path))].filter((p) => !known.has(p))
}

export function flaggedLines(findings: unknown, path: string): number[] {
  const results = (findings as Loose)?.results
  if (!Array.isArray(results)) return []
  return results.filter((r) => r?.path === path || String(r?.path ?? "").endsWith(`/${path}`))
    .map((r) => Number(r?.start?.line)).filter((n) => Number.isInteger(n) && n > 0)
}

export function numberedSource(file: SourceFile, flagged: number[] = [], maxChars = MAX_SOURCE_CHARS): string {
  const lines = splitLines(file.content).lines
  const width = String(lines.length).length
  const fmt = (i: number) => `${String(i + 1).padStart(width + 1)}| ${lines[i]}`
  const whole = lines.map((_, i) => fmt(i)).join("\n")
  const header = `path: ${file.path}${file.truncated ? " (truncated by the reader)" : ""}`
  if (whole.length <= maxChars) return `${header}\n${whole}`
  const keep = new Set<number>()
  for (let i = 0; i < Math.min(HEAD_LINES, lines.length); i++) keep.add(i)
  for (const line of flagged) {
    for (let i = Math.max(0, line - 1 - WINDOW_LINES); i < Math.min(lines.length, line + WINDOW_LINES); i++) keep.add(i)
  }
  const out: string[] = []
  let size = 0
  for (let i = 0; i < lines.length; i++) {
    if (!keep.has(i)) {
      if (out[out.length - 1] !== "...") out.push("...")
      continue
    }
    const row = fmt(i)
    if (size + row.length > maxChars) { out.push("...[window limit]"); break }
    out.push(row)
    size += row.length + 1
  }
  return `${header} (only the first lines and the windows around Semgrep findings are shown)\n${out.join("\n")}`
}

function splitLines(content: string): { lines: string[]; finalNewline: boolean } {
  if (content === "") return { lines: [], finalNewline: true }
  const finalNewline = content.endsWith("\n")
  return { lines: (finalNewline ? content.slice(0, -1) : content).split("\n"), finalNewline }
}

function fileDiff(path: string, before: string, after: string): string {
  const a = splitLines(before)
  const b = splitLines(after)
  let prefix = 0
  while (prefix < a.lines.length && prefix < b.lines.length && a.lines[prefix] === b.lines[prefix]) prefix++
  let suffix = 0
  while (suffix < a.lines.length - prefix && suffix < b.lines.length - prefix
    && a.lines[a.lines.length - 1 - suffix] === b.lines[b.lines.length - 1 - suffix]) suffix++
  if (a.finalNewline !== b.finalNewline) suffix = 0
  const start = Math.max(0, prefix - CONTEXT_LINES)
  const aEnd = a.lines.length - suffix
  const bEnd = b.lines.length - suffix
  const tailEnd = Math.min(a.lines.length, aEnd + CONTEXT_LINES)
  const noNewline = "\\ No newline at end of file"
  const rows: string[] = []
  for (let i = start; i < prefix; i++) rows.push(` ${a.lines[i]}`)
  for (let i = prefix; i < aEnd; i++) {
    rows.push(`-${a.lines[i]}`)
    if (i === a.lines.length - 1 && !a.finalNewline) rows.push(noNewline)
  }
  for (let i = prefix; i < bEnd; i++) {
    rows.push(`+${b.lines[i]}`)
    if (i === b.lines.length - 1 && !b.finalNewline) rows.push(noNewline)
  }
  for (let i = aEnd; i < tailEnd; i++) {
    rows.push(` ${a.lines[i]}`)
    if (i === a.lines.length - 1 && !a.finalNewline) rows.push(noNewline)
  }
  const oldCount = tailEnd - start
  const newCount = oldCount - (aEnd - prefix) + (bEnd - prefix)
  const range = (from: number, count: number) => `${count === 0 ? from : from + 1},${count}`
  return [`diff --git a/${path} b/${path}`, `--- a/${path}`, `+++ b/${path}`,
    `@@ -${range(start, oldCount)} +${range(start, newCount)} @@`, ...rows, ""].join("\n")
}

export function buildDiff(files: SourceFile[], edits: Edit[]): { diff: string } | { error: string } {
  const contents = new Map<string, string>()
  for (const f of files) {
    contents.set(f.path, f.truncated ? f.content.slice(0, f.content.lastIndexOf("\n") + 1) : f.content)
  }
  const after = new Map<string, string>()
  for (const edit of edits) {
    const current = after.get(edit.path) ?? contents.get(edit.path)
    if (current === undefined) return { error: `${edit.path} was not read; only edit files shown in source_files` }
    if (edit.old_text === "") return { error: `empty old_text for ${edit.path}` }
    const at = current.indexOf(edit.old_text)
    if (at < 0) return { error: `old_text not found verbatim in ${edit.path}: ${edit.old_text.slice(0, 200)}` }
    if (current.indexOf(edit.old_text, at + 1) >= 0) return { error: `old_text occurs more than once in ${edit.path}; include more surrounding lines` }
    after.set(edit.path, current.slice(0, at) + edit.new_text + current.slice(at + edit.old_text.length))
  }
  const parts: string[] = []
  for (const [path, text] of after) {
    if (text !== contents.get(path)) parts.push(fileDiff(path, contents.get(path)!, text))
  }
  return parts.length ? { diff: parts.join("") } : { error: "the edits change nothing" }
}
