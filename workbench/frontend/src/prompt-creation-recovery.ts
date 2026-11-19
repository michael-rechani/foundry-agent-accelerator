const storageKey = 'foundry-lab.prompt-creation.v1'
export const promptOnlyId = 'prompt-only'

export type PromptReceipt = {
  id: string
  fingerprint: string
}

export const recoveryUnavailable =
  'This browser cannot safely read or save its creation receipt. No new request was sent. Restore browser storage or check Made in this Lab before creating again.'

export function withPromptReceiptLock<T>(callback: () => T): Promise<T> {
  if (!navigator.locks) return Promise.reject(new Error(recoveryUnavailable))
  return navigator.locks.request(storageKey, callback)
}

export function readPromptReceipt(): PromptReceipt | null {
  const raw = localStorage.getItem(storageKey)
  if (raw === null) return null
  const value: unknown = JSON.parse(raw)
  if (
    !value ||
    typeof value !== 'object' ||
    !('id' in value) ||
    typeof value.id !== 'string' ||
    !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value.id) ||
    !('fingerprint' in value) ||
    typeof value.fingerprint !== 'string' ||
    !/^[0-9a-f]{64}$/.test(value.fingerprint)
  )
    throw new Error(recoveryUnavailable)
  return { id: value.id, fingerprint: value.fingerprint }
}

export function samePromptReceipt(
  left: PromptReceipt | null,
  right: PromptReceipt | null,
) {
  return left?.id === right?.id && left?.fingerprint === right?.fingerprint
}

export function savePromptReceipt(receipt: PromptReceipt) {
  localStorage.setItem(storageKey, JSON.stringify(receipt))
  if (!samePromptReceipt(readPromptReceipt(), receipt))
    throw new Error(recoveryUnavailable)
}

export function clearPromptReceipt(receipt: PromptReceipt) {
  if (!samePromptReceipt(readPromptReceipt(), receipt))
    throw new Error(recoveryUnavailable)
  localStorage.removeItem(storageKey)
  if (readPromptReceipt() !== null) throw new Error(recoveryUnavailable)
}

export async function promptFingerprint(
  id: string,
  name: string,
  instructions: string,
) {
  const setup = new TextEncoder().encode(
    JSON.stringify([id, name, instructions]),
  )
  const digest = await crypto.subtle.digest('SHA-256', setup)
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}
