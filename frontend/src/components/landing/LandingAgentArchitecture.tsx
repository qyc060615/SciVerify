import { Reveal } from '@/components/landing/Reveal'
import { AgentCard } from '@/components/sciverify/AgentCard'
import { Panel } from '@/components/ui/Card'

const agents = [
  {
    name: 'Prosecutor',
    role: 'Challenge the claim',
    status: 'running' as const,
    description:
      'Challenges the claim and searches for evidence that the citation may be misleading, incomplete, or overstated.',
  },
  {
    name: 'Defender',
    role: 'Build the supporting case',
    status: 'running' as const,
    description:
      'Builds the strongest evidence-based case for why the citation supports the claim.',
  },
  {
    name: 'Adjudicator',
    role: 'Decide the final verdict',
    status: 'idle' as const,
    description:
      'Weighs the Prosecutor and Defender arguments against the evidence and produces the final verdict.',
  },
]

export function LandingAgentArchitecture() {
  return (
    <section id="agents" className="scroll-mt-20 px-4 py-20 sm:px-6 sm:py-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <p className="text-sm font-medium uppercase tracking-wider text-primary">
            Architecture
          </p>
          <h2 className="mt-3 max-w-2xl text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
            Three-agent debate system
          </h2>
          <p className="mt-4 max-w-2xl text-text-secondary">
            Three specialized agents examine the claim from different perspectives
            before reaching a final evidence-backed verdict.
          </p>
          <p className="mt-3 max-w-2xl text-sm text-text-muted">
            Two agents argue from opposing perspectives. A third agent evaluates
            both against the evidence.
          </p>
        </Reveal>

        <Reveal delay={80}>
          <Panel padding="sm" className="mt-8 text-center font-mono text-xs text-text-secondary sm:text-sm">
            Claim → Prosecutor + Defender → Adjudicator → Final Verdict
          </Panel>
        </Reveal>

        <div className="mt-10 grid gap-6 lg:grid-cols-3">
          {agents.map((agent, index) => (
            <Reveal key={agent.name} delay={index * 120}>
              <AgentCard {...agent} className="h-full" />
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
