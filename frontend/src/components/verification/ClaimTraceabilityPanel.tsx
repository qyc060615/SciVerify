import {
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  MinusCircle,
  XCircle,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import { Panel } from '@/components/ui/Card'
import { segmentLabel } from '@/lib/traceability-utils'
import type { ClaimSegment, ClaimSegmentStatus } from '@/types/verification'

const STATUS_CONFIG: Record<
  ClaimSegmentStatus,
  {
    label: string
    icon: typeof CheckCircle2
    className: string
  }
> = {
  SUPPORTED: {
    label: 'Supported',
    icon: CheckCircle2,
    className: 'text-success border-success/30 bg-success/10',
  },
  PARTIALLY_SUPPORTED: {
    label: 'Partially supported',
    icon: MinusCircle,
    className: 'text-warning border-warning/30 bg-warning/10',
  },
  UNSUPPORTED: {
    label: 'Unsupported',
    icon: CircleHelp,
    className: 'text-text-muted border-border bg-surface-elevated',
  },
  CONTRADICTED: {
    label: 'Contradicted',
    icon: XCircle,
    className: 'text-danger border-danger/30 bg-danger/10',
  },
}

export interface ClaimTraceabilityPanelProps {
  claim: string
  traceability: NonNullable<import('@/types/verification').ClaimTraceability>
  selectedSegmentId?: string | null
  highlightedEvidenceIds?: string[]
  onSegmentSelect?: (segment: ClaimSegment) => void
}

export function ClaimTraceabilityPanel({
  claim,
  traceability,
  selectedSegmentId,
  highlightedEvidenceIds = [],
  onSegmentSelect,
}: ClaimTraceabilityPanelProps) {
  return (
    <Panel padding="lg" className="space-y-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Claim traceability
        </p>
        <p className="mt-2 text-sm leading-relaxed text-text-secondary">{claim}</p>
      </div>

      <div className="space-y-3">
        {traceability.segments.map((segment, index) => {
          const config = STATUS_CONFIG[segment.status]
          const Icon = config.icon
          const isSelected = selectedSegmentId === segment.id
          const segmentHighlightsEvidence = segment.evidenceIds.some((id) =>
            highlightedEvidenceIds.includes(id),
          )

          return (
            <button
              key={segment.id}
              type="button"
              className={cn(
                'w-full rounded-lg border p-4 text-left transition-colors',
                config.className,
                isSelected && 'ring-2 ring-primary/40',
                segmentHighlightsEvidence && !isSelected && 'ring-1 ring-primary/20',
              )}
              onClick={() => onSegmentSelect?.(segment)}
              aria-pressed={isSelected}
            >
              <div className="flex items-start gap-3">
                <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                <div className="min-w-0 flex-1 space-y-2">
                  <p className="text-sm font-medium leading-relaxed text-text-primary">
                    &ldquo;{segment.text}&rdquo;
                  </p>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-semibold uppercase tracking-wide">
                      {config.label}
                    </span>
                    <span className="text-text-muted">·</span>
                    <span className="tabular-nums">
                      Coverage: {segment.coverageScore}%
                    </span>
                    <span className="text-text-muted">·</span>
                    <span>
                      {segment.evidenceIds.length} supporting evidence item
                      {segment.evidenceIds.length === 1 ? '' : 's'}
                    </span>
                  </div>
                  <p className="text-xs text-text-muted">{segmentLabel(index)}</p>
                </div>
              </div>
            </button>
          )
        })}
      </div>

      <div className="border-t border-border pt-4">
        <p className="text-sm text-text-secondary">
          Overall coverage:{' '}
          <span className="font-semibold tabular-nums text-text-primary">
            {traceability.overallCoverage}%
          </span>
        </p>
      </div>

      {traceability.warnings && traceability.warnings.length > 0 ? (
        <div className="space-y-2 border-t border-border pt-4">
          {traceability.warnings.map((warning) => (
            <p
              key={warning}
              className="flex items-start gap-2 text-sm leading-relaxed text-text-secondary"
            >
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
              <span>{warning}</span>
            </p>
          ))}
        </div>
      ) : null}
    </Panel>
  )
}
