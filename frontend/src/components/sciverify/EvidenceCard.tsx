import { ExternalLink, Quote } from 'lucide-react'
import { cn } from '@/lib/cn'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'
import { Badge } from '@/components/ui/Badge'
import type { VerdictKey } from '@/constants/verdicts'
import type { EvidenceStrength } from '@/types/verification'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/Card'

const strengthVariant: Record<
  EvidenceStrength,
  'success' | 'warning' | 'default'
> = {
  HIGH: 'success',
  MEDIUM: 'warning',
  LOW: 'default',
}

export interface EvidenceCardProps {
  title: string
  excerpt: string
  source?: string
  authors?: string
  year?: number
  whyItMatters?: string
  strength?: EvidenceStrength
  identifier?: string
  sourceUrl?: string
  verdict?: VerdictKey
  relevance?: number
  className?: string
}

function resolveSourceHref(identifier?: string, sourceUrl?: string) {
  if (sourceUrl) return sourceUrl
  if (identifier?.startsWith('10.')) {
    return `https://doi.org/${identifier}`
  }
  return undefined
}

function SectionDivider() {
  return <div className="border-t border-border/70" aria-hidden />
}

export function EvidenceCard({
  title,
  excerpt,
  source,
  authors,
  year,
  whyItMatters,
  strength,
  identifier,
  sourceUrl,
  verdict,
  relevance,
  className,
}: EvidenceCardProps) {
  const href = resolveSourceHref(identifier, sourceUrl)
  const sourceLine = [authors, year?.toString(), source].filter(Boolean).join(' · ')

  return (
    <Card
      className={cn(
        'h-full transition-all duration-200 motion-reduce:transition-none hover:border-border/80 hover:shadow-sm',
        className,
      )}
    >
      <CardHeader className="space-y-4 p-5 pb-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-elevated">
              <Quote className="h-4 w-4 text-text-muted" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                Source
              </p>
              <CardTitle className="mt-2 text-sm leading-snug">{title}</CardTitle>
              {sourceLine ? (
                <CardDescription className="mt-1 leading-relaxed">
                  {sourceLine}
                </CardDescription>
              ) : null}
              {identifier ? (
                <p className="mt-2 truncate font-mono text-xs text-text-muted">
                  {identifier}
                </p>
              ) : null}
            </div>
          </div>
          {verdict ? <VerdictBadge verdict={verdict} size="sm" /> : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-5 pt-4">
        <SectionDivider />

        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Relevant evidence
          </p>
          <p className="mt-3 text-sm leading-relaxed text-text-secondary">
            &ldquo;{excerpt}&rdquo;
          </p>
        </div>

        {whyItMatters ? (
          <>
            <SectionDivider />
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
                Why this matters
              </p>
              <p className="mt-3 text-sm leading-relaxed text-text-secondary">
                {whyItMatters}
              </p>
            </div>
          </>
        ) : null}

        <SectionDivider />

        <div className="flex flex-wrap items-center gap-2">
          {strength ? (
            <Badge variant={strengthVariant[strength]} size="sm">
              Evidence strength: {strength}
            </Badge>
          ) : null}
          {relevance !== undefined ? (
            <Badge variant="muted" size="sm">
              Relevance: {relevance}%
            </Badge>
          ) : null}
        </div>

        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:text-primary-hover"
          >
            Open source
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : null}
      </CardContent>
    </Card>
  )
}
