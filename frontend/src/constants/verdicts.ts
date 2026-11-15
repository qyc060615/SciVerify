import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  CircleHelp,
  XCircle,
  type LucideIcon,
} from 'lucide-react'

export const VERDICT_KEYS = [
  'SUPPORTS',
  'OVERSTATED',
  'CONTRADICTS',
  'INSUFFICIENT',
  'FABRICATED',
] as const

export type VerdictKey = (typeof VERDICT_KEYS)[number]

export interface VerdictConfig {
  key: VerdictKey
  label: string
  description: string
  icon: LucideIcon
  textClass: string
  bgClass: string
  borderClass: string
  ringClass: string
  barClass: string
}

export const VERDICTS: Record<VerdictKey, VerdictConfig> = {
  SUPPORTS: {
    key: 'SUPPORTS',
    label: 'Supports',
    description: 'Evidence strongly supports the cited claim.',
    icon: CheckCircle2,
    textClass: 'text-verdict-supports',
    bgClass: 'bg-verdict-supports/10',
    borderClass: 'border-verdict-supports/30',
    ringClass: 'ring-verdict-supports/20',
    barClass: 'bg-verdict-supports',
  },
  OVERSTATED: {
    key: 'OVERSTATED',
    label: 'Overstated',
    description: 'The claim exaggerates or misrepresents the evidence.',
    icon: AlertTriangle,
    textClass: 'text-verdict-overstated',
    bgClass: 'bg-verdict-overstated/10',
    borderClass: 'border-verdict-overstated/30',
    ringClass: 'ring-verdict-overstated/20',
    barClass: 'bg-verdict-overstated',
  },
  CONTRADICTS: {
    key: 'CONTRADICTS',
    label: 'Contradicts',
    description: 'Available evidence directly contradicts the claim.',
    icon: XCircle,
    textClass: 'text-verdict-contradicts',
    bgClass: 'bg-verdict-contradicts/10',
    borderClass: 'border-verdict-contradicts/30',
    ringClass: 'ring-verdict-contradicts/20',
    barClass: 'bg-verdict-contradicts',
  },
  INSUFFICIENT: {
    key: 'INSUFFICIENT',
    label: 'Insufficient',
    description: 'Not enough reliable evidence to reach a conclusion.',
    icon: CircleHelp,
    textClass: 'text-verdict-insufficient',
    bgClass: 'bg-verdict-insufficient/10',
    borderClass: 'border-verdict-insufficient/30',
    ringClass: 'ring-verdict-insufficient/20',
    barClass: 'bg-verdict-insufficient',
  },
  FABRICATED: {
    key: 'FABRICATED',
    label: 'Fabricated',
    description: 'The citation or claim appears to be fabricated.',
    icon: Ban,
    textClass: 'text-verdict-fabricated',
    bgClass: 'bg-verdict-fabricated/10',
    borderClass: 'border-verdict-fabricated/30',
    ringClass: 'ring-verdict-fabricated/20',
    barClass: 'bg-verdict-fabricated',
  },
}

export function getVerdictConfig(key: string | VerdictKey): VerdictConfig {
  const normalized = (
    typeof key === 'string' ? key.trim().toUpperCase() : key
  ) as VerdictKey
  return VERDICTS[normalized] ?? VERDICTS.INSUFFICIENT
}
