import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardList,
  FileSearch,
  HelpCircle,
  Plus,
  XCircle,
} from 'lucide-react'
import { AppHeader } from '@/components/app/AppHeader'
import { DashboardQuickActions } from '@/components/app/DashboardQuickActions'
import { NeedsReviewSection } from '@/components/app/NeedsReviewSection'
import { VerificationOverview } from '@/components/app/VerificationOverview'
import { VerificationWorkflowCta } from '@/components/app/VerificationWorkflowCta'
import { WorkspaceInsights } from '@/components/app/WorkspaceInsights'
import { VerificationActivityCard } from '@/components/verification/VerificationActivityCard'
import {
  getMostRecentRecord,
  getNeedsReviewRecords,
  getRecentRecords,
} from '@/lib/dashboard-selectors'
import { computeDashboardStats } from '@/mocks/verification'
import { useVerificationStore } from '@/stores/verificationStore'
import { useUserDisplayName } from '@/hooks/useUserDisplayName'
import { ROUTES } from '@/constants'
import { Button } from '@/components/ui/Button'
import { StatCard } from '@/components/sciverify/StatCard'

export default function AppHomePage() {
  const displayName = useUserDisplayName()
  const records = useVerificationStore((state) => state.records)
  const stats = computeDashboardStats(records)
  const recentRecords = getRecentRecords(records)
  const needsReviewRecords = getNeedsReviewRecords(records, 10)
  const mostRecentRecord = getMostRecentRecord(records)

  return (
    <div className="space-y-7">
      <AppHeader
        title={`Welcome back, ${displayName}`}
        description="Evidence-backed verification for your scientific claims."
        actions={
          <Link to={ROUTES.APP_VERIFY} className="w-full sm:w-auto">
            <Button className="h-10 w-full sm:w-auto">
              <Plus className="h-4 w-4" aria-hidden />
              New Verification
            </Button>
          </Link>
        }
      />

      <section aria-label="Quick actions">
        <DashboardQuickActions mostRecentRecord={mostRecentRecord} />
      </section>

      <section aria-label="Verification statistics">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          <StatCard
            label="Total Verifications"
            value={stats.total}
            description="All verification runs"
            accent="total"
            icon={<ClipboardList className="h-4 w-4" aria-hidden />}
          />
          <StatCard
            label="Supports"
            value={stats.supports}
            description="Evidence aligned"
            accent="SUPPORTS"
            icon={<CheckCircle2 className="h-4 w-4" aria-hidden />}
          />
          <StatCard
            label="Overstated"
            value={stats.overstated}
            description="Claims requiring review"
            accent="OVERSTATED"
            icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
          />
          <StatCard
            label="Contradicts"
            value={stats.contradicts}
            description="Evidence conflicts"
            accent="CONTRADICTS"
            icon={<XCircle className="h-4 w-4" aria-hidden />}
          />
          <StatCard
            label="Insufficient"
            value={stats.insufficient}
            description="Insufficient evidence"
            accent="INSUFFICIENT"
            icon={<HelpCircle className="h-4 w-4" aria-hidden />}
          />
          <StatCard
            label="Fabricated"
            value={stats.fabricated}
            description="Citation authenticity issue"
            accent="FABRICATED"
            icon={<Ban className="h-4 w-4" aria-hidden />}
          />
        </div>
      </section>

      <section
        className="grid grid-cols-1 gap-5 lg:grid-cols-2 lg:items-start"
        aria-label="Verification overview, workflow, needs review, and workspace insights"
      >
        <div className="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-5">
          <VerificationOverview
            stats={stats}
            records={records}
            className="order-1"
          />
          <NeedsReviewSection
            records={records}
            needsReviewRecords={needsReviewRecords}
            className="order-3 lg:order-none"
          />
        </div>
        <div className="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-5">
          <div className="order-2 contents lg:contents">
            <VerificationWorkflowCta />
          </div>
          <WorkspaceInsights
            records={records}
            stats={stats}
            className="order-4 lg:order-none"
          />
        </div>
      </section>

      <section aria-label="Recent verification activity">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold text-text-primary">
            Recent verification activity
          </h2>
          <Link
            to={ROUTES.APP_HISTORY}
            className="rounded-sm text-sm font-medium text-primary outline-offset-2 transition-colors hover:text-primary-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          >
            View all
          </Link>
        </div>

        {recentRecords.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface px-6 py-10 text-center">
            <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-surface-elevated">
              <FileSearch className="h-5 w-5 text-text-muted" aria-hidden />
            </span>
            <div className="mt-4 space-y-2">
              <p className="text-sm font-medium text-text-primary">
                No verification runs yet
              </p>
              <p className="mx-auto max-w-md text-sm text-text-secondary">
                Start your first evidence-backed citation verification to see
                results here.
              </p>
            </div>
            <Link to={ROUTES.APP_VERIFY} className="mt-5 inline-block">
              <Button className="h-10">Start Verification</Button>
            </Link>
          </div>
        ) : (
          <div className="grid gap-4">
            {recentRecords.map((record) => (
              <VerificationActivityCard key={record.id} record={record} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
