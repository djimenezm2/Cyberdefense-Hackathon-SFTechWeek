export const TOOL_ARG_SHAPE: "flat" | "body" = "flat"
export const SESSION_HEADER_ARG: string | null = null
export const SESSION_BODY_FIELD = "guild_session_id"
export const REPRODUCE_REQUEST_FIELD = "reproduction"

// Same full-match rule the toolbox applies to ids it records.
const TOOLBOX_ID = /^[A-Za-z0-9_.:-]{1,64}$/

export function toolArgs(body: Record<string, unknown>, sessionId: string,
  shape: "flat" | "body" = TOOL_ARG_SHAPE, headerArg: string | null = SESSION_HEADER_ARG): Record<string, unknown> {
  const fields: Record<string, unknown> = TOOLBOX_ID.test(sessionId) ? { ...body, [SESSION_BODY_FIELD]: sessionId } : { ...body }
  const args: Record<string, unknown> = shape === "body" ? { body: fields } : fields
  if (headerArg) args[headerArg] = sessionId
  return args
}
