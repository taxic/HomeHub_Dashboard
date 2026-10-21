import { useState, type FormEvent } from 'react'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'
import { Icon } from '../components/Icon'
import { Banner, Field } from '../components/ui'

function useSubmit(fn: () => Promise<void>) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Cannot reach the backend')
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, submit }
}

export function LoginPage() {
  const { login } = useAuth()
  const [u, setU] = useState('')
  const [p, setP] = useState('')
  const { busy, error, submit } = useSubmit(() => login(u, p))
  return (
    <div className="login">
      <form className="card" onSubmit={submit} aria-label="Sign in">
        <div className="brand" style={{ padding: 0, marginBottom: 18 }}><Icon name="containers" size={24} /> HomeLab Command Centre</div>
        {error && <Banner kind="crit" title={error} />}
        <Field label="Username" htmlFor="u"><input id="u" className="input" autoComplete="username" value={u} onChange={(e) => setU(e.target.value)} required autoFocus /></Field>
        <Field label="Password" htmlFor="p"><input id="p" className="input" type="password" autoComplete="current-password" value={p} onChange={(e) => setP(e.target.value)} required /></Field>
        <button className="btn primary" style={{ width: '100%' }} disabled={busy || !u || !p}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  )
}

export function SetupPage() {
  const { setup, setupTokenRequired } = useAuth()
  const [u, setU] = useState('admin')
  const [p, setP] = useState('')
  const [p2, setP2] = useState('')
  const [tok, setTok] = useState('')
  const [local, setLocal] = useState<string | null>(null)
  const { busy, error, submit } = useSubmit(async () => {
    if (p.length < 12) return setLocal('Use at least 12 characters')
    if (p !== p2) return setLocal('Passwords do not match')
    setLocal(null)
    await setup(u, p, tok)
  })
  return (
    <div className="login">
      <form className="card" onSubmit={submit} aria-label="First-run setup">
        <h1 style={{ marginBottom: 6 }}>Create the administrator</h1>
        <p className="muted" style={{ marginTop: 0 }}>This is the first run. Choose credentials for the single owner account.</p>
        {error && <Banner kind="crit" title={error} />}
        <Field label="Username" htmlFor="su"><input id="su" className="input" value={u} onChange={(e) => setU(e.target.value)} required pattern="[A-Za-z0-9_.\-]{3,64}" autoComplete="username" /></Field>
        <Field label="Password" htmlFor="sp" hint="At least 12 characters." error={local}><input id="sp" className="input" type="password" value={p} onChange={(e) => setP(e.target.value)} required autoComplete="new-password" aria-invalid={!!local} /></Field>
        <Field label="Repeat password" htmlFor="sp2"><input id="sp2" className="input" type="password" value={p2} onChange={(e) => setP2(e.target.value)} required autoComplete="new-password" /></Field>
        {setupTokenRequired && <Field label="Setup token" htmlFor="st" hint="From HOMELAB_SETUP_TOKEN on the server."><input id="st" className="input" value={tok} onChange={(e) => setTok(e.target.value)} required /></Field>}
        <button className="btn primary" style={{ width: '100%' }} disabled={busy}>{busy ? 'Creating…' : 'Create account'}</button>
      </form>
    </div>
  )
}
