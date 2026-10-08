import axios from 'axios'
import { extractDoi, InvalidDoiError } from '@/lib/doi'
import { apiClient } from '@/services/api'
import {
  mapBackendVerificationToResult,
  mapInsufficientEvidenceResult,
} from '@/services/verificationMapper'
import type {
  BackendVerificationResponse,
  VerificationAnalyzeRequest,
  VerificationApiErrorBody,
} from '@/types/backend-verification'
import type { VerificationFormInput, VerificationResult } from '@/types/verification'

export class VerificationServiceError extends Error {
  status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'VerificationServiceError'
    this.status = status
  }
}

export class SourceRequiredError extends VerificationServiceError {
  response: BackendVerificationResponse

  constructor(response: BackendVerificationResponse) {
    super('The cited paper could not be retrieved automatically.')
    this.name = 'SourceRequiredError'
    this.response = response
  }
}

export async function uploadManualSource(doi: string, file: File): Promise<void> {
  const form = new FormData()
  form.append('doi', doi)
  form.append('file', file)
  try {
    await apiClient.post('/api/sources/manual', form, {
      headers: { 'Content-Type': undefined },
    })
  } catch (error) {
    throw parseApiError(error)
  }
}

function parseApiError(error: unknown): VerificationServiceError {
  if (error instanceof VerificationServiceError) {
    return error
  }

  if (error instanceof InvalidDoiError) {
    return new VerificationServiceError(error.message, 400)
  }

  if (axios.isAxiosError<VerificationApiErrorBody>(error)) {
    if (!error.response) {
      return new VerificationServiceError(
        'Unable to connect to the SciVerify backend. Please make sure the backend server is running.',
      )
    }

    const status = error.response.status
    const detail = error.response.data?.detail
    const detailText =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg).filter(Boolean).join(', ')
          : undefined

    if (status === 422) {
      return new VerificationServiceError(
        detailText ?? 'Please provide a valid claim and DOI.',
        status,
      )
    }

    if (status === 429) {
      return new VerificationServiceError(
        'The AI verification service is temporarily rate limited. Please try again later.',
        status,
      )
    }

    if (status === 400) {
      const message = detailText ?? 'Please provide a valid DOI and claim.'
      return new VerificationServiceError(message, status)
    }

    if (status === 404) {
      return new VerificationServiceError(
        detailText ?? 'The cited paper could not be found.',
        status,
      )
    }

    if (status === 503) {
      if (detailText?.toLowerCase().includes('full text')) {
        return new VerificationServiceError(
          'Full text could not be retrieved from the available sources. Please try another paper.',
          status,
        )
      }
      const message =
        detailText ?? "The cited paper's full text could not be retrieved."
      return new VerificationServiceError(message, status)
    }

    const fallback = detailText ?? 'Verification could not be completed.'
    return new VerificationServiceError(fallback, status)
  }

  if (error instanceof Error) {
    return new VerificationServiceError(error.message)
  }

  return new VerificationServiceError('Verification could not be completed.')
}

function buildRequest(input: VerificationFormInput): VerificationAnalyzeRequest {
  const doi = extractDoi(input.citation)
  return {
    claim: input.claim.trim(),
    doi,
  }
}

function handleApplicationStatus(
  response: BackendVerificationResponse,
  input: VerificationFormInput,
): VerificationResult {
  if (response.status === 'source_required') {
    throw new SourceRequiredError(response)
  }

  if (response.status === 'insufficient_evidence') {
    return mapInsufficientEvidenceResult(response, input)
  }

  if (response.status === 'llm_unavailable') {
    throw new VerificationServiceError(
      response.detail ??
        'The AI verification service is temporarily unavailable. Please try again later.',
      503,
    )
  }

  if (response.status === 'verification_failed') {
    const detail = response.detail ?? ''
    const isRateLimit =
      detail.includes('429') ||
      detail.toLowerCase().includes('rate limit') ||
      detail.toLowerCase().includes('quota')
    if (isRateLimit) {
      throw new VerificationServiceError(
        detail ||
          'The AI verification service is temporarily rate limited. Please try again later.',
        429,
      )
    }
    throw new VerificationServiceError(
      detail || 'Verification could not be completed.',
      500,
    )
  }

  if (response.status !== 'success') {
    throw new VerificationServiceError(
      response.detail ?? 'Verification could not be completed.',
      500,
    )
  }

  if (!response.verdict) {
    throw new VerificationServiceError(
      'Verification completed without a final verdict.',
      500,
    )
  }

  return mapBackendVerificationToResult(response, input)
}

export async function verifyCitation(
  input: VerificationFormInput,
): Promise<VerificationResult> {
  const request = buildRequest(input)

  try {
    const { data } = await apiClient.post<BackendVerificationResponse>(
      '/api/verification/analyze',
      request,
    )

    return handleApplicationStatus(data, input)
  } catch (error) {
    throw parseApiError(error)
  }
}

export { extractDoi, InvalidDoiError }
