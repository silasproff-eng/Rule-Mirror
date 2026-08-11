import { describe, expect, it } from 'vitest'
import { formatActivityTime } from '../src/activity_time'

describe('activity timestamps', () => {
  it('renders a factual time from the server import timestamp', () => {
    const source = '2026-08-11T14:30:00+00:00'
    expect(formatActivityTime(source)).toBe(new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(source)))
    expect(formatActivityTime(source)).not.toBe('just now')
  })

  it('uses a neutral factual fallback when a legacy item has no timestamp', () => {
    expect(formatActivityTime(undefined)).toBe('Imported')
  })
})
