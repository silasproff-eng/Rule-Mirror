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
})
