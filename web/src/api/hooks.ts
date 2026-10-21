import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type * as T from './types'

/** Poll interval comes from the server-side setting; pauses automatically in background tabs. */
export function useRefreshMs(): number {
  const qc = useQueryClient()
  const s = qc.getQueryData<T.SettingsResponse>(['settings'])
  return (s?.settings.dashboard_refresh_seconds ?? 10) * 1000
}

export const useSettings = () => useQuery({ queryKey: ['settings'], queryFn: () => api<T.SettingsResponse>('/settings') })
export const useOverview = () => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['overview'], queryFn: () => api<T.Overview>('/overview'), refetchInterval: ms })
}
export const useServices = () => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['services'], queryFn: () => api<T.Page<T.ServiceView>>('/services', { query: { limit: 200 } }), refetchInterval: ms })
}
export const useService = (id: number) => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['services', id], queryFn: () => api<T.ServiceView>(`/services/${id}`), refetchInterval: ms })
}
export const useContainers = () => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['containers'], queryFn: () => api<T.ContainerListResponse>('/containers'), refetchInterval: ms })
}
export const useContainerLogs = (id: string, tail: number, enabled = true) =>
  useQuery({ queryKey: ['containers', id, 'logs', tail], queryFn: () => api<T.ContainerLogs>(`/containers/${id}/logs`, { query: { tail } }), enabled, retry: false })
export const useHistory = (range: T.HistoryRange) => {
  const ms = Math.max(useRefreshMs(), 15000)
  return useQuery({ queryKey: ['history', range], queryFn: () => api<T.HistoryResponse>('/metrics/history', { query: { range } }), refetchInterval: ms, placeholderData: keepPreviousData })
}
export const useStorage = () => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['storage'], queryFn: () => api<T.StorageResponse>('/storage'), refetchInterval: ms })
}
export const useVolumes = () => useQuery({ queryKey: ['volumes'], queryFn: () => api<T.VolumeOut[]>('/storage/volumes') })
export const useAlerts = (status: 'open' | 'resolved' | 'all') => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['alerts', status], queryFn: () => api<T.Page<T.AlertOut>>('/alerts', { query: { status, limit: 100 } }), refetchInterval: ms })
}
export const useEvents = () => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['events'], queryFn: () => api<T.Page<T.EventOut>>('/events', { query: { limit: 100 } }), refetchInterval: ms })
}
export const useBackups = () => {
  const ms = useRefreshMs()
  return useQuery({ queryKey: ['backups'], queryFn: () => api<T.BackupJobOut[]>('/backups'), refetchInterval: ms })
}
export const useSessions = () => useQuery({ queryKey: ['sessions'], queryFn: () => api<T.SessionOut[]>('/auth/sessions') })
export const useApiKeys = () => useQuery({ queryKey: ['apikeys'], queryFn: () => api<T.ApiKeyOut[]>('/auth/api-keys') })

/** Mutation helper that invalidates the given query keys on success. */
export function useApiMutation<V, R>(fn: (v: V) => Promise<R>, invalidate: string[][]) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all(invalidate.map((k) => qc.invalidateQueries({ queryKey: k }))),
  })
}
