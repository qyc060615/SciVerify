import { useId } from 'react'
import { FileText, Upload } from 'lucide-react'

export function PdfPicker({ label, file, disabled, onChange }: { label: string; file: File | null; disabled?: boolean; onChange: (file: File | null) => void }) {
  const id = useId()
  return <div className="min-w-0">
    <input id={id} aria-label={label} className="peer sr-only" type="file" accept="application/pdf,.pdf" disabled={disabled}
      onChange={event => onChange(event.target.files?.[0] ?? null)} />
    <label htmlFor={id} onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); if (!disabled) onChange(event.dataTransfer.files[0] ?? null) }}
      className={'flex min-w-0 cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-border px-4 py-6 text-center peer-focus-visible:ring-2 peer-focus-visible:ring-primary ' + (disabled ? 'pointer-events-none opacity-60' : 'hover:border-primary/50 hover:bg-primary-muted/20')}>
      {file ? <FileText className="h-6 w-6 text-primary" /> : <Upload className="h-6 w-6 text-text-muted" />}
      <span className="max-w-full break-all text-sm font-medium">{file?.name ?? 'Choose a PDF or drop it here'}</span>
      <span className="text-xs text-text-muted">{file ? (file.size / 1024 / 1024).toFixed(2) + ' MB · Click to change' : label}</span>
    </label>
  </div>
}
