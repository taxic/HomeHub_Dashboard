import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, NetworkError, refreshSession, setAccessToken, setAuthLostHandler } from '../api/client'

export type AuthState = 'loading' | 'unreachable' | 'setup' | 'anonymous' | 'authenticated'

type Ctx = {
  state: AuthState
  username: string | null
  retry: () => void
  login: (username: string, password: string) => Promise<void>
  setup: (username: string, password: string, setupToken?: string) => Promise<void>
  logout: () => Promise<void>
  setupTokenRequired: boolean
}

const AuthContext = createContext<Ctx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>('loading')
  const [username, setUsername] = useState<string | null>(null)
  const [setupTokenRequired, setTokenReq] = useState(false)
  const qc = useQueryClient()

  const boot = useCallback(async () => {
    setState('loading')
    try {
      const st = await api<{ setup_required: boolean; setup_token_required: boolean }>('/auth/status', { auth: false })
      setTokenReq(st.setup_token_required)
      if (st.setup_required) return setState('setup')
      if (await refreshSession()) {
        const me = await api<{ username: string }>('/auth/me')
        setUsername(me.username)
        setState('authenticated')
      } else setState('anonymous')
    } catch (e) {
      setState(e instanceof NetworkError ? 'unreachable' : 'anonymous')
    }
  }, [])

  useEffect(() => {
    void boot()
  }, [boot])

  useEffect(() => {
    setAuthLostHandler(() => {
      setAccessToken(null)
      qc.clear()
      setState('anonymous')
    })
    return () => setAuthLostHandler(null)
  }, [qc])

  const login = useCallback(async (u: string, p: string) => {
    const r = await api<{ access_token: string; username: string }>('/auth/login', { method: 'POST', auth: false, body: { username: u, password: p, client: 'web' } })
    setAccessToken(r.access_token)
    setUsername(r.username)
    setState('authenticated')
  }, [])

  const setup = useCallback(
    async (u: string, p: string, token?: string) => {
      await api('/auth/setup', { method: 'POST', auth: false, body: { username: u, password: p, setup_token: token || null } })
      await login(u, p)
    },
    [login],
  )

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST', auth: false, body: {} })
    } catch {
      /* even if the server is unreachable, drop local state */
    }
    setAccessToken(null)
    qc.clear()
    setUsername(null)
    setState('anonymous')
  }, [qc])

  const value = useMemo(() => ({ state, username, retry: boot, login, setup, logout, setupTokenRequired }), [state, username, boot, login, setup, logout, setupTokenRequired])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): Ctx {
  const c = useContext(AuthContext)
  if (!c) throw new Error('useAuth outside AuthProvider')
  return c
}
