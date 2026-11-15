import { Panel } from '@/components/ui/Card'

const pipelineSteps = [
  { step: '01', label: 'Evidence retrieval' },
  { step: '02', label: 'Prosecutor challenge' },
  { step: '03', label: 'Defender analysis' },
  { step: '04', label: 'Adjudicator decision' },
]

export function VerificationPipelinePreview() {
  return (
    <Panel padding="md" className="border-border/60 bg-surface-elevated/30">
      <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
        Verification pipeline
      </p>
      <ol className="mt-4 grid gap-3 sm:grid-cols-2">
        {pipelineSteps.map((item) => (
          <li
            key={item.step}
            className="flex items-center gap-3 rounded-lg border border-border/60 bg-surface/50 px-3 py-2.5"
          >
            <span className="font-mono text-xs font-semibold text-primary">
              {item.step}
            </span>
            <span className="text-sm text-text-secondary">{item.label}</span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-text-muted">
        Informational preview only. Agents run after you submit a verification.
      </p>
    </Panel>
  )
}
