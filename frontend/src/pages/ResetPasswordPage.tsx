import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { CheckCircle2 } from 'lucide-react'
import { toast } from 'sonner'
import { AuthLayout } from '@/layouts/AuthLayout'
import { useAuth } from '@/hooks/useAuth'
import { useSupabaseConfigured } from '@/hooks/useSupabaseConfigured'
import { ROUTES } from '@/constants'
import {
  resetPasswordSchema,
  type ResetPasswordSchema,
} from '@/lib/validations/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Panel } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'

export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const { updatePassword, signOut, isRecoverySession, session, initializing, isLocalDemo } = useAuth()
  const isSupabaseReady = useSupabaseConfigured()
  const [completed, setCompleted] = useState(false)
  const sessionInvalid =
    isSupabaseReady && !initializing && !isRecoverySession && !session

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetPasswordSchema>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: {
      password: '',
      confirmPassword: '',
    },
  })

  const onSubmit = async (values: ResetPasswordSchema) => {
    try {
      await updatePassword(values.password)
      await signOut()
      setCompleted(true)
      toast.success('Password updated successfully.')
      setTimeout(() => navigate(ROUTES.LOGIN, { replace: true }), 1500)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Unable to update password.',
      )
    }
  }

  if (isLocalDemo) return <Navigate to={ROUTES.APP_HOME} replace />

  if (initializing) {
    return (
      <AuthLayout
        title="Reset password"
        description="Verifying your recovery session..."
      >
        <div className="flex justify-center py-8">
          <Spinner size="lg" className="text-primary" />
        </div>
      </AuthLayout>
    )
  }

  if (sessionInvalid) {
    return (
      <AuthLayout
        title="Reset link expired"
        description="This password reset link is invalid or has expired."
      >
        <Panel className="space-y-4 text-center">
          <p className="text-sm text-text-secondary">
            Request a new reset link and try again.
          </p>
          <Link to={ROUTES.FORGOT_PASSWORD} className="block">
            <Button className="w-full">Request New Link</Button>
          </Link>
          <Link to={ROUTES.LOGIN} className="block">
            <Button variant="outline" className="w-full">
              Back to Sign In
            </Button>
          </Link>
        </Panel>
      </AuthLayout>
    )
  }

  if (completed) {
    return (
      <AuthLayout
        title="Password updated"
        description="Your password has been changed successfully."
      >
        <Panel className="space-y-4 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-success/20 bg-success/10">
            <CheckCircle2 className="h-5 w-5 text-success" />
          </div>
          <Link to={ROUTES.LOGIN} className="block">
            <Button className="w-full">Sign In</Button>
          </Link>
        </Panel>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout
      title="Reset password"
      description="Choose a new password for your SciVerify account."
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="New Password"
          type="password"
          autoComplete="new-password"
          placeholder="At least 8 characters"
          error={errors.password?.message}
          {...register('password')}
        />
        <Input
          label="Confirm Password"
          type="password"
          autoComplete="new-password"
          placeholder="Re-enter your password"
          error={errors.confirmPassword?.message}
          {...register('confirmPassword')}
        />

        <Button
          type="submit"
          className="w-full"
          loading={isSubmitting}
          disabled={!isSupabaseReady}
        >
          {isSubmitting ? 'Updating password...' : 'Update Password'}
        </Button>
      </form>
    </AuthLayout>
  )
}
