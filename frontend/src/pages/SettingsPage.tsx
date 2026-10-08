import { useNavigate } from 'react-router-dom'
import { LogOut, Mail, UserRound } from 'lucide-react'
import { toast } from 'sonner'
import { useState } from 'react'
import { AppHeader } from '@/components/app/AppHeader'
import { useAuth } from '@/hooks/useAuth'
import { useUserDisplayName } from '@/hooks/useUserDisplayName'
import { ROUTES } from '@/constants'
import { Avatar } from '@/components/ui/Avatar'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Panel } from '@/components/ui/Card'
import { Divider } from '@/components/ui/Divider'

export default function SettingsPage() {
  const navigate = useNavigate()
  const { user, profile, signOut, isLocalDemo } = useAuth()
  const displayName = useUserDisplayName()
  const [signingOut, setSigningOut] = useState(false)

  const handleLogout = async () => {
    try {
      setSigningOut(true)
      await signOut()
      toast.success('Signed out successfully.')
      navigate(ROUTES.LOGIN, { replace: true })
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : 'Unable to sign out.',
      )
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div>
      <AppHeader
        title="Settings"
        description="Manage your SciVerify workspace profile and account access."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel padding="lg" className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">Profile</h2>
            <p className="mt-1 text-sm text-text-secondary">
              {isLocalDemo ? 'Local Demo identity. This profile is read-only.' : 'Your workspace identity loaded from Supabase.'}
            </p>
          </div>

          <div className="flex items-center gap-4 rounded-lg border border-border/80 bg-surface-elevated/40 p-4">
            <Avatar name={displayName} size="lg" />
            <div>
              <p className="font-medium text-text-primary">{displayName}</p>
              <p className="text-sm text-text-secondary">{user?.email}</p>
            </div>
          </div>

          <div className="space-y-4">
            <Input
              label="Full name"
              value={profile?.full_name ?? displayName}
              readOnly
              leftIcon={<UserRound className="h-4 w-4" />}
            />
            <Input
              label="Email"
              value={user?.email ?? ''}
              readOnly
              leftIcon={<Mail className="h-4 w-4" />}
            />
          </div>
        </Panel>

        <Panel padding="lg" className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-text-primary">Account</h2>
            <p className="mt-1 text-sm text-text-secondary">
              Session and access controls for this workspace.
            </p>
          </div>

          <div className="rounded-lg border border-border/80 bg-surface-elevated/30 p-4 text-sm leading-relaxed text-text-secondary">
            {isLocalDemo
              ? 'Local Demo uses a local identity and browser history. No cloud account or password is required.'
              : 'Profile data is loaded from your existing Supabase session and profile record.'}
          </div>

          {!isLocalDemo ? (
            <>
              <Divider />
              <Button
                variant="danger"
                onClick={handleLogout}
                loading={signingOut}
                className="w-full sm:w-auto"
              >
                <LogOut className="h-4 w-4" />
                {signingOut ? 'Signing out...' : 'Logout'}
              </Button>
            </>
          ) : null}
        </Panel>
      </div>
    </div>
  )
}
