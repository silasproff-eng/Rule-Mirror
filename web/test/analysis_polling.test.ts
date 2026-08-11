import { describe, expect, it } from 'vitest'
import { pollAnalysisRun } from '../src/analysis_polling'

describe('pollAnalysisRun', () => {
  it('accepts completion after more than six seconds', async () => {
    let time = 0
    let calls = 0
    const run = await pollAnalysisRun(async () => ({ status: ++calls < 7 ? 'running' as const : 'completed' as const }), async (delay) => { time += delay }, () => time)
    expect(run.status).toBe('completed')
    expect(time).toBeGreaterThan(6000)
  })

  it('stops immediately on failure and does not poll again', async () => {
    let calls = 0
    const run = await pollAnalysisRun(async () => { calls += 1; return { status: 'failed' as const } }, async () => { throw new Error('should not wait') })
    expect(run.status).toBe('failed')
    expect(calls).toBe(1)
  })

  it('returns a pending run at the deadline', async () => {
    let time = 0
    const run = await pollAnalysisRun(async () => ({ status: 'queued' as const }), async (delay) => { time += delay }, () => time)
    expect(run.status).toBe('queued')
    expect(time).toBe(30000)
  })
})
