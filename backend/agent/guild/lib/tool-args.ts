export const TOOL_ARG_SHAPE: "flat" | "body" = "flat"
export const SESSION_HEADER_ARG: string | null = null

export function toolArgs(body: Record<string, unknown>, sessionId: string,
  shape: "flat" | "body" = TOOL_ARG_SHAPE, headerArg: string | null = SESSION_HEADER_ARG): Record<string, unknown> {
  const args: Record<string, unknown> = shape === "body" ? { body } : { ...body }
  if (headerArg) args[headerArg] = sessionId
  return args
}
