import { Link } from 'react-router-dom'
import { ArrowRight, FileSearch, ShieldCheck } from 'lucide-react'
import { useLandingEntry } from '@/hooks/useLandingEntry'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Reveal } from '@/components/landing/Reveal'

export function LandingHero() {
  const { startPath } = useLandingEntry()
  return (
    <section className="landing-grid relative overflow-hidden px-4 pb-20 pt-16 sm:px-6 sm:pb-28 sm:pt-24">
      <div className="pointer-events-none absolute inset-0 landing-glow" aria-hidden="true" />

      <div className="relative mx-auto max-w-6xl">
        <Reveal>
          <Badge variant="primary" className="mb-6">
            Multi-agent citation verification
          </Badge>
        </Reveal>

        <Reveal delay={100}>
          <h1 className="max-w-4xl text-4xl font-semibold leading-tight tracking-tight text-text-primary sm:text-5xl lg:text-6xl">
            Verify scientific citations with{' '}
            <span className="text-primary">evidence-backed</span> confidence
          </h1>
        </Reveal>

        <Reveal delay={200}>
          <p className="mt-6 max-w-2xl text-base leading-relaxed text-text-secondary sm:text-lg">
            SciVerify helps researchers, reviewers, and teams validate whether
            cited claims truly match the underlying literature — using specialized
            agents that challenge, defend, and adjudicate, not opaque guesswork.
          </p>
        </Reveal>

        <Reveal delay={300}>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
            <Link to={startPath}>
              <Button size="lg" className="w-full sm:w-auto">
                Start verifying
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <a href="#how-it-works">
              <Button variant="outline" size="lg" className="w-full sm:w-auto">
                See how it works
              </Button>
            </a>
          </div>
        </Reveal>

        <Reveal delay={400}>
          <div className="mt-14 grid gap-4 sm:grid-cols-3">
            {[
              {
                icon: FileSearch,
                label: 'Evidence-first',
                text: 'Every verdict links to retrievable sources.',
              },
              {
                icon: ShieldCheck,
                label: 'Research-grade',
                text: 'Built for academic integrity workflows.',
              },
              {
                icon: ArrowRight,
                label: 'Structured output',
                text: 'Clear verdicts, not conversational noise.',
              },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-xl border border-border/80 bg-surface/60 p-4 backdrop-blur-sm transition-colors hover:border-primary/30 hover:bg-surface-elevated/60"
              >
                <item.icon className="mb-3 h-5 w-5 text-primary" />
                <p className="text-sm font-medium text-text-primary">{item.label}</p>
                <p className="mt-1 text-sm text-text-secondary">{item.text}</p>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  )
}
