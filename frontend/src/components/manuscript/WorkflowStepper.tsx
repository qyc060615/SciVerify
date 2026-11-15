import { Check } from 'lucide-react'

const workflowStages = ['upload', 'references', 'claims', 'verification', 'report'] as const
export type WorkflowStage = typeof workflowStages[number]
const labels = ['Upload', 'References', 'Claims', 'Verification', 'Report']
export function WorkflowStepper({ current, completed, allowed, onSelect, busy = false }: {
  current: WorkflowStage; completed: WorkflowStage[]; allowed: WorkflowStage[]
  onSelect: (stage: WorkflowStage) => void; busy?: boolean
}) {
  return <nav aria-label="Verification workflow" className="grid min-w-0 grid-cols-5 gap-1 rounded-xl border border-border bg-surface p-2 sm:gap-3 sm:p-3">
    {workflowStages.map((stage, index) => <button key={stage} type="button" aria-current={current === stage ? 'step' : undefined}
      disabled={busy || !allowed.includes(stage)} onClick={() => onSelect(stage)}
      aria-label={labels[index] + (completed.includes(stage) ? ' — completed' : '')}
      className={'flex min-w-0 flex-col items-center gap-1.5 rounded-lg px-1 py-2 disabled:cursor-default disabled:opacity-40 ' + (current === stage ? 'bg-primary-muted text-primary' : 'text-text-secondary hover:bg-surface-hover')}>
      <span className={'flex h-6 w-6 items-center justify-center rounded-full border text-xs ' + (completed.includes(stage) ? 'border-success/40 text-success' : 'border-current/30')}>
        {completed.includes(stage) ? <Check className="h-3.5 w-3.5" aria-hidden /> : index + 1}
      </span><span className="max-w-full break-words text-[10px] font-medium sm:text-xs">{labels[index]}</span>
    </button>)}
  </nav>
}
