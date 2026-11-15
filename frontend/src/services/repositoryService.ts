import { apiClient } from './api'

export interface RepositoryRecord {
  id: string
  title: string | null
  doi: string | null
  literature_type: 'Reference' | 'Manuscript'
  format: 'pdf' | 'html'
  source_type: 'Uploaded PDF' | 'Retrieved HTML' | 'Other'
  availability: 'available' | 'missing' | 'corrupt' | 'unavailable'
  raw_content_sha256: string
  source_url: string | null
  related_job_ids: string[]
}
export interface RepositoryResponse { records: RepositoryRecord[]; warnings: string[] }
export async function getRepository(signal?: AbortSignal): Promise<RepositoryResponse> {
  return (await apiClient.get<RepositoryResponse>('/api/repository', { signal })).data
}
