import { extractDoi } from '@/lib/doi'
import { getSupabaseClient, isSupabaseConfigured } from '@/lib/supabase'
import type {
  VerificationHistoryInsert,
  VerificationHistoryRow,
} from '@/types/history'
import type { VerificationResult } from '@/types/verification'

import { VERDICT_KEYS, type VerdictKey } from '@/constants/verdicts'
import { isLocalDemoMode } from '@/lib/demo-mode'
import { readLocalHistory, saveLocalHistory, deleteLocalHistory } from '@/services/localHistory'

const GENERIC_HISTORY_ERROR = 'Unable to access verification history.'

function resolveVerdict(rawVerdict: unknown): VerdictKey {
  if (typeof rawVerdict === 'string') {
    const upper = rawVerdict.trim().toUpperCase()
    if ((VERDICT_KEYS as readonly string[]).includes(upper)) {
      return upper as VerdictKey
    }
  }
  return 'INSUFFICIENT'
}

function resolveDoi(result: VerificationResult): string {
  if (result.paperDoi?.trim()) {
    return result.paperDoi.trim()
  }

  try {
    return extractDoi(result.citation)
  } catch {
    return result.citation.trim().slice(0, 255) || 'unknown'
  }
}

function toInsertRow(
  userId: string,
  result: VerificationResult,
): VerificationHistoryInsert {
  return {
    id: result.id,
    user_id: userId,
    claim: result.claim,
    doi: resolveDoi(result),
    paper_title: result.paperTitle ?? null,
    verdict: result.verdict,
    confidence: result.confidence,
    summary: result.summary,
    result_json: result,
    created_at: result.createdAt,
  }
}

function rebuildMinimalResult(row: VerificationHistoryRow): VerificationResult {
  const verdict = resolveVerdict(row.verdict)
  return {
    id: row.id,
    claim: row.claim || 'Unspecified claim',
    citation: row.doi || 'Unknown citation',
    sourceType: 'doi',
    citationStatus: verdict === 'FABRICATED' ? 'fabricated' : 'verified',
    verdict,
    confidence: Number(row.confidence) || 0,
    summary: row.summary ?? 'Verification summary unavailable.',
    reasoning: row.summary ?? 'Verification reasoning unavailable.',
    paperTitle: row.paper_title ?? undefined,
    paperDoi: row.doi,
    // Explicitly null so VerdictHeader renders "Agreement information unavailable"
    // rather than breaking on an undefined value.
    agentAgreement: null,
    validationWarnings: [],
    evidenceFactors: [],
    prosecutor: {
      role: 'Prosecutor',
      summary: 'Analysis unavailable.',
      finding: 'Stored report did not include agent details.',
      status: 'completed',
    },
    defender: {
      role: 'Defender',
      summary: 'Analysis unavailable.',
      finding: 'Stored report did not include agent details.',
      status: 'completed',
    },
    adjudicator: {
      role: 'Adjudicator',
      summary: 'Analysis unavailable.',
      finding: 'Stored report did not include agent details.',
      status: 'completed',
    },
    evidence: [],
    suggestedCorrection: null,
    createdAt: row.created_at || new Date().toISOString(),
  }
}

export function parseStoredVerificationResult(
  row: VerificationHistoryRow,
): VerificationResult {
  const raw = row.result_json

  if (raw && typeof raw === 'object' && 'claim' in raw && 'verdict' in raw) {
    const rawResult = raw as VerificationResult
    return {
      ...rawResult,
      id: row.id || rawResult.id,
      verdict: resolveVerdict(rawResult.verdict ?? row.verdict),
      confidence:
        typeof rawResult.confidence === 'number'
          ? rawResult.confidence
          : Number(row.confidence) || 0,
      createdAt:
        row.created_at || rawResult.createdAt || new Date().toISOString(),
      paperTitle:
        rawResult.paperTitle ?? row.paper_title ?? undefined,
      paperDoi: rawResult.paperDoi ?? row.doi,
      agentAgreement: rawResult.agentAgreement ?? null,
      validationWarnings: Array.isArray(rawResult.validationWarnings)
        ? rawResult.validationWarnings
        : [],
      evidenceFactors: Array.isArray(rawResult.evidenceFactors)
        ? rawResult.evidenceFactors
        : [],
      evidence: Array.isArray(rawResult.evidence)
        ? rawResult.evidence
        : [],
    }
  }

  return rebuildMinimalResult(row)
}

export async function saveVerificationHistory(
  userId: string,
  result: VerificationResult,
): Promise<void> {
  if (isLocalDemoMode()) {
    saveLocalHistory(result)
    return
  }
  if (!isSupabaseConfigured()) {
    throw new Error(GENERIC_HISTORY_ERROR)
  }

  const { error } = await getSupabaseClient()
    .from('verification_history')
    .upsert(toInsertRow(userId, result), { onConflict: 'id' })

  if (error) {
    throw new Error(GENERIC_HISTORY_ERROR)
  }
}

export async function listVerificationHistory(
  userId: string,
  onWarning?: (warning: string | null) => void,
): Promise<VerificationResult[]> {
  if (isLocalDemoMode()) {
    const { records, warning } = readLocalHistory()
    onWarning?.(warning)
    return records
  }
  if (!isSupabaseConfigured()) {
    throw new Error(GENERIC_HISTORY_ERROR)
  }

  const { data, error } = await getSupabaseClient()
    .from('verification_history')
    .select('*')
    .eq('user_id', userId)
    .order('created_at', { ascending: false })

  if (error) {
    throw new Error(GENERIC_HISTORY_ERROR)
  }

  return (data as VerificationHistoryRow[]).map(parseStoredVerificationResult)
}

export async function deleteVerificationHistory(
  userId: string,
  recordId: string,
): Promise<void> {
  if (isLocalDemoMode()) {
    deleteLocalHistory(recordId)
    return
  }
  if (!isSupabaseConfigured()) {
    throw new Error(GENERIC_HISTORY_ERROR)
  }

  const { error } = await getSupabaseClient()
    .from('verification_history')
    .delete()
    .eq('user_id', userId)
    .eq('id', recordId)

  if (error) {
    throw new Error(GENERIC_HISTORY_ERROR)
  }
}
