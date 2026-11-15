/** Preserve structured HTTP errors for stage-aware services without exposing them in UI. */
export class ApiResponseError extends Error {
  readonly status?: number
  readonly data?: unknown
  constructor(message: string, status?: number, data?: unknown) {
    super(message)
    this.name = 'ApiResponseError'
    this.status = status
    this.data = data
  }
}
