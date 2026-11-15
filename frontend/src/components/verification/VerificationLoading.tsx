import { Scale, Shield, Swords } from 'lucide-react'
import { cn } from '@/lib/cn'
import { AgentCard } from '@/components/sciverify/AgentCard'
import { ProgressStep } from '@/components/sciverify/ProgressStep'
import { Panel } from '@/components/ui/Card'
import { VERIFICATION_STAGES } from '@/mocks/verification'
import type { AgentStatus } from '@/types'

export interface VerificationLoadingProps {
  stageIndex: number
  message?: string
  indeterminate?: boolean
}

const agentMeta = {
  prosecutor: {
    name: 'Prosecutor',
    role: 'Challenge the claim',
    icon: Swords,
    waitingMessage: 'Waiting for evidence...',
    runningMessage: 'Challenging the claim...',
  },
  defender: {
    name: 'Defender',
    role: 'Build the strongest supporting case',
    icon: Shield,
    waitingMessage: 'Waiting for evidence...',
    runningMessage: 'Building supporting case...',
  },
  adjudicator: {
    name: 'Adjudicator',
    role: 'Make the final evidence-backed decision',
    icon: Scale,
    waitingMessage: 'Waiting for arguments...',
    runningMessage: 'Evaluating both arguments...',
  },
} as const

function getAgentStatus(
  agent: 'prosecutor' | 'defender' | 'adjudicator',
  stageIndex: number,
): AgentStatus {
  const agentStageIndex = VERIFICATION_STAGES.findIndex(
    (stage) => stage.agent === agent,
  )

  if (stageIndex > agentStageIndex) return 'completed'
  if (stageIndex === agentStageIndex) return 'running'
  return 'idle'
}

function getAgentDescription(
  agent: 'prosecutor' | 'defender' | 'adjudicator',
  stageIndex: number,
  message?: string,
): string {
  const meta = agentMeta[agent]
  const status = getAgentStatus(agent, stageIndex)

  if (status === 'running') {
    return message ?? meta.runningMessage
  }
  if (status === 'completed') {
    return 'Analysis completed.'
  }
  return meta.waitingMessage
}

export function VerificationLoading({
  stageIndex,
  message,
  indeterminate = false,
}: VerificationLoadingProps) {
  const currentStage = VERIFICATION_STAGES[stageIndex]
  const activeStageIndex = indeterminate ? 0 : stageIndex

  return (
    <div className="space-y-6">
      <Panel padding="md" className="space-y-2 border-primary/15">
        <p className="text-xs font-semibold uppercase tracking-widest text-primary">
          Verifying citation
        </p>
        <p className="text-sm text-text-secondary">
          {message ?? currentStage?.activeMessage ?? currentStage?.title ?? 'Processing verification pipeline...'}
        </p>
      </Panel>

      <Panel padding="md" className="space-y-1">
        {VERIFICATION_STAGES.map((stage, index) => {
          let status: 'pending' | 'active' | 'completed' = 'pending'
          if (indeterminate) {
            status = index === 0 ? 'active' : 'pending'
          } else if (activeStageIndex > index) {
            status = 'completed'
          } else if (activeStageIndex === index) {
            status = 'active'
          }

          return (
            <ProgressStep
              key={stage.id}
              step={index + 1}
              title={stage.title}
              description={
                status === 'active'
                  ? message ?? stage.activeMessage ?? stage.title
                  : undefined
              }
              status={status}
              isLast={index === VERIFICATION_STAGES.length - 1}
            />
          )
        })}
      </Panel>

      <div className="space-y-4">
        <p className="text-center text-xs font-semibold uppercase tracking-widest text-text-muted">
          Agent debate
        </p>

        <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-stretch">
          <AgentCard
            name={agentMeta.prosecutor.name}
            role={agentMeta.prosecutor.role}
            icon={agentMeta.prosecutor.icon}
            status={indeterminate ? 'running' : getAgentStatus('prosecutor', stageIndex)}
            description={
              indeterminate
                ? 'Waiting for backend analysis...'
                : getAgentDescription('prosecutor', stageIndex, message)
            }
            className={cn(
              (indeterminate ||
                getAgentStatus('prosecutor', stageIndex) === 'running') &&
                'ring-1 ring-primary/40',
            )}
          />
          <p
            className="hidden self-center text-sm font-semibold text-text-muted md:block"
            aria-hidden
          >
            VS
          </p>
          <AgentCard
            name={agentMeta.defender.name}
            role={agentMeta.defender.role}
            icon={agentMeta.defender.icon}
            status={indeterminate ? 'idle' : getAgentStatus('defender', stageIndex)}
            description={
              indeterminate
                ? 'Waiting for backend analysis...'
                : getAgentDescription('defender', stageIndex, message)
            }
            className={cn(
              getAgentStatus('defender', stageIndex) === 'running' &&
                'ring-1 ring-primary/40',
            )}
          />
        </div>

        <p className="text-center text-lg text-text-muted" aria-hidden>
          ↓
        </p>

        <AgentCard
          name={agentMeta.adjudicator.name}
          role={agentMeta.adjudicator.role}
          icon={agentMeta.adjudicator.icon}
          status={indeterminate ? 'idle' : getAgentStatus('adjudicator', stageIndex)}
          description={
            indeterminate
              ? 'Waiting for backend analysis...'
              : getAgentDescription('adjudicator', stageIndex, message)
          }
          className={cn(
            getAgentStatus('adjudicator', stageIndex) === 'running' &&
              'ring-1 ring-primary/40',
          )}
        />
      </div>

      {indeterminate ? (
        <Panel padding="md" className="text-sm text-text-secondary">
          Waiting for the SciVerify backend to complete verification...
        </Panel>
      ) : stageIndex >= VERIFICATION_STAGES.length - 1 ? (
        <Panel padding="md" className="text-sm text-text-secondary">
          Finalizing validated verdict...
        </Panel>
      ) : null}
    </div>
  )
}
