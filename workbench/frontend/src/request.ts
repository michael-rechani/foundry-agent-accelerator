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
        data: await response.json(),
      })),
      cancelled,
    ])
    signal.throwIfAborted()
    return result
  } finally {
    signal.removeEventListener('abort', cancel)
  }
}
