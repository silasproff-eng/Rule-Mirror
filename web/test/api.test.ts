import { describe, expect, it, vi } from 'vitest'

import { API_BASE_PATH, ApiError, LunaApiClient } from '../src/api'

describe('LunaApiClient', () => {
  it('uses the same-origin API base and typed authorization header', async () => {
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify({ id: 'run-1', status: 'queued' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    const client = new LunaApiClient(fetcher as typeof fetch)
    await client.createAnalysis({ trade_id: 'trade-1' }, 'access-token')
    expect(API_BASE_PATH).toBe('/api/v1')
    expect(fetcher).toHaveBeenCalledWith(
      '/api/v1/analysis-runs',
      expect.objectContaining({ method: 'POST' }),
    )
    const request = (fetcher.mock.calls[0] as unknown as [RequestInfo, RequestInit])[1]
    expect(new Headers(request.headers).get('Authorization')).toBe('Bearer access-token')
  })

  it('normalizes backend error envelopes', async () => {
    const fetcher = vi.fn(async () =>
      new Response(
        JSON.stringify({ detail: { code: 'trade_open', message: 'Trade is open' } }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    const client = new LunaApiClient(fetcher as typeof fetch)
    await expect(client.createAnalysis({ trade_id: 'trade-1' }, 'token')).rejects.toEqual(
      new ApiError('trade_open', 'Trade is open', 409),
    )
  })

  it('supports the authenticated opaque-handle profile endpoint', async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ username: 'member-ab12cd34', public_profile: false, display_name: null, metrics: {} }), { status: 200 }))
    const client = new LunaApiClient(fetcher as typeof fetch)
    await client.ownProfile('token')
    expect(fetcher).toHaveBeenCalledWith('/api/v1/account/profile', expect.objectContaining({ headers: expect.any(Headers), signal: expect.any(AbortSignal) }))
  })

  it('handles refresh rotation and empty logout responses', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
    const client = new LunaApiClient(fetcher as typeof fetch)
    await expect(client.refresh('old-refresh')).resolves.toEqual({ access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' })
    await expect(client.logout('new-refresh')).resolves.toBeUndefined()
    expect(fetcher).toHaveBeenNthCalledWith(2, '/api/v1/auth/logout', expect.objectContaining({ method: 'POST' }))
  })

  it('returns a typed error for a non-json response', async () => {
    const fetcher = vi.fn(async () => new Response('upstream unavailable', { status: 502 }))
    const client = new LunaApiClient(fetcher as typeof fetch)
    await expect(client.createAnalysis({ trade_id: 'trade-1' }, 'token')).rejects.toEqual(
      new ApiError('invalid_response', 'The service returned an unreadable response.', 502),
    )
  })

  it('turns an aborted deadline into a retryable timeout error', async () => {
    const fetcher = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    }))
    const client = new LunaApiClient(fetcher as typeof fetch, 1)
    await expect(client.createAnalysis({ trade_id: 'trade-1' }, 'token')).rejects.toEqual(
      new ApiError('network_timeout', 'The request timed out. Check your connection and try again.', 408),
    )
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('forwards caller cancellation to the request without retrying', async () => {
    const caller = new AbortController()
    const fetcher = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    }))
    const client = new LunaApiClient(fetcher as typeof fetch, 1_000)
    const request = (client as unknown as { request: (path: string, init: RequestInit) => Promise<unknown> }).request('/health', { signal: caller.signal })
    caller.abort()
    await expect(request).rejects.toThrow('Aborted')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })
})
