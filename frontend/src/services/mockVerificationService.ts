import {
  VERIFICATION_STAGES,
  buildMockVerificationResult,
} from '@/mocks/verification'
import type {
  VerificationFormInput,
  VerificationProgressUpdate,
  VerificationResult,
} from '@/types/verification'

const MOCK_DELAY_MS = 3500
const STEP_INTERVAL_MS = MOCK_DELAY_MS / VERIFICATION_STAGES.length

export async function verifyCitationMock(
  input: VerificationFormInput,
  onProgress?: (update: VerificationProgressUpdate) => void,
): Promise<VerificationResult> {
  for (let index = 0; index < VERIFICATION_STAGES.length; index += 1) {
    const stage = VERIFICATION_STAGES[index]
    onProgress?.({
      stageId: stage.id,
      stageIndex: index,
      message: stage.activeMessage ?? stage.title,
    })
    await delay(STEP_INTERVAL_MS)
  }

  if (input.claim.toLowerCase().includes('fail')) {
    throw new Error('Verification could not be completed. Please try again.')
  }

  return buildMockVerificationResult(input)
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
