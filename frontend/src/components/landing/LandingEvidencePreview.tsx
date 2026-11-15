import { Reveal } from '@/components/landing/Reveal'
import { EvidenceCard } from '@/components/sciverify/EvidenceCard'
import { ConfidenceBar } from '@/components/sciverify/ConfidenceBar'
import { VerdictCard } from '@/components/sciverify/VerdictCard'
import { Panel } from '@/components/ui/Card'

export function LandingEvidencePreview() {
  return (
    <section className="px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-wider text-primary">
            Evidence preview
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
            Inspect the evidence behind every verdict
          </h2>
          <p className="mt-4 max-w-2xl text-text-secondary">
            Sample output from the SciVerify interface — showing how claims map to
            sources, relevance, and final classification.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-6 lg:grid-cols-5">
          <Reveal className="lg:col-span-3" delay={100}>
            <div className="grid gap-4 sm:grid-cols-2">
              <EvidenceCard
                title="Primary outcome alignment"
                source="Nature Medicine, 2023"
                excerpt="The intervention group showed a statistically significant reduction in the primary biomarker compared with placebo controls."
                verdict="SUPPORTS"
                relevance={94}
              />
              <EvidenceCard
                title="Secondary endpoint mismatch"
                source="Journal of Clinical Research, 2022"
                excerpt="After confounder adjustment, the reported effect size was substantially lower than the cited magnitude."
                verdict="OVERSTATED"
                relevance={81}
              />
            </div>
          </Reveal>

          <Reveal className="lg:col-span-2" delay={200}>
            <div className="flex h-full flex-col gap-4">
              <VerdictCard
                verdict="OVERSTATED"
                title="Claim verification result"
                summary="The cited effect is directionally supported but the magnitude appears overstated relative to primary literature."
                confidence={76}
              />
              <Panel padding="md">
                <ConfidenceBar
                  value={76}
                  verdict="OVERSTATED"
                  label="Overall confidence"
                />
              </Panel>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
