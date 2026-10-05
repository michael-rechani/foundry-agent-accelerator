// Add-ons an agent could connect to later. This is a preview catalogue: the page
// makes no calls and costs nothing. An add-on with `pilot` set also runs as a
// small sample in the Lab; the page itself still turns nothing on.
// The add-ons come from add-on-catalog.json, which `python addons/build_catalog.py --write`
// generates from the manifests in addons/. Uses erasable TypeScript only so `node --test`
// can import it directly.

import catalog from './add-on-catalog.json' with { type: 'json' }

export type AddOnIcon =
  'search' | 'memory' | 'documents' | 'notifications' | 'calculator' | 'web'

export type AddOn = {
  id: string
  name: string
  icon: AddOnIcon
  summary: string
  example: string
  // Set only when a small sample version already runs in the Lab.
  pilot?: string
  cost: string[]
  needs: string[]
  safety: string
  // Set when the add-on needs an explicit approval before it is even considered.
  approval?: string
  // Technical detail shown only with Under the hood on.
  service: string
  billing: string
  note?: string
}

// Rules every add-on would follow before anything is turned on.
export const addOnRules: string[] = [
  'Off by default. Nothing is turned on for you.',
  'Private network only. No public address.',
  'Managed identity instead of keys or passwords.',
  'Cost shown before it is turned on.',
  'Sample data first, so you can try it before using real data.',
  'No public resource is created without your explicit approval.',
]

export const addOns = catalog.add_ons as AddOn[]
