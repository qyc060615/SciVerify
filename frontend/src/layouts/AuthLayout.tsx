import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { SupabaseConfigNotice } from '@/components/auth/SupabaseConfigNotice'
import { ROUTES } from '@/constants'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'

export function AuthLayout({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <div className="flex min-h-[calc(100svh-4rem)] items-center justify-center py-8">
      <div className="w-full max-w-md space-y-6 px-1">
        <div className="flex flex-col items-center gap-3 text-center">
          <Link
            to={ROUTES.HOME}
            className="flex items-center gap-2 text-text-primary transition-colors hover:text-primary"
          >
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-surface-elevated">
              <ShieldCheck className="h-5 w-5 text-primary" />
            </span>
            <span className="text-lg font-semibold tracking-tight">SciVerify</span>
          </Link>
        </div>

        <Card>
          <CardHeader className="text-center">
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </CardHeader>
          <CardContent>
            <SupabaseConfigNotice />
            {children}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
