export type ReportFormat = 'pdf' | 'docx'
interface SaveHandle { createWritable(): Promise<{ write(data: Blob): Promise<void>; close(): Promise<void>; abort(): Promise<void> }> }
interface SavePickerWindow extends Window {
  showSaveFilePicker?: (options: { suggestedName: string; excludeAcceptAllOption: boolean; types: { description: string; accept: Record<string, string[]> }[] }) => Promise<SaveHandle>
}
export interface ReportDestination { downloadFallback: boolean; save(blob: Blob): Promise<void> }

// Call directly from the click handler, before any imports/network requests:
// browsers require user activation to open the native Save As dialog.
export async function chooseReportDestination(format: ReportFormat, name: string): Promise<ReportDestination | null> {
  const stem = name.replace(/\.(pdf|docx)$/i, '').replace(/[<>:"/\\|?*]/g, '_').split('').map(character => character.charCodeAt(0) < 32 ? '_' : character).join('').replace(/[. ]+$/, '').slice(0, 160) || 'Whole-paper'
  const filename = stem + '-verification-report.' + format
  const mime = format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  const picker = (window as SavePickerWindow).showSaveFilePicker
  if (picker) {
    let handle: SaveHandle
    try {
      handle = await picker.call(window, { suggestedName: filename, excludeAcceptAllOption: true,
        types: [{ description: format === 'pdf' ? 'PDF report' : 'Word document', accept: { [mime]: ['.' + format] } }] })
    } catch (error) {
      if (error && typeof error === 'object' && 'name' in error && error.name === 'AbortError') return null
      throw error
    }
    return { downloadFallback: false, async save(blob) {
      const stream = await handle.createWritable()
      try { await stream.write(blob); await stream.close() }
      catch (error) { await stream.abort().catch(() => {}); throw error }
    } }
  }
  return { downloadFallback: true, async save(blob) {
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.append(link)
    try { link.click() } finally {
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(url), 60000)
    }
  } }
}
