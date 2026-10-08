import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { AppHeader } from '@/components/app/AppHeader'
import { VerificationForm } from '@/components/verification/VerificationForm'
import { VerificationLoading } from '@/components/verification/VerificationLoading'
import { VerificationResultView } from '@/components/verification/VerificationResultView'
import { useAuth } from '@/hooks/useAuth'
import { SourceRequiredError, verifyCitation } from '@/services/verificationService'
import { useVerificationStore } from '@/stores/verificationStore'
import { ROUTES, verificationReportPath } from '@/constants'
import { Button } from '@/components/ui/Button'
import { Panel } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import type { VerificationFormSchema } from '@/lib/validations/verification'
import type { VerificationResult } from '@/types/verification'

import { ManualSourceRecovery } from '@/components/verification/ManualSourceRecovery'
import type { BackendVerificationResponse } from '@/types/backend-verification'

type SubmissionPhase = 'idle' | 'loading' | 'error' | 'source-required'

export default function VerifyPage() {
  const { verificationId } = useParams<{ verificationId?: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const { user, isLocalDemo } = useAuth()
  const getRecord = useVerificationStore((state) => state.getRecord)
  const addRecord = useVerificationStore((state) => state.addRecord)
  const historyLoading = useVerificationStore((state) => state.loading)
  const historyHydrated = useVerificationStore((state) => state.hydrated)

  const [submissionPhase, setSubmissionPhase] = useState<SubmissionPhase>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [freshResult, setFreshResult] = useState<VerificationResult | null>(null)

  const [recovery, setRecovery] = useState<BackendVerificationResponse | null>(null)
  const [pendingInput, setPendingInput] = useState<VerificationFormSchema | null>(null)

  const storedRecord = verificationId ? getRecord(verificationId) : undefined

  useEffect(() => {
    const legacyRecordId = (location.state as { recordId?: string } | null)
      ?.recordId

    if (legacyRecordId && !verificationId) {
      navigate(verificationReportPath(legacyRecordId), { replace: true, state: null })
    }
  }, [location.state, navigate, verificationId])

  useEffect(() => {
    // Reset transient submission state on route change
    setSubmissionPhase('idle')
    setErrorMessage(null)
    setFreshResult(null)
  }, [verificationId])

  const phase = (() => {
    if (submissionPhase === 'loading') return 'loading' as const
    if (submissionPhase === 'source-required') return 'source-required' as const
    if (submissionPhase === 'error') return 'error' as const
    if (freshResult) return 'result' as const
    if (verificationId) {
      if (!historyHydrated || historyLoading) return 'history-loading' as const
      return storedRecord ? ('result' as const) : ('error' as const)
    }
    return 'form' as const
  })()

  const result = freshResult ?? storedRecord ?? null

  const handleSubmit = async (values: VerificationFormSchema) => {
    if (!user?.id) {
      toast.error('You must be signed in to save verification history.')
      return
    }

    setPendingInput({ ...values })
    setFreshResult(null)
    setSubmissionPhase('loading')
    setErrorMessage(null)

    try {
      const verificationResult = await verifyCitation({
        claim: values.claim,
        citation: values.citation,
        sourceType: values.sourceType,
        context: values.context,
      })

      setFreshResult(verificationResult)
      const { saved } = await addRecord(user.id, verificationResult)
      setSubmissionPhase('idle')
      navigate(verificationReportPath(verificationResult.id), { replace: true })
      toast.success('Verification completed.')
      if (!saved) {
        toast.warning(isLocalDemo
          ? 'Could not save locally. The report is still available now.'
          : 'Could not save to history. The report is still available now.')
      }
    } catch (error) {
      if (error instanceof SourceRequiredError) {
        setRecovery(error.response)
        setSubmissionPhase('source-required')
        return
      }
      setFreshResult(null)
      setSubmissionPhase('error')
      const message =
        error instanceof Error
          ? error.message
          : 'Verification could not be completed.'
      setErrorMessage(message)
      toast.error(message)
    }
  }

  const handleNewVerification = () => {
    setRecovery(null)
    setPendingInput(null)
    setFreshResult(null)
    setSubmissionPhase('idle')
    setErrorMessage(null)
    navigate(ROUTES.APP_VERIFY, { replace: true })
  }

  const handleBackFromReport = () => {
    navigate(ROUTES.APP_HOME)
  }

  const reportErrorMessage =
    submissionPhase === 'error'
      ? errorMessage
      : verificationId && !storedRecord
        ? 'Verification report not found.'
        : errorMessage

  return (
    <div>
      {phase === 'form' ? (
        <AppHeader
          eyebrow="New verification"
          title="Evaluate a scientific claim"
          description="Evaluate whether a scientific claim is supported by its cited evidence."
        />
      ) : phase === 'source-required' ? (
        <AppHeader title="Cited source required" description="Upload the cited PDF to resume your verification." />
      ) : phase === 'result' ? (
        <AppHeader
          title="Verification report"
          description="Review the complete evidence-backed analysis for this claim."
          actions={
            <Button variant="outline" onClick={handleNewVerification}>
              New verification
            </Button>
          }
        />
      ) : phase === 'loading' || phase === 'history-loading' ? (
        <AppHeader
          eyebrow="Verifying"
          title={
            phase === 'history-loading'
              ? 'Loading verification report'
              : 'Running verification pipeline'
          }
          description={
            phase === 'history-loading'
              ? 'Retrieving the stored verification report from your history.'
              : 'SciVerify is analyzing the cited paper and running the multi-agent verification workflow.'
          }
        />
      ) : (
        <AppHeader
          title="Verification unavailable"
          description="The requested verification report could not be loaded."
        />
      )}

      {phase === 'form' ? (
        <VerificationForm
          onSubmit={handleSubmit}
          loading={submissionPhase === 'loading'}
        />
      ) : null}

      {phase === 'source-required' && recovery && pendingInput ? (
        <ManualSourceRecovery response={recovery}
          onAccepted={() => handleSubmit(pendingInput)} onCancel={handleNewVerification} />
      ) : null}

      {phase === 'loading' ? (
        <VerificationLoading
          stageIndex={0}
          message="Analyzing claim against cited paper..."
          indeterminate
        />
      ) : null}

      {phase === 'history-loading' ? (
        <Panel padding="lg" className="flex flex-col items-center gap-3 text-center">
          <Spinner size="lg" className="text-primary" />
          <p className="text-sm text-text-secondary">Loading stored verification report...</p>
        </Panel>
      ) : null}

      {phase === 'error' ? (
        <Panel padding="md" className="space-y-4 border-danger/30">
          <p className="font-medium text-text-primary">
            {submissionPhase === 'error'
              ? 'Verification could not be completed.'
              : verificationId
                ? 'Verification report not found.'
                : 'Verification could not be completed.'}
          </p>
          <p className="text-sm text-danger">{reportErrorMessage}</p>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => pendingInput ? handleSubmit(pendingInput) : handleNewVerification()}>Try again</Button>
            {verificationId ? (
              <Button variant="outline" onClick={() => navigate(ROUTES.APP_HISTORY)}>
                View history
              </Button>
            ) : null}
          </div>
        </Panel>
      ) : null}

      {phase === 'result' && result ? (
        <VerificationResultView result={result} onBack={handleBackFromReport} />
      ) : null}
    </div>
  )
}
