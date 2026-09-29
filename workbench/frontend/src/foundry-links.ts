const portalPrefix =
  /^https:\/\/ai\.azure\.com\/nextgen\/r\/[A-Za-z0-9_-]{22},[A-Za-z0-9._()-]{1,90},,[A-Za-z0-9-]{2,64},[A-Za-z0-9_-]{1,64}$/

export function validPortal(value: unknown): value is string | null {
  return (
    value === null || (typeof value === 'string' && portalPrefix.test(value))
  )
}

export function foundryAgentUrl(
  portal: string | null | undefined,
  agent: string | null | undefined,
): string | null {
  if (!portal || !agent) return null
  return `${portal}/build/agents/${encodeURIComponent(agent)}/build`
}
