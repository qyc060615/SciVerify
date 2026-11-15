import { ExternalLink, FileText } from 'lucide-react'
import { cn } from '@/lib/cn'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'

export interface SourceCardProps {
  title: string
  authors?: string
  journal?: string
  year?: number
  doi?: string
  url?: string
  type?: string
  className?: string
}

export function SourceCard({
  title,
  authors,
  journal,
  year,
  doi,
  url,
  type = 'Journal Article',
  className,
}: SourceCardProps) {
  return (
    <Card className={cn('h-full', className)}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-elevated">
              <FileText className="h-4 w-4 text-primary" />
            </span>
            <div className="min-w-0">
              <CardTitle className="text-sm leading-snug">{title}</CardTitle>
              <CardDescription>
                {[authors, journal, year?.toString()].filter(Boolean).join(' · ')}
              </CardDescription>
            </div>
          </div>
          <Badge variant="muted" size="sm">
            {type}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        {doi ? (
          <p className="truncate font-mono text-xs text-text-muted">DOI: {doi}</p>
        ) : null}
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary-hover"
          >
            View source
            <ExternalLink className="h-3 w-3" />
          </a>
        ) : null}
      </CardContent>
    </Card>
  )
}
