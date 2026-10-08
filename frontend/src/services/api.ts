import axios from 'axios'
import { env } from '@/lib/env'
import type { VerificationApiErrorBody } from '@/types/backend-verification'

function formatDetail(detail: VerificationApiErrorBody['detail']): string | null {
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    return detail.message
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item) => item.msg)
      .filter(Boolean)
      .join(', ')
  }

  return null
}

function formatApiError(error: unknown): string {
  if (!axios.isAxiosError<VerificationApiErrorBody>(error)) {
    return error instanceof Error
      ? error.message
      : 'An unexpected error occurred'
  }

  if (!error.response) {
    return 'Unable to connect to the SciVerify backend. Please make sure the backend server is running.'
  }

  const status = error.response.status
  const detail = formatDetail(error.response.data?.detail)

  if (status === 422) {
    return detail ?? 'Please provide a valid claim and DOI.'
  }

  if (status === 429) {
    return 'The AI verification service is temporarily rate limited. Please try again later.'
  }

  if (status === 404) {
    return (
      detail ??
      'The cited paper could not be found. Please check the DOI and try again.'
    )
  }

  if (status === 503) {
    const lowerDetail = detail?.toLowerCase() ?? ''
    if (
      lowerDetail.includes('full text') ||
      lowerDetail.includes('unavailable') ||
      lowerDetail.includes('open access')
    ) {
      return (
        'Citation found, but the full text could not be retrieved from any permitted open-access source. ' +
        'The paper may require a subscription or is not yet deposited in an open repository.'
      )
    }
    return detail ?? "The cited paper's full text could not be retrieved."
  }

  if (status >= 500) {
    return detail ?? 'The verification service encountered an unexpected error. Please try again later.'
  }

  return detail ?? error.message ?? 'An unexpected error occurred'
}

export const apiClient = axios.create({
  baseURL: env.apiBaseUrl || undefined,
  headers: {
    'Content-Type': 'application/json',
  },
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(new Error(formatApiError(error))),
)
