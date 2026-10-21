import { vi } from 'vitest'
import { api, ApiError, NetworkError, setAccessToken } from '../api/client'

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

afterEach(() => { vi.unstubAllGlobals(); setAccessToken(null) })

describe('api client', () => {
  it('never persists the access token in web storage', async () => {
    const f = vi.fn().mockResolvedValue(json(200, {}))
    vi.stubGlobal('fetch', f)
    setAccessToken('secret-token')
    await api('/overview')
    expect(f.mock.calls[0][1].headers.Authorization).toBe('Bearer secret-token')
    expect(JSON.stringify({ ...localStorage })).not.toContain('secret-token')
    expect(JSON.stringify({ ...sessionStorage })).not.toContain('secret-token')
  })

  it('on 401 refreshes once (single-flight, with CSRF header) and retries', async () => {
    let refreshes = 0
    const f = vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith('/auth/refresh')) {
        refreshes++
        expect((init!.headers as Record<string, string>)['X-Requested-With']).toBe('hlcc')
        await new Promise((r) => setTimeout(r, 10))
        return json(200, { access_token: 'new' })
      }
      const auth = (init!.headers as Record<string, string>).Authorization
      return auth === 'Bearer new' ? json(200, { ok: 1 }) : json(401, { error: { code: 'unauthorized', message: 'x' } })
    })
    vi.stubGlobal('fetch', f)
    setAccessToken('expired')
    const [a, b] = await Promise.all([api('/a'), api('/b')])
    expect(a).toEqual({ ok: 1 }); expect(b).toEqual({ ok: 1 })
    expect(refreshes).toBe(1)
  })

  it('when refresh fails the auth-lost handler fires and the error is surfaced', async () => {
    const { setAuthLostHandler } = await import('../api/client')
    const lost = vi.fn()
    setAuthLostHandler(lost)
    vi.stubGlobal('fetch', vi.fn(async () => json(401, { error: { code: 'invalid_refresh_token', message: 'Invalid refresh token' } })))
    setAccessToken('expired')
    await expect(api('/overview')).rejects.toBeInstanceOf(ApiError)
    expect(lost).toHaveBeenCalled()
    setAuthLostHandler(null)
  })

  it('maps fetch failure to NetworkError and parses error envelopes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(api('/x')).rejects.toBeInstanceOf(NetworkError)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(422, { error: { code: 'validation_error', message: 'bad', details: [{ field: 'name', message: 'req' }] } })))
    const e = await api('/x').catch((x) => x)
    expect(e).toMatchObject({ status: 422, code: 'validation_error', details: [{ field: 'name' }] })
  })
})
