import { fmtAgo, fmtBytes, fmtDuration, fmtPercent, fmtRate, levelFor } from '../lib/format'

describe('format', () => {
  it('distinguishes zero from unavailable', () => {
    expect(fmtPercent(0)).toBe('0%')
    expect(fmtPercent(null)).toBe('—')
    expect(fmtPercent(undefined)).toBe('—')
    expect(fmtRate(0)).toBe('0 B/s')
    expect(fmtRate(null)).toBe('—')
    expect(fmtBytes(null)).toBe('—')
  })
  it('formats sizes and durations', () => {
    expect(fmtBytes(1536)).toBe('1.5 KB')
    expect(fmtBytes(5 * 1024 ** 3)).toBe('5.0 GB')
    expect(fmtDuration(90061)).toBe('1d 1h')
    expect(fmtDuration(null)).toBe('—')
  })
  it('relative time', () => {
    const now = Date.now()
    expect(fmtAgo(new Date(now - 90_000).toISOString(), now)).toBe('1m ago')
    expect(fmtAgo(null)).toBe('never')
  })
  it('levels', () => {
    expect(levelFor(50)).toBe('ok')
    expect(levelFor(90)).toBe('warn')
    expect(levelFor(99)).toBe('crit')
    expect(levelFor(null)).toBe('unknown')
  })
})
