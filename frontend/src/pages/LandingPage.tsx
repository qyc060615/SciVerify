import { Toaster } from 'sonner'
import { LandingNavbar } from '@/components/landing/LandingNavbar'
import { LandingHero } from '@/components/landing/LandingHero'
import { LandingProblemSolution } from '@/components/landing/LandingProblemSolution'
import { LandingHowItWorks } from '@/components/landing/LandingHowItWorks'
import { LandingAgentArchitecture } from '@/components/landing/LandingAgentArchitecture'
import { LandingVerdictTypes } from '@/components/landing/LandingVerdictTypes'
import { LandingEvidencePreview } from '@/components/landing/LandingEvidencePreview'
import { LandingTrustSection } from '@/components/landing/LandingTrustSection'
import { LandingCTA } from '@/components/landing/LandingCTA'
import { LandingFooter } from '@/components/landing/LandingFooter'

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-text-primary">
      <LandingNavbar />
      <main>
        <LandingHero />
        <LandingProblemSolution />
        <LandingHowItWorks />
        <LandingAgentArchitecture />
        <LandingVerdictTypes />
        <LandingEvidencePreview />
        <LandingTrustSection />
        <LandingCTA />
      </main>
      <LandingFooter />
      <Toaster richColors theme="dark" />
    </div>
  )
}
