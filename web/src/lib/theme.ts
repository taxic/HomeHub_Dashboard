export type ThemePref = 'dark' | 'light' | 'system'
const KEY = 'hlcc.theme'

export function storedTheme(): ThemePref {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'dark' || v === 'light' || v === 'system') return v
  } catch {
    /* storage may be blocked; fall back to the default */
  }
  return 'dark'
}

export function applyTheme(pref: ThemePref, persist = true) {
  const resolved = pref === 'system' ? (window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : pref
  document.documentElement.dataset.theme = resolved
  if (persist) {
    try {
      localStorage.setItem(KEY, pref)
    } catch {
      /* ignore */
    }
  }
}
