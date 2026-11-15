import { Link } from 'react-router-dom'
import { MailCheck } from 'lucide-react'
import { toast } from 'sonner'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { AuthLayout } from '@/layouts/AuthLayout'
import { useAuth } from '@/hooks/useAuth'
import { useSupabaseConfigured } from '@/hooks/useSupabaseConfigured'
import { ROUTES } from '@/constants'
import { registerSchema, type RegisterSchema } from '@/lib/validations/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Panel } from '@/components/ui/Card'

export default function RegisterPage() {
  const { signUp } = useAuth()
  const isSupabaseReady = useSupabaseConfigured()
  const [emailConfirmationSent, setEmailConfirmationSent] = useState(false)
  const [registeredEmail, setRegisteredEmail] = useState('')

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterSchema>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      fullName: '',
      email: '',
      password: '',
      confirmPassword: '',
    },
  })

  const onSubmit = async (values: RegisterSchema) => {
    try {
      const result = await signUp(
        values.email,
        values.password,
        values.fullName,
      )

      if (result.needsEmailConfirmation) {
        setRegisteredEmail(values.email)
        setEmailConfirmationSent(true)
        toast.success('Check your email to confirm your account.')
        return
      }

      toast.success('Account created successfully.')
      window.location.assign(ROUTES.APP_HOME)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Unable to create account.',
      )
    }
  }

  if (emailConfirmationSent) {
    return (
      <AuthLayout
        title="Check your email"
        description="Confirm your address to activate your SciVerify account."
      >
        <Panel className="space-y-4 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-primary/20 bg-primary-muted">
            <MailCheck className="h-5 w-5 text-primary" />
          </div>
          <p className="text-sm text-text-secondary">
            We sent a confirmation link to{' '}
            <span className="font-medium text-text-primary">{registeredEmail}</span>.
            Open the email and verify your account before signing in.
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
      title="Create account"
      description="Start verifying scientific citations with SciVerify."
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <Input
          label="Full Name"
          autoComplete="name"
          placeholder="Ada Lovelace"
          error={errors.fullName?.message}
          {...register('fullName')}
        />
        <Input
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="you@university.edu"
          error={errors.email?.message}
          {...register('email')}
        />
        <Input
          label="Password"
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
          {isSubmitting ? 'Creating account...' : 'Create Account'}
        </Button>

        <p className="text-center text-sm text-text-secondary">
          Already have an account?{' '}
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
