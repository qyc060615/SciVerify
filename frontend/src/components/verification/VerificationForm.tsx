import { Controller, useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  verificationFormSchema,
  type VerificationFormSchema,
} from '@/lib/validations/verification'
import { VerificationPipelinePreview } from '@/components/verification/VerificationPipelinePreview'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { Panel } from '@/components/ui/Card'
import { cn } from '@/lib/cn'
import type { SourceType } from '@/types/verification'

const sourceTypeOptions: Array<{ value: SourceType; label: string }> = [
  { value: 'doi', label: 'DOI' },
  { value: 'url', label: 'URL' },
  { value: 'citation', label: 'Citation' },
  { value: 'reference', label: 'Reference' },
]

export interface VerificationFormProps {
  onSubmit: (values: VerificationFormSchema) => void
  loading?: boolean
}

export function VerificationForm({ onSubmit, loading = false }: VerificationFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<VerificationFormSchema>({
    resolver: zodResolver(verificationFormSchema),
    defaultValues: {
      claim: '',
      citation: '',
      sourceType: 'doi' as SourceType,
      context: '',
    },
  })

  const claimValue = useWatch({ control, name: 'claim' }) ?? ''

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
      <Panel padding="lg" className="space-y-6">
        <div className="space-y-2">
          <Textarea
            label="Scientific claim"
            placeholder="Example: The method improves software development productivity by 40%."
            hint="Enter the exact claim you want to verify."
            rows={6}
            error={errors.claim?.message}
            disabled={loading}
            className="min-h-40 text-base"
            {...register('claim')}
          />
          <p className="text-right text-xs tabular-nums text-text-muted">
            {claimValue.length} / 2000
          </p>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-widest text-text-muted">
            Source type
          </p>
          <Controller
            name="sourceType"
            control={control}
            render={({ field }) => (
              <div className="flex flex-wrap gap-2">
                {sourceTypeOptions.map((option) => {
                  const active = field.value === option.value
                  return (
                    <button
                      key={option.value}
                      type="button"
                      disabled={loading}
                      onClick={() => field.onChange(option.value)}
                      className={cn(
                        'rounded-lg border px-3 py-2 text-sm font-medium transition-colors',
                        active
                          ? 'border-primary/30 bg-primary-muted text-primary'
                          : 'border-border bg-surface text-text-secondary hover:border-border/80 hover:text-text-primary',
                      )}
                    >
                      {option.label}
                    </button>
                  )
                })}
              </div>
            )}
          />
          {errors.sourceType?.message ? (
            <p className="text-xs text-danger">{errors.sourceType.message}</p>
          ) : null}
        </div>

        <Textarea
          label="Citation / DOI"
          placeholder="Example: 10.1145/example or paste a full citation string."
          hint="Provide the DOI, citation, or paper identifier that supposedly supports the claim."
          rows={3}
          error={errors.citation?.message}
          disabled={loading}
          {...register('citation')}
        />

        <Textarea
          label="Additional context (optional)"
          placeholder="Section, paragraph, or experimental conditions."
          hint="Optional supporting context for interpreting the claim."
          rows={2}
          error={errors.context?.message}
          disabled={loading}
          className="opacity-90"
          {...register('context')}
        />
      </Panel>

      <VerificationPipelinePreview />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-text-muted">
          Submissions are sent to the SciVerify backend for evidence retrieval and
          multi-agent analysis.
        </p>
        <Button
          type="submit"
          loading={loading}
          disabled={loading}
          className="w-full sm:w-auto"
        >
          {loading ? 'Verifying...' : 'Verify Citation'}
        </Button>
      </div>
    </form>
  )
}
