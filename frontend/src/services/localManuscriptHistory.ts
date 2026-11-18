const historyKey = 'researchguard-recent-jobs'
const jobIdPattern = /^job_[0-9a-f]{32}$/

interface ManuscriptHistoryEntry {
  id: string
  fileName?: string
}

export function readManuscriptHistory(): ManuscriptHistoryEntry[] {
  const stored: unknown = JSON.parse(localStorage.getItem(historyKey) ?? '[]')
  if (!Array.isArray(stored)) throw new Error('Invalid manuscript history')

  const entries = new Map<string, ManuscriptHistoryEntry>()
  for (const item of stored as unknown[]) {
    const entry = item && typeof item === 'object' ? item as Partial<Record<'id' | 'fileName', unknown>> : null
    const id = typeof item === 'string' ? item : entry?.id
    if (typeof id !== 'string' || !jobIdPattern.test(id) || entries.has(id)) continue
    const fileName = typeof entry?.fileName === 'string' ? entry.fileName : undefined
    entries.set(id, { id, fileName })
  }
  return [...entries.values()]
}

export function rememberManuscriptJob(id: string, fileName?: string): void {
  const entries = readManuscriptHistory()
  const previous = entries.find(entry => entry.id === id)
  localStorage.setItem(historyKey, JSON.stringify([
    { id, fileName: fileName ?? previous?.fileName },
    ...entries.filter(entry => entry.id !== id),
  ]))
}
