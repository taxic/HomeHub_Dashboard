import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthProvider'
import { ErrorState, Spinner } from './components/ui'
import { AppShell } from './layout/AppShell'
import { AlertsPage } from './pages/AlertsPage'
import { BackupsPage } from './pages/BackupsPage'
import { ContainerDetailPage, ContainersPage } from './pages/ContainersPage'
import { LoginPage, SetupPage } from './pages/LoginPage'
import { MetricsPage } from './pages/MetricsPage'
import { OverviewPage } from './pages/OverviewPage'
import { ServiceDetailPage, ServicesPage } from './pages/ServicesPage'
import { SettingsPage } from './pages/SettingsPage'
import { StoragePage } from './pages/StoragePage'
import { NetworkError } from './api/client'

export default function App() {
  const { state, retry } = useAuth()
  if (state === 'loading') return <div className="login"><Spinner label="Starting" /></div>
  if (state === 'unreachable') return <div className="login"><div className="card"><ErrorState error={new NetworkError()} onRetry={retry} /></div></div>
  if (state === 'setup') return <SetupPage />
  if (state === 'anonymous') return <LoginPage />
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="services" element={<ServicesPage />} />
        <Route path="services/:id" element={<ServiceDetailPage />} />
        <Route path="containers" element={<ContainersPage />} />
        <Route path="containers/:id" element={<ContainerDetailPage />} />
        <Route path="metrics" element={<MetricsPage />} />
        <Route path="storage" element={<StoragePage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="backups" element={<BackupsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
