import { VERDICT_KEYS, getVerdictConfig } from '@/constants/verdicts'
import { Reveal } from '@/components/landing/Reveal'
import { VerdictBadge } from '@/components/sciverify/VerdictBadge'

export function LandingVerdictTypes() {
  return (
    <section id="verdicts" className="scroll-mt-20 px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-wider text-primary">
            Verdict system
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
            Explicit outcomes for every claim
          </h2>
          <p className="mt-4 max-w-2xl text-text-secondary">
            SciVerify classifies verification results into five research-meaningful
            verdict types — each with semantic styling and clear definitions.
          </p>
        </Reveal>

        <div className="mt-10 flex flex-wrap gap-2">
          {VERDICT_KEYS.map((key, index) => (
            <Reveal key={key} delay={index * 60}>
              <VerdictBadge verdict={key} />
            </Reveal>
          ))}
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {VERDICT_KEYS.map((key, index) => {
            const config = getVerdictConfig(key)
            const Icon = config.icon

            return (
              <Reveal key={key} delay={index * 80}>
                <div
                  className={`rounded-xl border p-5 transition-all duration-300 hover:-translate-y-0.5 ${config.bgClass} ${config.borderClass}`}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${config.borderClass} ${config.bgClass}`}
                    >
                      <Icon className={`h-4 w-4 ${config.textClass}`} />
                    </span>
                    <div>
                      <h3 className={`font-semibold ${config.textClass}`}>
                        {config.label}
                      </h3>
                      <p className="mt-1 text-sm leading-relaxed text-text-secondary">
                        {config.description}
                      </p>
                    </div>
                  </div>
                </div>
              </Reveal>
            )
          })}
        </div>
      </div>
    </section>
  )
}
