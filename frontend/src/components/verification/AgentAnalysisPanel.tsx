import { useId, useState, type ReactNode } from 'react'
import { ChevronDown, Scale, Shield, Swords } from 'lucide-react'
import { cn } from '@/lib/cn'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'
import { Badge } from '@/components/ui/Badge'
import { Panel } from '@/components/ui/Card'
import type { VerdictKey } from '@/constants/verdicts'
import type {
  AdjudicatorDetail,
  AgentAnalysis,
  AgentDetail,
} from '@/types/verification'

export interface AgentAnalysisPanelProps {
  prosecutor: AgentAnalysis
  defender: AgentAnalysis
  adjudicator: AgentAnalysis
  prosecutorDetail?: AgentDetail
  defenderDetail?: AgentDetail
  adjudicatorDetail?: AdjudicatorDetail
}

function EvidenceIdList({ ids }: { ids: string[] }) {
  if (ids.length === 0) {
    return (
      <p className="text-sm text-text-muted">None cited.</p>
    )
  }

  return (
    <ul className="flex flex-wrap gap-2" role="list">
      {ids.map((id) => (
        <li key={id}>
          <Badge variant="muted" size="sm">
            {id}
          </Badge>
        </li>
      ))}
    </ul>
  )
}

function ExpandableAgentSection({
  title,
  subtitle,
  icon: Icon,
  defaultOpen = false,
  highlighted = false,
  children,
}: {
  title: string
  subtitle: string
  icon: typeof Swords
  defaultOpen?: boolean
  highlighted?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  const panelId = useId()

  return (
    <Panel
      padding="md"
      className={cn(
        'space-y-0',
        highlighted && 'border-primary/20 bg-primary/5 ring-1 ring-primary/10',
      )}
    >
      <button
        type="button"
        className="flex w-full items-start justify-between gap-3 text-left"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-elevated">
            <Icon className="h-4 w-4 text-text-muted" aria-hidden />
          </span>
          <div>
            <p className="text-sm font-semibold text-text-primary">{title}</p>
            <p className="mt-1 text-xs text-text-muted">{subtitle}</p>
          </div>
        </div>
        <ChevronDown
          className={cn(
            'mt-1 h-4 w-4 shrink-0 text-text-muted transition-transform',
            open && 'rotate-180',
          )}
          aria-hidden
        />
      </button>

      <div
        id={panelId}
        hidden={!open}
        className="space-y-4 border-t border-border pt-4"
      >
        {children}
      </div>
    </Panel>
  )
}

function AgentDetailBody({ detail }: { detail: AgentDetail }) {
  return (
    <>
      {detail.stance ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Stance
          </p>
          <p className="mt-1 text-sm text-text-primary">{detail.stance}</p>
        </div>
      ) : null}

      {detail.confidence !== undefined ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Confidence
          </p>
          <p className="mt-1 text-sm font-medium tabular-nums text-text-primary">
            {detail.confidence}%
          </p>
        </div>
      ) : null}

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Analysis
        </p>
        <p className="mt-2 text-sm leading-relaxed text-text-secondary">
          {detail.analysis}
        </p>
      </div>

      {detail.keyPoints.length > 0 ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Key points
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-text-secondary">
            {detail.keyPoints.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Supporting evidence
        </p>
        <div className="mt-2">
          <EvidenceIdList ids={detail.supportingEvidence} />
        </div>
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Contradicting evidence
        </p>
        <div className="mt-2">
          <EvidenceIdList ids={detail.contradictingEvidence} />
        </div>
      </div>
    </>
  )
}

function FallbackAgentBody({ agent }: { agent: AgentAnalysis }) {
  return (
    <>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Analysis
        </p>
        <p className="mt-2 text-sm leading-relaxed text-text-secondary">
          {agent.summary}
        </p>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Finding
        </p>
        <p className="mt-2 text-sm leading-relaxed text-text-secondary">
          {agent.finding}
        </p>
      </div>
    </>
  )
}

export function AgentAnalysisPanel({
  prosecutor,
  defender,
  adjudicator,
  prosecutorDetail,
  defenderDetail,
  adjudicatorDetail,
}: AgentAnalysisPanelProps) {
  return (
    <div className="space-y-4">
      <ExpandableAgentSection
        title="Prosecutor"
        subtitle="Challenge the claim"
        icon={Swords}
      >
        {prosecutorDetail ? (
          <AgentDetailBody detail={prosecutorDetail} />
        ) : (
          <FallbackAgentBody agent={prosecutor} />
        )}
      </ExpandableAgentSection>

      <ExpandableAgentSection
        title="Defender"
        subtitle="Build the supporting case"
        icon={Shield}
      >
        {defenderDetail ? (
          <AgentDetailBody detail={defenderDetail} />
        ) : (
          <FallbackAgentBody agent={defender} />
        )}
      </ExpandableAgentSection>

      <ExpandableAgentSection
        title="Adjudicator"
        subtitle="Final reasoning stage"
        icon={Scale}
        defaultOpen
        highlighted
      >
        {adjudicatorDetail ? (
          <>
            {adjudicatorDetail.verdict ? (
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                  Verdict
                </p>
                <VerdictBadge
                  verdict={adjudicatorDetail.verdict as VerdictKey}
                  size="sm"
                />
              </div>
            ) : null}

            {adjudicatorDetail.confidence !== undefined ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                  Confidence
                </p>
                <p className="mt-1 text-sm font-medium tabular-nums text-text-primary">
                  {adjudicatorDetail.confidence}%
                </p>
              </div>
            ) : null}

            {adjudicatorDetail.reasoning ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                  Reasoning
                </p>
                <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                  {adjudicatorDetail.reasoning}
                </p>
              </div>
            ) : null}

            <AgentDetailBody detail={adjudicatorDetail} />

            {adjudicatorDetail.suggestedCorrection ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                  Suggested correction
                </p>
                <p className="mt-2 text-sm leading-relaxed text-text-primary">
                  &ldquo;{adjudicatorDetail.suggestedCorrection}&rdquo;
                </p>
              </div>
            ) : null}
          </>
        ) : (
          <FallbackAgentBody agent={adjudicator} />
        )}
      </ExpandableAgentSection>
    </div>
  )
}
