import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Reveal } from '@/components/landing/Reveal'
import { ROUTES } from '@/constants'
import { Button } from '@/components/ui/Button'
import { useLandingEntry } from '@/hooks/useLandingEntry'

export function LandingCTA() {
  const { startPath, isLocalDemo } = useLandingEntry()
  return (
    <section className="px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <div className="relative overflow-hidden rounded-2xl border border-primary/25 bg-surface px-6 py-12 text-center sm:px-10 sm:py-16">
            <div className="pointer-events-none absolute inset-0 landing-glow opacity-60" aria-hidden="true" />
            <div className="relative">
              <h2 className="text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
                Ready to verify citations with confidence?
              </h2>
              <p className="mx-auto mt-4 max-w-2xl text-text-secondary">
                {isLocalDemo
                  ? 'Enter Local Demo to verify citations and keep reports in this browser.'
                  : 'Create a SciVerify account and start building a more defensible evidence workflow for your next manuscript, review, or research sprint.'}
              </p>
              <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Link to={startPath}>
                  <Button size="lg">
                    {isLocalDemo ? 'Enter Local Demo' : 'Create free account'}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                {!isLocalDemo ? (
                  <Link to={ROUTES.LOGIN}>
                    <Button variant="outline" size="lg">
                      Sign in
                    </Button>
                  </Link>
                ) : null}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
