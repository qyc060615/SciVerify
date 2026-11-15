export function segmentLabel(index: number) {
  return `Claim segment ${index + 1}`
}

export function buildEvidenceSegmentLabelMap(
  segments: Array<{ id: string; evidenceIds: string[] }>,
) {
  const labelsByEvidence = new Map<string, string[]>()

  segments.forEach((segment, index) => {
    const label = segmentLabel(index)
    segment.evidenceIds.forEach((evidenceId) => {
      const existing = labelsByEvidence.get(evidenceId) ?? []
      labelsByEvidence.set(evidenceId, [...existing, label])
    })
  })

  return labelsByEvidence
}
