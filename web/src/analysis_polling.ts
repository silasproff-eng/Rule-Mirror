export type PollableRun = { status: 'queued' | 'running' | 'completed' | 'failed' }

export async function pollAnalysisRun<T extends PollableRun>(load: () => Promise<T>, wait: (milliseconds: number) => Promise<void>, now: () => number = Date.now): Promise<T> {
  const deadline = now() + 30000
  let run = await load()
  let delay = 500
  while ((run.status === 'queued' || run.status === 'running') && now() < deadline) {
    await wait(Math.min(delay, Math.max(0, deadline - now())))
    run = await load()
    delay = Math.min(2000, delay + 500)
  }
  return run
}
