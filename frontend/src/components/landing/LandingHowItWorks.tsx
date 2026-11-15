import { Reveal } from '@/components/landing/Reveal'

const steps = [
  {
    step: '01',
    title: 'Submit a claim or citation',
    description:
      'Provide a DOI, citation string, or excerpted claim from a manuscript or review.',
  },
  {
    step: '02',
    title: 'Prosecutor and Defender debate the claim',
    description:
      'One agent challenges the citation while another builds the strongest supporting case — both grounded in evidence.',
  },
  {
    step: '03',
    title: 'Adjudicator delivers the verdict',
    description:
      'A third agent weighs both sides and returns a verdict type, confidence score, and evidence cards you can inspect.',
  },
]

export function LandingHowItWorks() {
  return (
    <section id="how-it-works" className="scroll-mt-20 px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-wider text-primary">
            Workflow
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
            How SciVerify works
          </h2>
          <p className="mt-4 max-w-2xl text-text-secondary">
            An evidence-first verification workflow where agents debate before
            deciding — not open-ended chat.
          </p>
        </Reveal>

        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {steps.map((item, index) => (
            <Reveal key={item.step} delay={index * 120}>
              <div className="group relative h-full rounded-xl border border-border bg-surface p-6 transition-all duration-300 hover:-translate-y-1 hover:border-primary/30 hover:shadow-lg">
                <span className="text-xs font-mono font-medium text-primary">
                  {item.step}
                </span>
                <h3 className="mt-4 text-lg font-semibold text-text-primary">
                  {item.title}
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-text-secondary">
                  {item.description}
                </p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
