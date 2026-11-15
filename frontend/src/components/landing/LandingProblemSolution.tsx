import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Reveal } from '@/components/landing/Reveal'
import { Panel } from '@/components/ui/Card'

export function LandingProblemSolution() {
  return (
    <section className="px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-wider text-primary">
            Why SciVerify
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
            From citation uncertainty to evidence clarity
          </h2>
        </Reveal>

        <div className="mt-12 grid gap-6 lg:grid-cols-2">
          <Reveal delay={100}>
            <Panel className="h-full border-danger/20 bg-danger/5">
              <div className="mb-4 flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-danger" />
                <h3 className="text-lg font-semibold text-text-primary">The problem</h3>
              </div>
              <ul className="space-y-3 text-sm leading-relaxed text-text-secondary">
                <li>Citations are often overstated, misread, or disconnected from primary sources.</li>
                <li>Manual verification is slow, inconsistent, and hard to scale across manuscripts.</li>
                <li>Generic AI chat tools produce confident answers without traceable evidence chains.</li>
              </ul>
            </Panel>
          </Reveal>

          <Reveal delay={200}>
            <Panel className="h-full border-primary/20 bg-primary-muted">
              <div className="mb-4 flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-primary" />
                <h3 className="text-lg font-semibold text-text-primary">The SciVerify approach</h3>
              </div>
              <ul className="space-y-3 text-sm leading-relaxed text-text-secondary">
                <li>Specialized agents challenge and defend whether a citation supports the claim.</li>
                <li>An adjudicator weighs both perspectives against retrievable evidence.</li>
                <li>Deliver explicit verdicts with confidence scores and source transparency.</li>
              </ul>
            </Panel>
          </Reveal>
        </div>
      </div>
    </section>
  )
}
