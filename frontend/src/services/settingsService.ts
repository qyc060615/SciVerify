import { apiClient } from './api'
export interface SettingsField { name: string; label: string; kind: 'text' | 'url' | 'number' | 'select'; options: string[] }
export interface ApiConnection {
  id: string; label: string; purpose: string; fields: SettingsField[]; values: Record<string, string>
  has_key: boolean; has_own_key: boolean; supports_key: boolean; share_options: string[]; paid_test: boolean
  pending_restart: boolean; active_model: string | null; active_base_url: string | null; active_has_key: boolean
}
export interface ApiSettings { revision: number; services: ApiConnection[]; restart_required: boolean; management_token?: string }
export interface ConnectionDraft { values: Record<string, string>; api_key?: string; clear_api_key: boolean }
export interface CheckResult { id: string; state: 'ok' | 'failed' | 'unknown'; message: string; scope: string }
export interface ServiceStatus extends CheckResult { label: string }
export async function getApiSettings(signal?: AbortSignal): Promise<ApiSettings> {
  return (await apiClient.get<ApiSettings>('/api/settings', { signal })).data
}
export async function saveApiConnection(id: string, draft: ConnectionDraft, revision: number, token: string): Promise<ApiSettings> {
  return (await apiClient.put<ApiSettings>('/api/settings/connections/' + id, { ...draft, revision }, { headers: { 'X-Settings-Token': token } })).data
}
export async function testApiConnection(id: string, draft: ConnectionDraft, allowPaid: boolean, token: string): Promise<CheckResult> {
  return (await apiClient.post<CheckResult>('/api/settings/connections/' + id + '/test', { ...draft, allow_paid: allowPaid }, { headers: { 'X-Settings-Token': token } })).data
}
export async function getSystemStatus(signal?: AbortSignal): Promise<ServiceStatus[]> {
  return (await apiClient.get<{ services: ServiceStatus[] }>('/api/settings/status', { signal })).data.services
}
export async function refreshSystemStatus(token: string): Promise<ServiceStatus[]> {
  return (await apiClient.post<{ services: ServiceStatus[] }>('/api/settings/status/refresh', {}, { headers: { 'X-Settings-Token': token } })).data.services
}
