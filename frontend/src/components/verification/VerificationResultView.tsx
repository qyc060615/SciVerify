import { VerificationReportView } from '@/components/verification/VerificationReportView'
import type { VerificationResult } from '@/types/verification'

export interface VerificationResultViewProps {
  result: VerificationResult
  onBack?: () => void
}

export function VerificationResultView({
  result,
  onBack,
}: VerificationResultViewProps) {
  return <VerificationReportView result={result} onBack={onBack} />
}
