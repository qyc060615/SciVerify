import { useRef, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Modal } from '@/components/ui/Modal'
import { chooseReportDestination, type ReportFormat } from '@/services/reportFileSave'
import type { VerificationJob } from '@/types/verification-job'
export function ReportExportControls({job, fileLabel}: {job: VerificationJob; fileLabel?: string}) {
  const [includeAnalysis, setIncludeAnalysis] = useState(false)
  const [confirmAnalysis, setConfirmAnalysis] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportStage, setExportStage] = useState('')
  const [exportError, setExportError] = useState('')
  const [exportNotice, setExportNotice] = useState('')
  const [exportFormat, setExportFormat] = useState<ReportFormat>('pdf')
  const exportActive = useRef(false)
  async function exportReport() {
    if (exportActive.current) return
    exportActive.current = true
    setExporting(true)
    setExportStage('Choose a save location in the Save As dialog. It may be behind this window.')
    setExportError('')
    setExportNotice('')
    try {
      const destination = await chooseReportDestination(exportFormat, fileLabel || 'Whole-paper-' + job.job_id.slice(0, 16))
      if (!destination) return
      setExportStage(includeAnalysis ? 'Preparing quotations and AI analysis. This can take up to 3 minutes.' : 'Generating the report from saved evidence. No AI processing is required.')
      const { generateWholePaperFile } = await import('@/services/wholePaperPdf')
      const file = await generateWholePaperFile(job, exportFormat, fileLabel, includeAnalysis)
      setExportStage('Saving the report to the selected location...')
      await destination.save(file)
      setExportNotice(destination.downloadFallback
        ? 'Report downloaded. To choose a folder, enable Ask where to save each file in your browser download settings.'
        : 'Report saved to the selected location.')
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'The report could not be saved. Please try again.')
    } finally {
      exportActive.current = false
      setExporting(false)
      setExportStage('')
    }
  }
  return (
    <div className="flex flex-col items-end gap-2">
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={includeAnalysis} disabled={exporting} onChange={event => setIncludeAnalysis(event.target.checked)} /><span>Include AI analysis in export</span></label>
      <div className="flex items-center gap-2">
        <select aria-label="Report file format" className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary" value={exportFormat} disabled={exporting} onChange={event => setExportFormat(event.target.value as ReportFormat)}>
          <option value="pdf">PDF (.pdf)</option><option value="docx">Word (.docx)</option>
        </select>
        <Button variant="outline" loading={exporting} onClick={() => includeAnalysis ? setConfirmAnalysis(true) : void exportReport()}><span>{exporting ? (includeAnalysis ? 'Preparing readable report...' : 'Exporting report...') : 'Export report'}</span></Button>
      </div>
      <Modal open={confirmAnalysis} onClose={() => setConfirmAnalysis(false)} title="Export with AI analysis" description="AI will select quotations and generate analysis. This may take up to 3 minutes. Keep this page open until the report is saved." size="sm">
        <div className="flex justify-end gap-2"><Button variant="outline" onClick={() => setConfirmAnalysis(false)}>Cancel</Button><Button onClick={() => { setConfirmAnalysis(false); void exportReport() }}>Continue export</Button></div>
      </Modal>
      {exporting && <p role="status" className="text-sm text-text-secondary">{exportStage}</p>}
      {exportNotice && <p role="status" className="text-sm text-text-secondary">{exportNotice}</p>}
      {exportError && <p role="alert" className="text-sm text-danger">{exportError}</p>}
    </div>  )
}
