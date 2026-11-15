import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { AuthLayout } from '@/layouts/AuthLayout'
import { useAuth } from '@/hooks/useAuth'
import { useSupabaseConfigured } from '@/hooks/useSupabaseConfigured'
import { ROUTES } from '@/constants'
import { loginSchema, type LoginSchema } from '@/lib/validations/auth'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export default function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { signIn } = useAuth()
  const isSupabaseReady = useSupabaseConfigured()
  const redirect = searchParams.get('redirect') ?? ROUTES.APP_HOME

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginSchema>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
    },
  })

  const onSubmit = async (values: LoginSchema) => {
    try {
      await signIn(values.email, values.password)
      toast.success('Signed in successfully.')
      navigate(redirect, { replace: true })
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Unable to sign in.',
      )
    }
  }

  return (
    <AuthLayout
      title="Sign in"
      description="Access your SciVerify verification workspace."
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
        <Input
          label="Password"
          type="password"
          autoComplete="current-password"
          placeholder="Enter your password"
          error={errors.password?.message}
          {...register('password')}
        />

        <div className="flex justify-end">
          <Link
            to={ROUTES.FORGOT_PASSWORD}
            className="text-sm text-primary hover:text-primary-hover"
          >
            Forgot password?
          </Link>
        </div>

        <Button
          type="submit"
          className="w-full"
          loading={isSubmitting}
          disabled={!isSupabaseReady}
        >
          {isSubmitting ? 'Signing in...' : 'Sign In'}
        </Button>

        <p className="text-center text-sm text-text-secondary">
          Don&apos;t have an account?{' '}
          <Link
            to={ROUTES.REGISTER}
            className="font-medium text-primary hover:text-primary-hover"
          >
            Create account
          </Link>
        </p>
      </form>
    </AuthLayout>
  )
}
