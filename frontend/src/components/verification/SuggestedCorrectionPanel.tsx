import { useState } from 'react'
import { ArrowDown, Check, Copy } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import type { SuggestedCorrection } from '@/types/verification'

export interface SuggestedCorrectionPanelProps {
  correction: SuggestedCorrection | null | undefined
}

export function SuggestedCorrectionPanel({
  correction,
}: SuggestedCorrectionPanelProps) {
  const [copied, setCopied] = useState(false)

  if (!correction) {
    return null
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(correction.suggestedWording)
      setCopied(true)
      toast.success('Correction copied to clipboard.')
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Unable to copy. Please copy the text manually.')
    }
  }

  return (
    <Panel padding="lg" className="space-y-5 border-warning/20">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold text-text-primary">
          Suggested correction
        </h3>
        <Badge variant="warning">Human approval required</Badge>
      </div>

      <p className="text-sm text-text-secondary">
        SciVerify only suggests corrections. It does not automatically modify
        research papers or manuscripts.
      </p>

      <div className="space-y-4">
        <div className="rounded-lg border border-border bg-surface p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Original claim
          </p>
          <p className="mt-3 text-sm leading-relaxed text-text-primary">
            &ldquo;{correction.originalClaim}&rdquo;
          </p>
        </div>

        <div className="flex justify-center" aria-hidden>
          <ArrowDown className="h-4 w-4 text-text-muted" />
        </div>

        <div className="rounded-lg border border-danger/20 bg-danger/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-danger">
            Why it needs revision
          </p>
          <p className="mt-3 text-sm leading-relaxed text-text-secondary">
            {correction.problem}
          </p>
        </div>

        <div className="flex justify-center" aria-hidden>
          <ArrowDown className="h-4 w-4 text-text-muted" />
        </div>

        <div className="rounded-lg border border-primary/20 bg-primary-muted p-4">
          <p className="text-xs font-semibold uppercase tracking-widest text-primary">
            Recommended wording
          </p>
          <p className="mt-3 text-sm leading-relaxed text-text-primary">
            &ldquo;{correction.suggestedWording}&rdquo;
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-medium text-warning">
          Human approval required before using this wording in any publication.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleCopy}
          aria-label="Copy suggested correction to clipboard"
        >
          {copied ? (
            <>
              <Check className="h-4 w-4" />
              Copied
            </>
          ) : (
            <>
              <Copy className="h-4 w-4" />
              Copy correction
            </>
          )}
        </Button>
      </div>
    </Panel>
  )
}
