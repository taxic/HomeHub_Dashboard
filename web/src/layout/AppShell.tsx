import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { NetworkError } from '../api/client'
import { useOverview } from '../api/hooks'
import { useAuth } from '../auth/AuthProvider'
import { Icon, type IconName } from '../components/Icon'
import { Banner } from '../components/ui'
import { fmtTime } from '../lib/format'

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: 'Overview', icon: 'overview' },
  { to: '/services', label: 'Services', icon: 'services' },
  { to: '/containers', label: 'Containers', icon: 'containers' },
  { to: '/metrics', label: 'Metrics', icon: 'metrics' },
  { to: '/storage', label: 'Storage', icon: 'storage' },
  { to: '/alerts', label: 'Alerts & events', icon: 'alerts' },
  { to: '/backups', label: 'Backups', icon: 'backups' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]
const PRIMARY = NAV.slice(0, 4)
const MORE = NAV.slice(4)

/** Shown whenever the backend cannot be reached, so stale numbers are never mistaken for live ones. */
function ConnectionBanner() {
  const q = useOverview()
  if (!(q.error instanceof NetworkError)) return null
  return (
    <Banner kind="crit" title="Disconnected from the backend">
      Data on screen is from {q.dataUpdatedAt ? fmtTime(new Date(q.dataUpdatedAt).toISOString()) : 'an earlier session'} and is no longer updating. Retrying automatically.
    </Banner>
  )
}

export function AppShell() {
  const { logout, username } = useAuth()
  const [moreOpen, setMoreOpen] = useState(false)
  const loc = useLocation()
  const moreActive = MORE.some((m) => loc.pathname.startsWith(m.to))
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand"><Icon name="containers" size={22} /> HomeLab Command</div>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'} className="nav-link"><Icon name={n.icon} />{n.label}</NavLink>
        ))}
        <div className="sidebar-foot">
          <div className="faint" style={{ padding: '0 12px' }}>Signed in as {username}</div>
          <button className="nav-link" onClick={() => void logout()}><Icon name="logout" />Sign out</button>
        </div>
      </nav>
      <main className="main" id="main">
        <ConnectionBanner />
        <Outlet />
      </main>
      <nav className="tabbar" aria-label="Primary">
        {PRIMARY.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'} className="tab"><Icon name={n.icon} size={22} />{n.label}</NavLink>
        ))}
        <button className="tab" aria-expanded={moreOpen} aria-current={moreActive ? 'page' : undefined} onClick={() => setMoreOpen((o) => !o)}>
          <Icon name="more" size={22} />More
        </button>
        {moreOpen && (
          <div className="overlay" style={{ alignItems: 'flex-end' }} onClick={() => setMoreOpen(false)}>
            <div className="dialog" role="menu" aria-label="More" style={{ marginBottom: 64 }}>
              {MORE.map((n) => (
                <NavLink key={n.to} to={n.to} className="nav-link" role="menuitem" onClick={() => setMoreOpen(false)}><Icon name={n.icon} />{n.label}</NavLink>
              ))}
              <button className="nav-link" role="menuitem" onClick={() => void logout()}><Icon name="logout" />Sign out</button>
            </div>
          </div>
        )}
      </nav>
    </div>
  )
}
