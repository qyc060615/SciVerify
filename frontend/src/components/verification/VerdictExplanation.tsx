import { Check, X } from 'lucide-react'
import { cn } from '@/lib/cn'
import { getVerdictConfig } from '@/constants/verdicts'
import { ConfidenceBar } from '@/components/sciverify/ConfidenceBar'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'
import { Panel } from '@/components/ui/Card'
import type { VerdictKey } from '@/constants/verdicts'
import type { EvidenceFactor } from '@/types/verification'

export interface VerdictExplanationProps {
  verdict: VerdictKey
  confidence: number
  summary: string
  evidenceFactors: EvidenceFactor[]
  className?: string
}

export function VerdictExplanation({
  verdict,
  confidence,
  summary,
  evidenceFactors,
  className,
}: VerdictExplanationProps) {
  const config = getVerdictConfig(verdict)

  return (
    <Panel
      padding="lg"
      className={cn(
        'space-y-6 border ring-1 ring-inset',
        config.borderClass,
        config.ringClass,
        className,
      )}
    >
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Final verdict
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-4">
          <VerdictBadge verdict={verdict} size="md" />
          <p className="text-base font-semibold tabular-nums text-text-primary">
            {confidence}% confidence
          </p>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-text-primary">{summary}</p>

      {evidenceFactors.length > 0 ? (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Evidence factors
          </p>
          <ul className="mt-3 space-y-2">
            {evidenceFactors.map((factor) => (
              <li
                key={factor.text}
                className="flex items-start gap-2 text-sm text-text-secondary"
              >
                {factor.supported ? (
                  <Check
                    className="mt-0.5 h-4 w-4 shrink-0 text-success"
                    aria-label="Supported"
                  />
                ) : (
                  <X
                    className="mt-0.5 h-4 w-4 shrink-0 text-danger"
                    aria-label="Not supported"
                  />
                )}
                <span>{factor.text}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <ConfidenceBar value={confidence} verdict={verdict} label="Confidence" />
    </Panel>
  )
}
