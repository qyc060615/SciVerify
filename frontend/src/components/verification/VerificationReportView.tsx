import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import { AgentAnalysisPanel } from '@/components/verification/AgentAnalysisPanel'
import { ClaimTraceabilityPanel } from '@/components/verification/ClaimTraceabilityPanel'
import { SuggestedCorrectionPanel } from '@/components/verification/SuggestedCorrectionPanel'
import { ValidationWarningsPanel } from '@/components/verification/ValidationWarningsPanel'
import { VerdictHeader } from '@/components/verification/VerdictHeader'
import { VerificationEvidenceCard } from '@/components/verification/VerificationEvidenceCard'
import { getVerdictConfig } from '@/constants/verdicts'
import { buildEvidenceSegmentLabelMap } from '@/lib/traceability-utils'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Divider } from '@/components/ui/Divider'
import type { VerdictKey } from '@/constants/verdicts'
import type { ClaimSegment, EvidenceItem, VerificationResult } from '@/types/verification'

export interface VerificationReportViewProps {
  result: VerificationResult
  onBack?: () => void
}

function ReportSection({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section className="space-y-3">
      <Divider label={title} />
      {children}
    </section>
  )
}

function VerdictContextNote({ verdict }: { verdict: VerdictKey }) {
  const notes: Partial<Record<VerdictKey, string>> = {
    INSUFFICIENT:
      'The retrieved paper evidence was insufficient to determine whether this claim is supported or contradicted.',
    FABRICATED:
      'The cited paper does not appear to contain information that supports this claim as stated.',
    OVERSTATED:
      'The core idea may be supported, but the claim is broader or stronger than the cited evidence allows.',
    CONTRADICTS:
      'Retrieved evidence conflicts with all or part of the claim.',
    SUPPORTS:
      'Retrieved evidence supports the claim within the scope described in the cited paper.',
  }

  const note = notes[verdict]
  if (!note) return null

  const config = getVerdictConfig(verdict)

  return (
    <Panel padding="md" className={`text-sm leading-relaxed text-text-secondary ${config.bgClass}`}>
      {note}
    </Panel>
  )
}

export function VerificationReportView({
  result,
  onBack,
}: VerificationReportViewProps) {
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null)
  const [highlightedEvidenceIds, setHighlightedEvidenceIds] = useState<string[]>([])
  const evidenceRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const evidenceSegmentLabels = useMemo(
    () => buildEvidenceSegmentLabelMap(result.claimTraceability?.segments ?? []),
    [result.claimTraceability?.segments],
  )

  const showCorrection =
    result.verdict === 'OVERSTATED' ||
    result.verdict === 'CONTRADICTS' ||
    result.verdict === 'FABRICATED'

  useEffect(() => {
    if (highlightedEvidenceIds.length === 0) return

    const timeout = window.setTimeout(() => {
      setHighlightedEvidenceIds([])
    }, 2400)

    return () => window.clearTimeout(timeout)
  }, [highlightedEvidenceIds])

  const handleSegmentSelect = (segment: ClaimSegment) => {
    setSelectedSegmentId(segment.id)
    setHighlightedEvidenceIds(segment.evidenceIds)

    const firstId = segment.evidenceIds[0]
    if (firstId) {
      evidenceRefs.current[firstId]?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    }
  }

  const handleEvidenceSelect = (item: EvidenceItem) => {
    const linkedSegment = result.claimTraceability?.segments.find((segment) =>
      segment.evidenceIds.includes(item.id),
    )
    setHighlightedEvidenceIds([item.id])
    if (linkedSegment) {
      setSelectedSegmentId(linkedSegment.id)
    }
  }

  return (
    <article className="space-y-8">
      <header className="space-y-4 border-b border-border pb-6">
        {onBack ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onBack}
            className="-ml-2"
            aria-label="Back to verification home"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden />
            Back to verification
          </Button>
        ) : null}
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-widest text-primary">
            Science verification report
          </p>
          <p className="text-sm text-text-muted">
            Generated {new Date(result.createdAt).toLocaleString()}
          </p>
        </div>
      </header>

      <VerdictHeader
        verdict={result.verdict}
        confidence={result.confidence}
        claim={result.claim}
        paperTitle={result.paperTitle}
        paperDoi={result.paperDoi}
        agentAgreement={result.agentAgreement}
        summary={result.summary}
      />

      <VerdictContextNote verdict={result.verdict} />

      {result.claimTraceability ? (
        <ClaimTraceabilityPanel
          claim={result.claim}
          traceability={result.claimTraceability}
          selectedSegmentId={selectedSegmentId}
          highlightedEvidenceIds={highlightedEvidenceIds}
          onSegmentSelect={handleSegmentSelect}
        />
      ) : null}

      <ReportSection title="Evidence">
        {result.evidence.length > 0 ? (
          <div className="grid gap-4">
            {result.evidence.slice(0, 5).map((item, index) => (
              <VerificationEvidenceCard
                key={item.id}
                ref={(node) => {
                  evidenceRefs.current[item.id] = node
                }}
                item={item}
                index={index}
                linkedSegmentLabels={evidenceSegmentLabels.get(item.id)}
                highlighted={
                  highlightedEvidenceIds.includes(item.id) ||
                  Boolean(
                    selectedSegmentId &&
                      result.claimTraceability?.segments
                        .find((segment) => segment.id === selectedSegmentId)
                        ?.evidenceIds.includes(item.id),
                  )
                }
                onSelect={handleEvidenceSelect}
              />
            ))}
          </div>
        ) : (
          <Panel padding="md" className="text-sm text-text-secondary">
            No evidence items were retrieved for this verification.
          </Panel>
        )}
      </ReportSection>

      <ReportSection title="Reasoning">
        <Panel padding="md">
          <p className="text-sm leading-relaxed text-text-primary">{result.reasoning}</p>
        </Panel>
      </ReportSection>

      <ReportSection title="Agent analysis">
        <AgentAnalysisPanel
          prosecutor={result.prosecutor}
          defender={result.defender}
          adjudicator={result.adjudicator}
          prosecutorDetail={result.prosecutorDetail}
          defenderDetail={result.defenderDetail}
          adjudicatorDetail={result.adjudicatorDetail}
        />
      </ReportSection>

      {result.validationWarnings && result.validationWarnings.length > 0 ? (
        <ValidationWarningsPanel warnings={result.validationWarnings} />
      ) : null}

      {showCorrection && result.suggestedCorrection ? (
        <ReportSection title="Suggested correction">
          <SuggestedCorrectionPanel correction={result.suggestedCorrection} />
        </ReportSection>
      ) : null}

      {result.context ? (
        <ReportSection title="Additional context">
          <Panel padding="md">
            <p className="text-sm leading-relaxed text-text-secondary">{result.context}</p>
          </Panel>
        </ReportSection>
      ) : null}

      <ReportSection title="Citation">
        <Panel padding="md">
          <p className="text-sm leading-relaxed text-text-primary">{result.citation}</p>
          <p className="mt-2 text-xs uppercase tracking-wide text-text-muted">
            Source type: {result.sourceType}
          </p>
        </Panel>
      </ReportSection>
    </article>
  )
}
