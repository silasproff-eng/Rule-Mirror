import { describe, expect, it } from 'vitest'

describe('activity timestamps', () => {
  it('uses the server import timestamp instead of a relative placeholder', () => {
    const source = '2026-08-11T14:30:00+00:00'
    expect(new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(source))).not.toBe('just now')
  })
})
