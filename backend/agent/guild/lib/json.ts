function asObject(text: string): unknown | null {
  try {
    const value = JSON.parse(text)
    return value && typeof value === "object" && !Array.isArray(value) ? value : null
  } catch { return null }
}

export function extractJson(text: string): unknown | null {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/)
  const start = text.indexOf("{"), end = text.lastIndexOf("}")
  return asObject(text.trim()) ?? (fenced ? asObject(fenced[1]) : null) ?? (start >= 0 && end > start ? asObject(text.slice(start, end + 1)) : null)
}
