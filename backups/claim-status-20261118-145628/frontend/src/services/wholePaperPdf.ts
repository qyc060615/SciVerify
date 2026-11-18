import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { ReportExportSnapshot } from '@/components/manuscript/ReportExportSnapshot'
import { codePointSlice } from '@/services/manuscriptBridge'
import type { VerificationJob } from '@/types/verification-job'

// Isolated document: no application styles, clipped scroll areas, or live controls.
export function buildWholePaperPrintDocument(job: VerificationJob, fileLabel?: string): Document {
  const doc = new DOMParser().parseFromString('<!doctype html><html lang="en"><head><meta charset="utf-8"></head><body></body></html>', 'text/html')
  doc.title = (fileLabel?.replace(/\.pdf$/i, '') || 'Whole-paper-' + job.job_id.slice(0, 16)) + '-verification-report'
  const style = doc.createElement('style')
  style.textContent = `
    @page { size: A4; margin: 18mm 16mm; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #172b3a; background: white; font: 10pt/1.55 Arial, "Microsoft YaHei", sans-serif; overflow-wrap: anywhere; }
    header { border-bottom: 3px solid #167d92; padding-bottom: 14pt; margin-bottom: 18pt; }
    header p { color: #536575; font-size: 9pt; }
    h1 { font-size: 23pt; margin: 0 0 6pt; }
    h2 { font-size: 14pt; margin: 12pt 0 8pt; color: #14697c; }
    [data-testid="pair-card"] { margin-top: 24pt; }
    h3 { font-size: 11pt; margin: 10pt 0 6pt; }
    h1, h2, h3, summary { break-after: avoid; }
    p { margin: 5pt 0; orphans: 3; widows: 3; }
    article { border-top: 1px solid #cbd5df; padding-top: 9pt; margin-top: 12pt; }
    details { margin-top: 10pt; }
    summary { font-weight: bold; color: #36566a; list-style: none; }
    summary::-webkit-details-marker { display: none; }
    blockquote { margin: 9pt 0; padding: 8pt 12pt; border-left: 3px solid #167d92; background: #f3f7f9; white-space: pre-wrap; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; font: 8pt/1.45 Consolas, monospace; padding: 8pt; background: #f5f7f9; }
    a { color: #14697c; text-decoration: underline; margin-right: 5pt; }
    a[href^="http"]::after { content: " (" attr(href) ")"; font-size: 8pt; }
    [aria-label="Selected claim details"] { break-before: page; }
    [aria-label="Reference list"] article { padding-bottom: 8pt; }
    main > div > details { break-before: page; }
    progress { display: none; }
    span { margin-right: 5pt; }
    .whitespace-pre-wrap { white-space: pre-wrap; }
    * { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  `
  doc.head.append(style)
  const header = doc.createElement('header')
  const title = doc.createElement('h1')
  title.textContent = 'Whole-paper verification report'
  const subtitle = doc.createElement('p')
  subtitle.textContent = `${fileLabel || 'Saved manuscript'} | Exported ${new Date().toLocaleString()}`
  const note = doc.createElement('p')
  note.textContent = 'Original manuscript passages, verification conclusions and evidence from the cited references. Confidence describes the verification result, not the probability that a statement is true. Incomplete checks are not scientific verdicts.'
  header.append(title, subtitle, note)
  const main = doc.createElement('main')
  main.innerHTML = renderToStaticMarkup(createElement(ReportExportSnapshot, { job, fileLabel, printMode: true }))
  // Keep the existing cover/overview, but build the body from an explicit reader-facing schema.
  const overview = main.firstElementChild?.firstElementChild
  main.replaceChildren(...(overview ? [overview] : []))
  const body = doc.createElement('section')
  body.setAttribute('data-report-body', '')
  function add(parent: Element, tag: string, text: string) {
    const element = doc.createElement(tag)
    element.textContent = text
    parent.append(element)
    return element
  }
  function safeLink(value: string | null | undefined) {
    try {
      const url = new URL(value ?? '')
      return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : undefined
    } catch { return undefined }
  }
  const paragraphs = new Map(job.paragraphs.map(item => [item.id, item]))
  const claims = [...job.claims].sort((a, b) => (paragraphs.get(a.paragraph_id)?.order ?? 0) - (paragraphs.get(b.paragraph_id)?.order ?? 0) || (a.source_spans[0]?.start ?? 0) - (b.source_spans[0]?.start ?? 0))
  claims.forEach((claim, index) => {
    const article = doc.createElement('article')
    article.setAttribute('aria-label', 'Selected claim details')
    add(article, 'h2', `Claim ${String(index + 1).padStart(2, '0')}`)
    const paragraph = paragraphs.get(claim.paragraph_id)
    const original = paragraph && claim.source_spans.map(span => codePointSlice(paragraph.text, span.start, span.end)).filter(text => text.trim()).join(' ... ')
    add(article, 'blockquote', original || claim.text)
    const tasks = job.tasks.filter(task => task.claim_id === claim.id)
    if (!tasks.length) {
      add(article, 'p', 'Confidence: unavailable. No reference check was completed.')
      add(article, 'p', 'Related content: no linked reference evidence available.')
      add(article, 'p', 'URL: unavailable')
    }
    tasks.forEach((task, referenceIndex) => {
      const pair = doc.createElement('div')
      pair.setAttribute('data-testid', 'pair-card')
      const reference = job.references.find(item => item.id === task.reference_id)
      const result = task.pair_outcome?.verification
      const completed = task.state === 'completed' && result?.processing_status === 'completed'
      const confidence = result?.confidence
      add(pair, 'h3', `Reference ${referenceIndex + 1}: ` + (reference?.title || reference?.raw_text || 'Untitled reference'))
      add(pair, 'p', completed && typeof confidence === 'number' && Number.isFinite(confidence) && confidence >= 0 && confidence <= 1
        ? `Confidence: ${(confidence * 100).toFixed(0)}%`
        : 'Confidence: unavailable' + (completed ? '.' : ' - verification incomplete.'))
      const provenance = task.source_binding?.provenance
      const fallback = [provenance?.final_url, provenance?.source_url, task.source_binding?.locator?.value,
        reference?.url, reference?.resolution?.source_url, reference?.doi ? 'https://doi.org/' + reference.doi : null].map(safeLink).find(Boolean)
      const seen = new Set<string>()
      const chunks = (result?.evidence_chunks ?? []).filter(chunk => {
        const key = chunk.text.replace(/\s+/g, ' ').trim()
        if (!key || seen.has(key)) return false
        seen.add(key)
        return true
      })
      const urls = new Set<string>()
      chunks.forEach(chunk => {
        add(pair, 'blockquote', chunk.text)
        const url = safeLink(chunk.source_url) || fallback
        if (url && !urls.has(url)) {
          urls.add(url)
          const link = add(pair, 'a', 'URL: ' + url)
          link.setAttribute('href', url)
        }
      })
      if (!chunks.length) {
        add(pair, 'p', 'Related content: no reference passage available.')
        if (fallback) {
          const link = add(pair, 'a', 'URL: ' + fallback)
          link.setAttribute('href', fallback)
        }
      }
      if (!urls.size && !fallback) add(pair, 'p', 'URL: unavailable')
      article.append(pair)
    })
    body.append(article)
  })
  if (!claims.length) add(body, 'p', 'No accepted claims in this snapshot.')
  main.append(body)
  main.querySelectorAll('button, input, select, textarea').forEach(element => element.remove())
  doc.body.append(header, main)
  return doc
}

export interface ReportBlock { kind: 'title' | 'heading' | 'subheading' | 'body' | 'quote' | 'code' | 'pagebreak'; text: string }

export function buildWholePaperExportBlocks(job: VerificationJob, fileLabel?: string): { title: string; blocks: ReportBlock[] } {
  const doc = buildWholePaperPrintDocument(job, fileLabel)
  const blocks: ReportBlock[] = []
  function textOf(element: Element): string {
    if (element.tagName === 'PRE' || element.tagName === 'BLOCKQUOTE') return element.textContent ?? ''
    return Array.from(element.childNodes).map(node => node.nodeType === Node.ELEMENT_NODE
      ? textOf(node as Element) : node.textContent ?? '').join(' ').replace(/\s+/g, ' ').trim()
  }
  // Source links remain readable in both formats without fetching external content.
  doc.querySelectorAll('a[href^="http"]').forEach(link => { if (!link.textContent?.includes(link.getAttribute('href')!)) link.append(' (' + link.getAttribute('href') + ')') })
  const kinds: Record<string, ReportBlock['kind']> = { H1: 'title', H2: 'heading', H3: 'subheading', SUMMARY: 'subheading', P: 'body', BLOCKQUOTE: 'quote', PRE: 'code', LI: 'body' }
  function visit(node: Node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent?.trim()
      if (text) blocks.push({ kind: 'body', text })
      return
    }
    if (node.nodeType !== Node.ELEMENT_NODE) return
    const element = node as Element
    if (element.tagName === 'PROGRESS') return
    if (element.matches('[aria-label="Selected claim details"]') || (element.matches('[data-report-body]') && !element.querySelector('article'))) blocks.push({ kind: 'pagebreak', text: '' })
    const kind = kinds[element.tagName]
    if (kind) {
      const text = textOf(element)
      if (text) blocks.push({ kind, text })
    } else if (element.tagName === 'SPAN' || element.tagName === 'A') {
      const text = textOf(element)
      if (text) blocks.push({ kind: 'body', text })
    } else element.childNodes.forEach(visit)
  }
  visit(doc.body)
  return { title: doc.title, blocks }
}

export async function generateWholePaperFile(job: VerificationJob, format: 'pdf' | 'docx', fileLabel?: string, includeAnalysis = false): Promise<Blob> {
  const { apiClient } = await import('./api')
  const document = buildWholePaperExportBlocks(job, fileLabel)
  try {
    const response = await apiClient.post<Blob>(`/api/verification/jobs/${encodeURIComponent(job.job_id)}/export`,
      { format, ...document, simplify_evidence: includeAnalysis }, { timeout: includeAnalysis ? 210000 : 30000, responseType: 'blob' })
    return response.data
  } catch (error) {
    const failure = error as { status?: number; data?: unknown; message?: string }
    let detail: { code?: string; message?: string } | undefined
    try {
      const data = failure.data instanceof Blob ? JSON.parse(await failure.data.text()) : failure.data
      detail = (data as { detail?: {code?: string; message?: string} })?.detail
    } catch { /* Preserve a readable fallback for non-JSON server errors. */ }
    if (detail?.code === 'REPORT_EDITING_FAILED') throw new Error('AI analysis could not be completed or its quotations could not be verified. Retry, or uncheck Include AI analysis in export to export the saved evidence without AI.')
    if (detail?.code === 'REPORT_EXPORT_UNAVAILABLE') throw new Error('PDF/Word export dependencies are missing in the running backend. Install backend/requirements.txt and restart the backend.')
    if (failure.status === 404) throw new Error('The saved report or export endpoint was not found. Check that the backend is running from SciVerify1 and reopen the saved report.')
    if (detail?.message) throw new Error(detail.message)
    throw new Error(failure.message || 'Report generation failed. Check the backend connection and retry.')
  }
}
