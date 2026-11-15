import { expect, it } from 'vitest'
import { ApiResponseError } from '@/services/ApiResponseError'
import { wholePaperError } from '@/services/wholePaperErrors'

it.each([
  ['GROBID_UNAVAILABLE', 503, 'publish its port'],
  ['GROBID_TIMEOUT', 504, 'timed out'],
  ['GROBID_BUSY', 503, 'busy'],
  ['GROBID_CONFIGURATION_ERROR', 503, 'configuration is invalid'],
  ['MANUSCRIPT_PARSE_FAILED', 502, 'could not parse'],
] as const)('explains %s instead of masking it as a generic service error', (code, status, message) => {
  const error = new ApiResponseError('private provider detail', status, { detail: { code, message: 'private provider detail' } })
  expect(wholePaperError(error)).toContain(message)
  expect(wholePaperError(error)).not.toContain('private provider detail')
})

it('keeps unknown server errors sanitized', () => {
  const error = new ApiResponseError('secret internal path', 500, { detail: { code: 'UNKNOWN', message: 'secret internal path' } })
  expect(wholePaperError(error)).toBe('The local service could not complete this step. Check its configuration and try again.')
})
