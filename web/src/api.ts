import type {
  AnalysisRequest,
  AnalysisRun,
  ImportPreview,
  ImportResult,
  AnalysisRunCreated,
  AccountProfile,
  PortfolioImportResult,
  PortfolioSummary,
  TokenPair,
  TradeAnalysis,
  ImportSummary,
  TradeHistory,
} from './contracts'

export const API_BASE_PATH = '/api/v1'
export const DEFAULT_REQUEST_TIMEOUT_MS = 15000

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

type ErrorEnvelope = {
  detail?: {
    code?: string
    message?: string
  }
}

export class LunaApiClient {
  lastSearchWasLimited = false
  lastTradesWasLimited = false
  constructor(
    private readonly fetcher: typeof fetch = globalThis.fetch.bind(globalThis),
    private readonly timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  ) {}

  register(email: string, password: string): Promise<TokenPair> {
    return this.request('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  }

  login(email: string, password: string): Promise<TokenPair> {
    return this.request('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
  }

  preview(file: File, accessToken: string): Promise<ImportPreview> {
    const body = new FormData()
    body.append('file', file)
    return this.authorized('/imports/preview', accessToken, { method: 'POST', body })
  }

  importExecutions(
    file: File,
    mapping: Record<string, string>,
    timezone: string,
    accessToken: string,
  ): Promise<ImportResult> {
    const body = new FormData()
    body.append('file', file)
    body.append('mapping', JSON.stringify(mapping))
    body.append('timezone', timezone)
    return this.authorized('/imports', accessToken, { method: 'POST', body })
  }

  importHistory(accessToken: string): Promise<ImportSummary[]> {
    return this.authorized('/imports', accessToken)
  }

  tradeHistory(accessToken: string): Promise<TradeHistory[]> {
    this.lastTradesWasLimited = false
    return this.authorized('/trades', accessToken)
  }

  deleteTrade(tradeId: string, accessToken: string): Promise<void> {
    return this.authorized(`/trades/${encodeURIComponent(tradeId)}`, accessToken, { method: 'DELETE' }).then(() => undefined)
  }

  searchAccounts(query: string, accessToken: string): Promise<AccountProfile[]> {
    this.lastSearchWasLimited = false
    return this.authorized(`/accounts/search?q=${encodeURIComponent(query)}`, accessToken)
  }

  accountProfile(username: string, accessToken: string): Promise<AccountProfile> {
    return this.authorized(`/accounts/${encodeURIComponent(username)}`, accessToken)
  }

  ownProfile(accessToken: string): Promise<AccountProfile> {
    return this.authorized('/account/profile', accessToken)
  }

  updateProfile(displayName: string, accessToken: string): Promise<AccountProfile> {
    return this.authorized('/account/profile', accessToken, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ display_name: displayName }),
    })
  }

  portfolio(accessToken: string): Promise<PortfolioSummary> {
    return this.authorized('/portfolio', accessToken)
  }

  importPortfolio(file: File, accessToken: string): Promise<PortfolioImportResult> {
    const body = new FormData()
    body.append('file', file)
    return this.authorized('/portfolio/import', accessToken, { method: 'POST', body })
  }

  setPublicProfile(enabled: boolean, accessToken: string): Promise<{ public_profile: boolean; username: string }> {
    return this.authorized(`/account/public-profile?enabled=${enabled ? 'true' : 'false'}`, accessToken, { method: 'PUT' })
  }

  createAnalysis(request: AnalysisRequest, accessToken: string): Promise<AnalysisRunCreated> {
    return this.authorized('/analysis-runs', accessToken, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  }

  analysisRun(runId: string, accessToken: string): Promise<AnalysisRun> {
    return this.authorized(`/analysis-runs/${encodeURIComponent(runId)}`, accessToken)
  }

  tradeAnalysis(analysisId: string, accessToken: string): Promise<TradeAnalysis> {
    return this.authorized(`/trade-analyses/${encodeURIComponent(analysisId)}`, accessToken)
  }

  refresh(refreshToken: string): Promise<TokenPair> {
    return this.request('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
  }

  logout(refreshToken: string): Promise<void> {
    return this.request('/auth/logout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    }).then(() => undefined)
  }

  deleteAccount(accessToken: string): Promise<void> {
    return this.authorized('/account', accessToken, { method: 'DELETE' }).then(() => undefined)
  }

  private authorized<T>(path: string, accessToken: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers)
    headers.set('Authorization', `Bearer ${accessToken}`)
    return this.request(path, { ...init, headers })
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController()
    let timedOut = false
    const callerSignal = init.signal
    const forwardAbort = () => controller.abort()
    if (callerSignal?.aborted) controller.abort()
    else callerSignal?.addEventListener('abort', forwardAbort, { once: true })
    const timer = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, this.timeoutMs)
    let response: Response
    try {
      response = await this.fetcher(`${API_BASE_PATH}${path}`, { ...init, signal: controller.signal })
    } catch (error) {
      if (timedOut) throw new ApiError('network_timeout', 'The request timed out. Check your connection and try again.', 408)
      throw error
    } finally {
      clearTimeout(timer)
      callerSignal?.removeEventListener('abort', forwardAbort)
    }
    const raw = await response.text()
    let body: T | ErrorEnvelope = {} as T
    if (raw) {
      try {
        body = JSON.parse(raw) as T | ErrorEnvelope
      } catch {
        throw new ApiError('invalid_response', 'The service returned an unreadable response.', response.status)
      }
    }
    if (!response.ok) {
      const envelope = body as ErrorEnvelope
      throw new ApiError(
        envelope.detail?.code ?? 'request_failed',
        envelope.detail?.message ?? 'The request failed.',
        response.status,
      )
    }
    if (path.startsWith('/accounts/search')) this.lastSearchWasLimited = response.headers.get('X-Result-Limit') === '20'
    if (path === '/trades') this.lastTradesWasLimited = response.headers.get('X-Result-Limit') === '200'
    return body as T
  }
}
