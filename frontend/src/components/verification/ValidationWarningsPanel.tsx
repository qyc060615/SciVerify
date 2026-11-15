import { AlertTriangle } from 'lucide-react'
import { Panel } from '@/components/ui/Card'

export interface ValidationWarningsPanelProps {
  warnings: string[]
}

export function ValidationWarningsPanel({ warnings }: ValidationWarningsPanelProps) {
  if (warnings.length === 0) return null

  return (
    <Panel padding="md" className="space-y-3 border-warning/30 bg-warning/5">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 shrink-0 text-warning" aria-hidden />
        <h3 className="text-sm font-semibold text-text-primary">Validation notes</h3>
      </div>
      <ul className="space-y-2" role="list">
        {warnings.map((warning) => (
          <li
            key={warning}
            className="flex items-start gap-2 text-sm leading-relaxed text-text-secondary"
          >
            <span className="text-warning" aria-hidden>
              ⚠
            </span>
            <span>{warning}</span>
          </li>
        ))}
      </ul>
    </Panel>
  )
}
