import { ExternalLink } from 'lucide-react'
import { forwardRef } from 'react'
import { cn } from '@/lib/cn'
import { ScoreBar } from '@/components/verification/ScoreBar'
import { Badge } from '@/components/ui/Badge'
import { Panel } from '@/components/ui/Card'
import type { EvidenceItem } from '@/types/verification'

export interface VerificationEvidenceCardProps {
  item: EvidenceItem
  index: number
  linkedSegmentLabels?: string[]
  highlighted?: boolean
  onSelect?: (item: EvidenceItem) => void
}

function resolveSourceHref(item: EvidenceItem) {
  if (item.sourceUrl) return item.sourceUrl
  if (item.identifier?.startsWith('10.')) {
    return `https://doi.org/${item.identifier}`
  }
  return undefined
}

export const VerificationEvidenceCard = forwardRef<
  HTMLDivElement,
  VerificationEvidenceCardProps
>(function VerificationEvidenceCard(
  {
    item,
    index,
    linkedSegmentLabels = [],
    highlighted = false,
    onSelect,
  },
  ref,
) {
  const href = resolveSourceHref(item)

  return (
    <div
      ref={ref}
      id={`evidence-${item.id}`}
      className={cn(
        highlighted && 'rounded-xl ring-2 ring-primary/50 shadow-md transition-shadow duration-300',
      )}
    >
      <Panel padding="md" className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Evidence #{index + 1}
          </p>
          <p className="mt-1 text-sm font-medium text-text-primary">{item.evidenceType}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {linkedSegmentLabels.length > 0 ? (
            <Badge variant="muted" size="sm">
              Linked to {linkedSegmentLabels.length} claim segment
              {linkedSegmentLabels.length === 1 ? '' : 's'}
            </Badge>
          ) : null}
          <Badge variant="muted" size="sm">
            {item.id}
          </Badge>
        </div>
      </div>

      {linkedSegmentLabels.length > 0 ? (
        <p className="text-xs text-text-muted">
          Supports: {linkedSegmentLabels.join(', ')}
        </p>
      ) : null}

      <button
        type="button"
        className="grid w-full gap-4 text-left sm:grid-cols-2"
        onClick={() => onSelect?.(item)}
      >
        <ScoreBar label="Relevance" value={item.relevance} />
        {item.claimOverlap !== undefined ? (
          <ScoreBar label="Claim overlap" value={item.claimOverlap} />
        ) : null}
      </button>

      {item.numericOverlap !== undefined && item.numericOverlap > 0 ? (
        <ScoreBar label="Numeric overlap" value={item.numericOverlap} />
      ) : null}

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
          Evidence
        </p>
        <blockquote className="mt-2 border-l-2 border-primary/30 pl-4 text-sm leading-relaxed text-text-secondary">
          {item.excerpt}
        </blockquote>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        {item.page != null ? <span>Page {item.page}</span> : null}
        {item.source ? <span>{item.source}</span> : null}
      </div>

      {href ? (
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:text-primary-hover"
        >
          Open source
          <ExternalLink className="h-3.5 w-3.5" aria-hidden />
        </a>
      ) : null}
      </Panel>
    </div>
  )
})
