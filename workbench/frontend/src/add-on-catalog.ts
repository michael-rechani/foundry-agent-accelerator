// Add-ons an agent could connect to later. This is a preview catalogue: nothing
// here is built or turned on, so it makes no calls and costs nothing.
// Uses erasable TypeScript only so `node --test` can import it directly.

export type AddOnIcon =
  'search' | 'memory' | 'documents' | 'notifications' | 'calculator' | 'web'

export type AddOn = {
  id: string
  name: string
  icon: AddOnIcon
  summary: string
  example: string
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

export const addOns: AddOn[] = [
  {
    id: 'knowledge-search',
    name: 'Knowledge search',
    icon: 'search',
    summary:
      'Lets an agent answer from your own documents, not only from what it already knows.',
    example:
      'A grant reviewer asks what the policy says about travel. The agent finds the right pages and quotes them.',
    cost: [
      'The search service is billed by the hour while it runs. The price depends on its size.',
      'Ranking results by meaning and preparing documents for search add small extra charges.',
    ],
    needs: [
      'A search service on the private network.',
      'Your documents, kept in storage you control.',
    ],
    safety:
      'Only the documents you add can be searched. Access would use a managed identity, not keys.',
    service: 'Azure AI Search',
    billing:
      'Search units per hour by tier, plus semantic ranker and embedding calls.',
    note: 'The dev platform already has a Basic search service (#76). Try that first, and decide the tier before anything larger.',
  },
  {
    id: 'conversation-memory',
    name: 'Conversation memory',
    icon: 'memory',
    summary:
      'Lets an agent remember earlier conversations, so people do not have to repeat themselves.',
    example:
      'A returning person carries on with an earlier case without restating the details.',
    cost: [
      'Billed for how much the database is used, either as reserved capacity or per request.',
      'Stored conversations also add a storage charge.',
    ],
    needs: [
      'A decision on how long conversations are kept.',
      'A way to delete the history of anyone who asks.',
    ],
    safety:
      'It would store what people type, so it needs retention and deletion rules before it is used.',
    service: 'Azure Cosmos DB',
    billing: 'Provisioned or serverless request units, plus storage.',
  },
  {
    id: 'document-extraction',
    name: 'Document extraction',
    icon: 'documents',
    summary:
      'Lets an agent read scanned forms, receipts and PDFs, so it can work with the text and fields in them.',
    example:
      'An expense claim arrives as a photo of a receipt. The agent reads the date and the total from it.',
    cost: ['Billed for each page that is read.'],
    needs: [
      'Example documents to test with.',
      'A person checks anything the reader is unsure about.',
    ],
    safety:
      'It would read documents only inside your private network, and it would not keep them unless you decide it should.',
    service: 'Azure AI Document Intelligence',
    billing: 'Per page analyzed, by model.',
  },
  {
    id: 'notifications',
    name: 'Notifications',
    icon: 'notifications',
    summary: 'Lets an agent send a message once a person has approved it.',
    example:
      'The agent drafts an email to a vendor. A person reads it, then chooses Send.',
    cost: [
      'Billed for each message sent, or for each step when the message goes through a workflow.',
    ],
    needs: [
      'A sender address your organization owns.',
      'A named person who approves every message.',
    ],
    safety:
      'The agent only drafts. A person must approve every send, and nothing goes out on its own.',
    service: 'Azure Communication Services email, or Logic Apps',
    billing: 'Per message, or per action for Logic Apps.',
  },
  {
    id: 'code-interpreter',
    name: 'Code interpreter',
    icon: 'calculator',
    summary:
      'Lets an agent run small calculations on the data you give it, instead of doing the arithmetic in its head.',
    example:
      'The agent totals the lines on an expense claim and shows its working.',
    cost: ['Billed for each session the agent opens.'],
    needs: ['Nothing to set up in the Lab. It is a built-in Foundry tool.'],
    safety:
      'It runs in a sandbox managed by Foundry and only sees the data it is given.',
    service: 'Foundry Agent Service code interpreter tool',
    billing: 'Per session.',
    note: 'Prefer the tools Foundry already provides over rebuilding them in the Lab.',
  },
  {
    id: 'web-search',
    name: 'Web search',
    icon: 'web',
    summary: 'Lets an agent look things up on the public internet.',
    example: 'The agent checks a current public regulation before it answers.',
    cost: [
      'Charged for each search by the search provider. The price has not been assessed yet.',
    ],
    needs: ['Explicit approval of what may be sent outside your organization.'],
    safety:
      'The questions the agent asks would leave your organization and go to a public search service.',
    approval: 'Needs data-handling approval first',
    service: 'Web grounding (public search service)',
    billing: 'Per query. Not assessed.',
  },
]
