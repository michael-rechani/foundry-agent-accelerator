// Add-ons an agent could connect to later. This is a preview catalogue: the page
// makes no calls and costs nothing. An add-on with `pilot` set also runs as a
// small sample in the Lab; the page itself still turns nothing on.
// The add-ons come from add-on-catalog.json, which `python addons/build_catalog.py --write`
// generates from the manifests in addons/. Uses erasable TypeScript only so `node --test`
// can import it directly.

import catalog from './add-on-catalog.json' with { type: 'json' }

export type AddOnIcon =
  | 'search'
  | 'memory'
  | 'documents'
  | 'notifications'
  | 'calculator'
  | 'web'
  | 'cache'
  | 'storage'
  | 'queue'

// "abilities" lets an agent do something more. "support" is what an agent runs on.
export type AddOnGroup = 'abilities' | 'support'

export const addOnGroupLabels: Record<AddOnGroup, string> = {
  abilities: 'Lets an agent do more',
  support: 'Supports the agent',
}

export type AddOn = {
  id: string
  name: string
  icon: AddOnIcon
  group: AddOnGroup
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

// The request a person pastes into their coding agent to draft this add-on's package.
// It asks for a pull request only: nothing is deployed, and a person approves any apply.
export function codingAgentRequest(addOn: AddOn): string {
  const lines = [
    `Draft the "${addOn.name}" add-on package for the Foundry Agent Lab.`,
    '',
    `Read first: docs/addon-package-format.md, addons/${addOn.id}/addon.json, docs/optional-integrations.md and .github/copilot-instructions.md.`,
    '',
    `What it is: ${addOn.summary}`,
    'What it would need:',
    ...addOn.needs.map((line) => `- ${line}`),
    'What it would cost:',
    ...addOn.cost.map((line) => `- ${line}`),
  ]
  if (addOn.approval)
    lines.push(
      '',
      `This add-on is marked "${addOn.approval}". Draft the request for that approval only. Do not draft a module that sends data outside the tenant.`,
    )
  lines.push(
    '',
    'Do:',
    `- Add or update the package under addons/${addOn.id}/ as the package format describes: a Terraform module, bootstrap notes, an acceptance case and DEPLOY.md.`,
    '- Keep it private and keyless, with no variable that turns that off.',
    '- Run `python addons/check_addons.py` and `python -m unittest discover -s addons -p "test_*.py"` from the repository root.',
    '- Open a pull request that references #54 and #121.',
    '',
    'Do not:',
    '- Run terraform apply, deploy anything, make a billable call or touch shared data.',
    '- Create anything with public network access, a public IP, keys, shared-key access or an admin user. If the only path needs one, stop and ask.',
    '- Apply a plan. A person reviews and approves the saved plan and runs any apply.',
  )
  return lines.join('\n')
}
