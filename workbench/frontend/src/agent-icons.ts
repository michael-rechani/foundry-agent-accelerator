import {
  Banknote,
  Bot,
  CalendarClock,
  FilePenLine,
  FileText,
  HardHat,
  Headset,
  ListChecks,
  MessagesSquare,
  NotebookPen,
  PackageCheck,
  Receipt,
  Route,
  Scale,
  ScanText,
  ShieldCheck,
  Siren,
  Stethoscope,
  Truck,
  type LucideIcon,
} from 'lucide-react'

// One icon per library agent, shared by the library cards and the Create page.
// A test checks that every agent in the catalog has its own.
export const agentIcons: Record<string, LucideIcon> = {
  'supplier-invoice-reviewer': PackageCheck,
  'expense-report-checker': Receipt,
  'order-delay-helper': Truck,
  'customer-support-brief': Headset,
  'customer-feedback-themes': MessagesSquare,
  'document-analyst': FileText,
  'document-intake': ScanText,
  'criteria-checker': ListChecks,
  'contract-playbook-checker': Scale,
  'rfp-answer-drafter': FilePenLine,
  'incident-timeline-writer': Siren,
  'cash-application-reviewer': Banknote,
  'maintenance-work-order-planner': HardHat,
  'workflow-coordinator': Route,
  'casework-assistant': NotebookPen,
  'medical-bill-reviewer': Stethoscope,
  'insurance-preapproval-helper': ShieldCheck,
  'benefits-renewal-helper': CalendarClock,
}

export const fallbackAgentIcon: LucideIcon = Bot
