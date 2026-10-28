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
import { ApiSettingsPanel } from '@/components/settings/ApiSettingsPanel'
import { SystemStatusPanel } from '@/components/settings/SystemStatusPanel'

const tabs = [{ id: 'account', label: 'ACCOUNT' }, { id: 'system', label: 'SYSTEM STATUS' }, { id: 'api', label: 'API' }] as const
type SettingsTab = typeof tabs[number]['id']

export default function SettingsPage() {
  const navigate = useNavigate()
  const { user, profile, signOut, isLocalDemo } = useAuth()
  const displayName = useUserDisplayName()
  const [signingOut, setSigningOut] = useState(false)
  const [tab, setTab] = useState<SettingsTab>('account')
  const [visited, setVisited] = useState<SettingsTab[]>(['account'])
  function select(id: SettingsTab) { setTab(id); setVisited(old => old.includes(id) ? old : [...old, id]) }
  const handleLogout = async () => {
    try {
      setSigningOut(true)
      await signOut()
      toast.success('Signed out successfully.')
      navigate(ROUTES.LOGIN, { replace: true })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Unable to sign out.')
    } finally { setSigningOut(false) }
  }
  return <div className="min-w-0 space-y-5">
    <AppHeader title="Settings" description="Manage your account, system services, and API configurations." />
    <div role="tablist" aria-label="Settings" className="flex border-b border-border">
      {tabs.map((item, i) => <button key={item.id} id={'settings-tab-' + item.id} role="tab" type="button" aria-selected={tab === item.id} aria-controls={'settings-panel-' + item.id}
        tabIndex={tab === item.id ? 0 : -1} onClick={() => select(item.id)} onKeyDown={event => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
          event.preventDefault()
          const index = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (i + (event.key === 'ArrowRight' ? 1 : 2)) % 3
          select(tabs[index].id); document.getElementById('settings-tab-' + tabs[index].id)?.focus()
        }} className={'border-b-2 px-3 py-3 text-xs font-semibold transition-colors sm:px-5 sm:text-sm ' + (tab === item.id ? 'border-primary text-primary' : 'border-transparent text-text-muted hover:text-text-primary')}>{item.label}</button>)}
    </div>
    <section role="tabpanel" id="settings-panel-account" aria-labelledby="settings-tab-account" hidden={tab !== 'account'}>
      <Panel className="space-y-5">
        <div className="flex min-w-0 items-center gap-3"><Avatar name={displayName} size="md" /><div className="min-w-0"><h2 className="text-base font-semibold text-text-primary">Profile</h2><p className="text-sm text-text-secondary">{isLocalDemo ? 'Local Demo identity. This profile is read-only.' : 'Your workspace identity loaded from Supabase.'}</p></div></div>
        <div className="grid gap-4 sm:grid-cols-2"><Input label="Full name" value={profile?.full_name ?? displayName} readOnly leftIcon={<UserRound className="h-4 w-4" />} /><Input label="Email" value={user?.email ?? ''} readOnly leftIcon={<Mail className="h-4 w-4" />} /></div>
        <div className="flex flex-col items-start justify-between gap-4 border-t border-border pt-4 sm:flex-row sm:items-center"><div><h2 className="text-base font-semibold text-text-primary">Account</h2><p className="mt-1 max-w-xl text-sm text-text-secondary">{isLocalDemo ? 'Local Demo uses a local identity and browser history. No cloud account or password is required.' : 'Profile data is loaded from your existing Supabase session and profile record.'}</p></div>
          {!isLocalDemo && <Button variant="danger" size="sm" loading={signingOut} onClick={() => void handleLogout()}><LogOut className="h-4 w-4" />{signingOut ? 'Signing out...' : 'Logout'}</Button>}
        </div>
      </Panel>
    </section>
    <section role="tabpanel" id="settings-panel-system" aria-labelledby="settings-tab-system" hidden={tab !== 'system'}>
      {visited.includes('system') && (isLocalDemo ? <SystemStatusPanel /> : <Panel>Local service administration is available in Local Demo on this machine.</Panel>)}
    </section>
    <section role="tabpanel" id="settings-panel-api" aria-labelledby="settings-tab-api" hidden={tab !== 'api'}>
      {visited.includes('api') && (isLocalDemo ? <ApiSettingsPanel /> : <Panel>API administration is available in Local Demo on this machine. Existing deployment configuration is unchanged.</Panel>)}
    </section>
  </div>
}
