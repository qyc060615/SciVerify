import { BookOpen, FlaskConical, Scale, ShieldCheck } from 'lucide-react'
import { Reveal } from '@/components/landing/Reveal'
import { StatCard } from '@/components/sciverify/StatCard'

const trustPoints = [
  {
    icon: ShieldCheck,
    title: 'Built for research integrity',
    text: 'Designed for labs, reviewers, and hackathon-grade scientific workflows — not consumer chat.',
  },
  {
    icon: BookOpen,
    title: 'Source-transparent by default',
    text: 'Verdicts are accompanied by retrievable evidence cards and traceable agent steps.',
  },
  {
    icon: Scale,
    title: 'Nuanced classification',
    text: 'Five verdict types capture support, exaggeration, contradiction, insufficiency, and fabrication.',
  },
  {
    icon: FlaskConical,
    title: 'Evidence-first methodology',
    text: 'SciVerify prioritizes literature alignment over fluent but ungrounded summaries.',
  },
]

export function LandingTrustSection() {
  return (
    <section id="trust" className="scroll-mt-20 px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-wider text-primary">
            Trust & research focus
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
            Verification you can defend in a paper review
          </h2>
        </Reveal>

        <div className="mt-12 grid gap-4 sm:grid-cols-2">
          {trustPoints.map((point, index) => (
            <Reveal key={point.title} delay={index * 100}>
              <div className="flex h-full gap-4 rounded-xl border border-border bg-surface p-5 transition-colors hover:border-primary/25 hover:bg-surface-elevated/50">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-surface-elevated">
                  <point.icon className="h-5 w-5 text-primary" />
                </span>
                <div>
                  <h3 className="font-semibold text-text-primary">{point.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                    {point.text}
                  </p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>

        <div className="mt-10 grid gap-4 md:grid-cols-3">
          <Reveal delay={100}>
            <StatCard
              label="Verdict types"
              value="5"
              description="Structured research outcomes"
            />
          </Reveal>
          <Reveal delay={180}>
            <StatCard
              label="Debate agents"
              value="3"
              description="Prosecutor, defender, adjudicator"
            />
          </Reveal>
          <Reveal delay={260}>
            <StatCard
              label="Evidence trail"
              value="100%"
              description="Inspectable source cards per run"
            />
          </Reveal>
        </div>
      </div>
    </section>
  )
}
