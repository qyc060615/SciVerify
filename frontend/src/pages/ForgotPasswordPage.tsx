import { Link, Navigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { MailCheck } from 'lucide-react'
import { toast } from 'sonner'
import { useState } from 'react'
import { AuthLayout } from '@/layouts/AuthLayout'
import { useAuth } from '@/hooks/useAuth'
import { useSupabaseConfigured } from '@/hooks/useSupabaseConfigured'
import { ROUTES } from '@/constants'
import {
  forgotPasswordSchema,
  type ForgotPasswordSchema,
} from '@/lib/validations/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Panel } from '@/components/ui/Card'

export default function ForgotPasswordPage() {
  const { resetPassword, isLocalDemo } = useAuth()
  const isSupabaseReady = useSupabaseConfigured()
  const [submitted, setSubmitted] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotPasswordSchema>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  })

  const onSubmit = async (values: ForgotPasswordSchema) => {
    try {
      await resetPassword(values.email)
      setSubmitted(true)
      toast.success('If an account exists, reset instructions were sent.')
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : 'Unable to send reset email.',
      )
    }
  }

  if (isLocalDemo) return <Navigate to={ROUTES.APP_HOME} replace />

  if (submitted) {
    return (
      <AuthLayout
        title="Check your email"
        description="Password reset instructions may be on the way."
      >
        <Panel className="space-y-4 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-primary/20 bg-primary-muted">
            <MailCheck className="h-5 w-5 text-primary" />
          </div>
          <p className="text-sm text-text-secondary">
            If an account exists for this email, you&apos;ll receive
            instructions to reset your password.
          </p>
          <Link to={ROUTES.LOGIN} className="block">
            <Button variant="outline" className="w-full">
              Back to Sign In
            </Button>
          </Link>
        </Panel>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Forgot password"
      description="We'll send reset instructions if an account exists."
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@university.edu"
          error={errors.email?.message}
          {...register('email')}
        />

        <Button
          type="submit"
          className="w-full"
          loading={isSubmitting}
          disabled={!isSupabaseReady}
        >
          {isSubmitting ? 'Sending reset email...' : 'Send Reset Link'}
        </Button>

        <p className="text-center text-sm text-text-secondary">
          Remember your password?{' '}
          <Link
            to={ROUTES.LOGIN}
            className="font-medium text-primary hover:text-primary-hover"
          >
            Sign in
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
