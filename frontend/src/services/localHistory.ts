import { z } from 'zod'
import { VERDICT_KEYS } from '@/constants/verdicts'
import type { VerificationResult } from '@/types/verification'

export const LOCAL_HISTORY_KEY = 'researchguard:demo:history:v1'
const verdict = z.enum(VERDICT_KEYS)
const identifier = z.string().refine((value) => Boolean(value.trim()))
const percentage = z.number().finite().min(0).max(100)
const strings = z.array(z.string())
const agent = z.object({
  role: z.string(), summary: z.string(), finding: z.string(),
  status: z.enum(['completed', 'running', 'idle']),
}).passthrough()
const detail = z.object({
  analysis: z.string(), stance: z.string().optional(), confidence: percentage.optional(),
  keyPoints: strings, supportingEvidence: strings, contradictingEvidence: strings,
}).passthrough()
const evidence = z.object({
  id: identifier, title: z.string(), source: z.string(), excerpt: z.string(),
  relevance: z.number().finite(), evidenceType: z.string(),
  authors: z.string().optional(), year: z.number().int().optional(),
  whyItMatters: z.string().optional(), claimOverlap: z.number().finite().optional(),
  numericOverlap: z.number().finite().optional(),
  strength: z.enum(['HIGH', 'MEDIUM', 'LOW']).optional(),
  identifier: z.string().optional(), sourceUrl: z.string().optional(),
  page: z.number().int().nullable().optional(), chunkIndex: z.number().int().optional(),
  verdict: verdict.optional(),
}).passthrough()

// Validate the actual report contract, including nested values rendered by React.
// No coercion, defaults, invented evidence or fallback scientific verdicts.
const reportSchema = z.object({
  id: identifier, claim: identifier, citation: identifier,
  sourceType: z.enum(['doi', 'url', 'citation', 'reference']),
  citationStatus: z.enum(['verified', 'fabricated', 'unverified']),
  verdict, confidence: percentage, summary: z.string(), reasoning: z.string(),
  createdAt: z.iso.datetime({ offset: true }),
  context: z.string().optional(), paperTitle: z.string().optional(), paperDoi: z.string().optional(),
  agentAgreement: z.boolean().nullable().optional(), validationWarnings: strings.optional(),
  evidenceFactors: z.array(z.object({ text: z.string(), supported: z.boolean() })),
  prosecutor: agent, defender: agent, adjudicator: agent,
  prosecutorDetail: detail.optional(), defenderDetail: detail.optional(),
  adjudicatorDetail: detail.extend({
    verdict: verdict.optional(), reasoning: z.string().optional(),
    suggestedCorrection: z.string().nullable().optional(),
  }).optional(),
  evidence: z.array(evidence),
  suggestedCorrection: z.object({
    originalClaim: z.string(), problem: z.string(), suggestedWording: z.string(),
  }).nullable().optional(),
  claimTraceability: z.object({
    segments: z.array(z.object({
      id: identifier, text: z.string(),
      status: z.enum(['SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED', 'CONTRADICTED']),
      coverageScore: percentage, evidenceIds: strings,
    })),
    overallCoverage: percentage, warnings: strings.optional(),
  }).optional(),
}).passthrough()

export interface LocalHistoryRead {
  records: VerificationResult[]
  warning: string | null
}

function newestFirst(records: VerificationResult[]): VerificationResult[] {
  return records.sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt))
}

export function readLocalHistory(forMutation = false): LocalHistoryRead {
  let raw: string | null
  try {
    raw = window.localStorage.getItem(LOCAL_HISTORY_KEY)
  } catch (error) {
    if (forMutation) throw error
    return { records: [], warning: 'Local history is unavailable in this browser. Reports can still be viewed during this session.' }
  }
  if (raw === null) return { records: [], warning: null }

  let envelope: unknown
  try {
    envelope = JSON.parse(raw)
  } catch {
    if (forMutation) throw new Error('Invalid local history must be cleared before saving or deleting records.')
    return { records: [], warning: 'Local history could not be read. The stored data is invalid.' }
  }
  const parsed = z.object({ version: z.literal(1), records: z.array(z.unknown()) }).safeParse(envelope)
  if (!parsed.success) {
    if (forMutation) throw new Error('Unsupported local history must be cleared before saving or deleting records.')
    return { records: [], warning: 'Local history could not be read. Its format or version is unsupported.' }
  }

  const records = new Map<string, VerificationResult>()
  let skipped = false
  for (const rawRecord of parsed.data.records) {
    if (!reportSchema.safeParse(rawRecord).success) {
      skipped = true
      continue
    }
    // Preserve the complete original report after validation, without rewriting it.
    const record = rawRecord as VerificationResult
    const previous = records.get(record.id)
    if (!previous || Date.parse(record.createdAt) > Date.parse(previous.createdAt)) {
      records.set(record.id, record)
    }
  }
  return {
    records: newestFirst([...records.values()]),
    warning: skipped ? 'Some local history records could not be loaded.' : null,
  }
}

function writeLocalHistory(records: VerificationResult[]): void {
  window.localStorage.setItem(LOCAL_HISTORY_KEY, JSON.stringify({ version: 1, records }))
}

export function saveLocalHistory(result: VerificationResult): void {
  if (!reportSchema.safeParse(result).success) {
    throw new Error('This report could not be saved locally because its format is invalid.')
  }
  const { records } = readLocalHistory(true)
  writeLocalHistory(newestFirst([result, ...records.filter((record) => record.id !== result.id)]))
}

export function deleteLocalHistory(recordId: string): void {
  const { records } = readLocalHistory(true)
  writeLocalHistory(records.filter((record) => record.id !== recordId))
}
