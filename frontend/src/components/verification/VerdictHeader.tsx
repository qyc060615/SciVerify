import { getVerdictConfig } from '@/constants/verdicts'
import { ConfidenceBar } from '@/components/sciverify/ConfidenceBar'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'
import { Panel } from '@/components/ui/Card'
import type { VerdictKey } from '@/constants/verdicts'

export interface VerdictHeaderProps {
  verdict: VerdictKey
  confidence: number
  claim: string
  paperTitle?: string
  paperDoi?: string
  agentAgreement?: boolean | null
  summary: string
}

function AgentAgreementBadge({ agreement }: { agreement: boolean | null | undefined }) {
  if (agreement === true) {
    return (
      <span className="inline-flex items-center rounded-full border border-success/30 bg-success/10 px-3 py-1 text-xs font-medium text-success">
        Agents agree
      </span>
    )
  }

  if (agreement === false) {
    return (
      <span className="inline-flex items-center rounded-full border border-warning/30 bg-warning/10 px-3 py-1 text-xs font-medium text-warning">
        Agents disagree
      </span>
    )
  }

  return (
    <span className="inline-flex items-center rounded-full border border-border bg-surface-elevated px-3 py-1 text-xs font-medium text-text-muted">
      Agreement information unavailable
    </span>
  )
}

export function VerdictHeader({
  verdict,
  confidence,
  claim,
  paperTitle,
  paperDoi,
  agentAgreement,
  summary,
}: VerdictHeaderProps) {
  const config = getVerdictConfig(verdict)
  const VerdictIcon = config.icon

  return (
    <Panel
      padding="lg"
      className={`space-y-6 border ring-1 ring-inset ${config.borderClass} ${config.ringClass}`}
    >
      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Verification result
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <VerdictIcon
            className={`h-6 w-6 shrink-0 ${config.textClass}`}
            aria-hidden
          />
          <h2 className={`text-2xl font-bold uppercase tracking-wide ${config.textClass}`}>
            {config.label}
          </h2>
          <VerdictBadge verdict={verdict} size="md" />
        </div>
        <p className="text-sm text-text-secondary">{config.description}</p>
      </div>

      <ConfidenceBar value={confidence} verdict={verdict} label="Confidence" />

      <div className="grid gap-4 border-t border-border pt-4 md:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Claim
          </p>
          <p className="mt-2 text-sm leading-relaxed text-text-primary">{claim}</p>
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Paper
          </p>
          <p className="mt-2 text-sm font-medium text-text-primary">
            {paperTitle ?? 'Title unavailable'}
          </p>
          {paperDoi ? (
            <p className="mt-1 font-mono text-xs text-text-muted">{paperDoi}</p>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Agent agreement
        </p>
        <AgentAgreementBadge agreement={agentAgreement} />
      </div>

      <div className="border-t border-border pt-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Summary
        </p>
        <p className="mt-2 text-sm leading-relaxed text-text-primary">{summary}</p>
      </div>
    </Panel>
  )
}
