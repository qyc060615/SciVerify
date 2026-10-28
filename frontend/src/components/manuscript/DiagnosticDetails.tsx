import type { ReactNode } from 'react'
import type { Diagnostic } from '@/types/manuscript'

export function DiagnosticDetails({ records, label = 'diagnostics', children }: { records: Diagnostic[]; label?: string; children?: ReactNode }) {
  const counts = new Map<string, number>()
  records.forEach(record => counts.set(record.code, (counts.get(record.code) ?? 0) + 1))
  if (!records.length && !children) return null
  return <details className="min-w-0 text-sm">
    <summary className="cursor-pointer text-text-secondary">{records.length} {label} · View details</summary>
    <div className="mt-3 space-y-3 border-l border-border pl-3">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">{[...counts].map(([code, count]) => <span className="break-all" key={code}>{code} × {count}</span>)}</div>
      <details><summary className="cursor-pointer text-xs text-primary">Original diagnostic records</summary><ul className="mt-2 space-y-2">{records.map((record, index) => <li key={index} className="break-words text-xs [overflow-wrap:anywhere]">{record.code}: {record.safe_message}{record.entity_id ? ' · ' + record.entity_id : ''}</li>)}</ul></details>
      {children}
    </div>
  </details>
}
