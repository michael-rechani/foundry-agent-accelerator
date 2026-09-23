// Proxies and gateways can return HTML or empty error bodies; callers then fall
// back to their generic messages instead of surfacing a JSON parse error.
async function readJson(response: Response) {
  const text = await response.text()
  try {
    return JSON.parse(text)
  } catch {
    if (response.ok)
      throw new Error('The server returned an unreadable response.')
    return {}
  }
}

export async function requestJson(
  url: string,
  options: RequestInit,
  signal: AbortSignal,
) {
  signal.throwIfAborted()
  let cancel = () => {}
  const cancelled = new Promise<never>((_resolve, reject) => {
    cancel = () => reject(new DOMException('Request cancelled', 'AbortError'))
    signal.addEventListener('abort', cancel, { once: true })
  })
  try {
    const result = await Promise.race([
      fetch(url, { ...options, signal }).then(async (response) => ({
        response,
        data: await readJson(response),
      })),
      cancelled,
    ])
    signal.throwIfAborted()
    return result
  } finally {
    signal.removeEventListener('abort', cancel)
  }
}
