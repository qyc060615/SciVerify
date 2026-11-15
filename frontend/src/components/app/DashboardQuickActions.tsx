import { Link } from 'react-router-dom'
import { Clock, FileSearch, Plus } from 'lucide-react'
import { ROUTES, verificationReportPath } from '@/constants'
import { Button } from '@/components/ui/Button'
import type { VerificationResult } from '@/types/verification'

export interface DashboardQuickActionsProps {
  mostRecentRecord?: VerificationResult
}

const actionButtonClass = 'h-10 w-full justify-center'

export function DashboardQuickActions({
  mostRecentRecord,
}: DashboardQuickActionsProps) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-4 sm:px-5">
      <h2 className="text-sm font-semibold text-text-primary">Quick actions</h2>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <Link to={ROUTES.APP_VERIFY}>
          <Button className={actionButtonClass}>
            <Plus className="h-4 w-4 shrink-0" aria-hidden />
            New Verification
          </Button>
        </Link>
        <Link to={ROUTES.APP_HISTORY}>
          <Button variant="outline" className={actionButtonClass}>
            <Clock className="h-4 w-4 shrink-0" aria-hidden />
            View History
          </Button>
        </Link>
        {mostRecentRecord ? (
          <Link to={verificationReportPath(mostRecentRecord.id)}>
            <Button variant="outline" className={actionButtonClass}>
              <FileSearch className="h-4 w-4 shrink-0" aria-hidden />
              Recent Reports
            </Button>
          </Link>
        ) : (
          <Button variant="outline" className={actionButtonClass} disabled>
            <FileSearch className="h-4 w-4 shrink-0" aria-hidden />
            Recent Reports
          </Button>
        )}
      </div>
    </div>
  )
}
