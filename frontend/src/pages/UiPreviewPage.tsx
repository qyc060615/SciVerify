import { useState, type ReactNode } from 'react'
import {
  AlertTriangle,
  ChevronDown,
  FileSearch,
  Search,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { toast } from 'sonner'
import { VERDICT_KEYS } from '@/constants/verdicts'
import {
  AgentCard,
  ConfidenceBar,
  EvidenceCard,
  SourceCard,
  StatCard,
  VerdictBadge,
  VerdictCard,
  VerificationTimeline,
} from '@/components/sciverify'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Divider,
  Drawer,
  Dropdown,
  DropdownMenu,
  DropdownTrigger,
  Input,
  Modal,
  Panel,
  Select,
  Skeleton,
  Spinner,
  Tabs,
  TabsList,
  TabsPanel,
  Textarea,
  Tooltip,
} from '@/components/ui'

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
        {description ? (
          <p className="mt-1 text-sm text-text-secondary">{description}</p>
        ) : null}
      </div>
      {children}
    </section>
  )
}

export default function UiPreviewPage() {
  const [modalOpen, setModalOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [checked, setChecked] = useState(true)

  return (
    <div className="mx-auto max-w-7xl space-y-10 pb-16">
      <header className="space-y-3 border-b border-border pb-8">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="primary">Phase 2</Badge>
          <Badge>Design System</Badge>
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-text-primary sm:text-4xl">
          SciVerify UI Preview
        </h1>
        <p className="max-w-3xl text-sm leading-relaxed text-text-secondary sm:text-base">
          Component showcase for the SciVerify dark research interface. Use this
          page to validate buttons, forms, verdict states, cards, and loading
          patterns before building product screens.
        </p>
      </header>

      <Section title="Buttons" description="Primary actions and secondary controls.">
        <div className="flex flex-wrap gap-3">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="outline">Outline</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button loading>Loading</Button>
          <Button disabled>Disabled</Button>
        </div>
      </Section>

      <Section title="Form Controls">
        <div className="grid gap-6 lg:grid-cols-2">
          <Input
            label="Citation query"
            placeholder="Enter DOI, PMID, or claim text"
            leftIcon={<Search className="h-4 w-4" />}
            hint="Supports plain-language scientific claims."
          />
          <Input
            label="Invalid input"
            placeholder="Missing required field"
            error="This field is required."
          />
          <Select
            label="Verification mode"
            placeholder="Select mode"
            options={[
              { value: 'fast', label: 'Fast screening' },
              { value: 'deep', label: 'Deep evidence review' },
              { value: 'multi', label: 'Multi-agent audit' },
            ]}
          />
          <Textarea
            label="Claim excerpt"
            placeholder="Paste the claim you want to verify..."
            hint="Keep claims concise for better agent routing."
          />
          <Checkbox
            label="Include related citations"
            description="Expand the search to semantically related references."
            checked={checked}
            onChange={(event) => setChecked(event.target.checked)}
          />
        </div>
      </Section>

      <Section title="Badges, Avatars, Tooltips">
        <div className="flex flex-wrap items-center gap-3">
          <Badge>Default</Badge>
          <Badge variant="primary">Primary</Badge>
          <Badge variant="success">Success</Badge>
          <Badge variant="warning">Warning</Badge>
          <Badge variant="danger">Danger</Badge>
          <Avatar name="SciVerify" />
          <Avatar name="Research Agent" size="lg" />
          <Tooltip content="Evidence confidence tooltip">
            <Button variant="outline" size="sm">
              Hover me
            </Button>
          </Tooltip>
        </div>
      </Section>

      <Section title="Verdict System">
        <div className="flex flex-wrap gap-2">
          {VERDICT_KEYS.map((verdict) => (
            <VerdictBadge key={verdict} verdict={verdict} />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <VerdictCard
            verdict="SUPPORTS"
            summary="Multiple independent sources align with the cited finding."
            confidence={92}
          />
          <VerdictCard
            verdict="CONTRADICTS"
            summary="Primary literature reports conflicting outcomes."
            confidence={81}
          />
        </div>
      </Section>

      <Section title="Confidence Bars">
        <Panel className="grid gap-5 sm:grid-cols-2">
          <ConfidenceBar value={92} verdict="SUPPORTS" />
          <ConfidenceBar value={64} verdict="OVERSTATED" />
          <ConfidenceBar value={38} verdict="INSUFFICIENT" />
          <ConfidenceBar value={88} verdict="FABRICATED" label="Risk score" />
        </Panel>
      </Section>

      <Section title="Cards & Panels">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <StatCard
            label="Claims verified"
            value="128"
            description="Across 24 uploaded manuscripts"
            trend="+12% this week"
            icon={<ShieldCheck className="h-5 w-5" />}
          />
          <StatCard
            label="Sources indexed"
            value="4.2k"
            description="Peer-reviewed references in cache"
            icon={<FileSearch className="h-5 w-5" />}
          />
          <StatCard
            label="Agent uptime"
            value="99.4%"
            description="Multi-agent verification pipeline"
            icon={<Sparkles className="h-5 w-5" />}
          />
        </div>
      </Section>

      <Section title="Agent, Evidence, and Source Cards">
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          <AgentCard
            name="Citation Parser"
            role="Extracts structured metadata"
            status="completed"
            description="Parsed DOI, authors, and claim span from the uploaded PDF."
          />
          <AgentCard
            name="Evidence Retriever"
            role="Finds supporting literature"
            status="running"
            description="Searching PubMed, Crossref, and Semantic Scholar."
          />
          <AgentCard
            name="Verdict Synthesizer"
            role="Aggregates agent outputs"
            status="idle"
            description="Waiting for upstream agents to finish."
          />
          <EvidenceCard
            title="Primary outcome match"
            source="Nature Medicine, 2023"
            excerpt="The trial demonstrated a statistically significant reduction in biomarker levels compared with placebo."
            verdict="SUPPORTS"
            relevance={94}
          />
          <EvidenceCard
            title="Contradictory cohort study"
            source="Lancet Regional Health, 2022"
            excerpt="No significant difference was observed after adjusting for confounders."
            verdict="CONTRADICTS"
            relevance={78}
          />
          <SourceCard
            title="Randomized trial of intervention X in metabolic syndrome"
            authors="Patel et al."
            journal="Nature Medicine"
            year={2023}
            doi="10.1038/s41591-023-01234"
            url="https://example.org/source"
          />
        </div>
      </Section>

      <Section title="Progress & Timeline">
        <VerificationTimeline
          items={[
            {
              id: '1',
              title: 'Parse citation',
              description: 'Extract claim, metadata, and references.',
              status: 'completed',
            },
            {
              id: '2',
              title: 'Retrieve evidence',
              description: 'Query literature databases and preprint indexes.',
              status: 'active',
            },
            {
              id: '3',
              title: 'Synthesize verdict',
              description: 'Combine agent findings into a final assessment.',
              status: 'pending',
            },
          ]}
        />
      </Section>

      <Section title="Tabs, Dropdown, Overlays">
        <Tabs defaultValue="overview">
          <TabsList
            items={[
              { value: 'overview', label: 'Overview' },
              { value: 'agents', label: 'Agents' },
              { value: 'sources', label: 'Sources' },
            ]}
          />
          <TabsPanel value="overview">
            <Panel>
              <p className="text-sm text-text-secondary">
                Overview panel content for verification summary.
              </p>
            </Panel>
          </TabsPanel>
          <TabsPanel value="agents">
            <Panel>
              <p className="text-sm text-text-secondary">
                Agent activity and routing details.
              </p>
            </Panel>
          </TabsPanel>
          <TabsPanel value="sources">
            <Panel>
              <p className="text-sm text-text-secondary">
                Retrieved sources and citation graph.
              </p>
            </Panel>
          </TabsPanel>
        </Tabs>

        <div className="flex flex-wrap gap-3">
          <Button variant="outline" onClick={() => setModalOpen(true)}>
            Open modal
          </Button>
          <Button variant="outline" onClick={() => setDrawerOpen(true)}>
            Open drawer
          </Button>
          <Dropdown>
            <DropdownTrigger>
              <Button variant="secondary">
                Actions
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownTrigger>
            <DropdownMenu
              items={[
                {
                  label: 'Export report',
                  onSelect: () => toast.success('Report exported'),
                },
                {
                  label: 'Re-run verification',
                  onSelect: () => toast.message('Verification queued'),
                },
                {
                  label: 'Delete session',
                  destructive: true,
                  onSelect: () => toast.error('Delete action blocked in preview'),
                },
              ]}
            />
          </Dropdown>
        </div>
      </Section>

      <Section title="Loading & Error States">
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Loading skeleton</CardTitle>
              <CardDescription>Placeholder while data is fetched.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-24 w-full" />
            </CardContent>
          </Card>
          <Card className="border-danger/30">
            <CardHeader>
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-danger" />
                <CardTitle>Error state</CardTitle>
              </div>
              <CardDescription>
                Failed to retrieve evidence from upstream source.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-sm text-text-secondary">
                <Spinner size="sm" />
                Retry available in 12s
              </div>
              <Button variant="danger" size="sm">
                Retry
              </Button>
            </CardContent>
          </Card>
        </div>
      </Section>

      <Divider label="End of preview" />

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Verification details"
        description="Modal overlay for focused inspection workflows."
      >
        <p className="text-sm text-text-secondary">
          This modal demonstrates the SciVerify overlay pattern for detail views
          without leaving the current context.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setModalOpen(false)}>
            Close
          </Button>
          <Button onClick={() => setModalOpen(false)}>Continue</Button>
        </div>
      </Modal>

      <Drawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Evidence drawer"
      >
        <div className="space-y-4">
          <EvidenceCard
            title="Drawer evidence item"
            excerpt="Side panel layout for source inspection on tablet and desktop."
            verdict="INSUFFICIENT"
            relevance={52}
          />
          <ConfidenceBar value={52} verdict="INSUFFICIENT" />
        </div>
      </Drawer>
    </div>
  )
}
