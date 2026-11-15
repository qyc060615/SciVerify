const DOI_PREFIX_PATTERN = /^doi:\s*/i
const DOI_URL_PATTERN = /^https?:\/\/(?:dx\.)?doi\.org\/\s*/i
const DOI_IN_TEXT_PATTERN = /10\.\d{4,9}\/\S+/i
const VALID_DOI_PATTERN = /^10\.\d{4,9}\/\S+$/i

export class InvalidDoiError extends Error {
  constructor(message = 'Please provide a valid DOI.') {
    super(message)
    this.name = 'InvalidDoiError'
  }
}

export function extractDoi(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) {
    throw new InvalidDoiError()
  }

  let candidate = trimmed.replace(DOI_PREFIX_PATTERN, '').replace(DOI_URL_PATTERN, '').trim()

  if (!VALID_DOI_PATTERN.test(candidate)) {
    const match = trimmed.match(DOI_IN_TEXT_PATTERN)
    if (match) {
      candidate = match[0]
    }
  }

  candidate = candidate.replace(/[.,;]+$/, '')

  if (!VALID_DOI_PATTERN.test(candidate)) {
    throw new InvalidDoiError(
      'Please provide a valid DOI (for example, 10.1038/s41586-020-2649-2).',
    )
  }

  return candidate.toLowerCase()
}
