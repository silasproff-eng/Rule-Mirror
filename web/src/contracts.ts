export type TokenPair = {
  access_token: string
  refresh_token: string
  token_type: string
}

export type ApiIssue = {
  code: string
  message: string
  field?: string | null
  row?: number | null
}

export type ImportPreview = {
  detected_format?: 'canonical' | 'schwab_order_status' | 'schwab_transaction_ledger' | 'unknown' | 'positions_snapshot'
  ignored_nontrade_count?: number
  headers: string[]
  suggested_mapping: Record<string, string>
  validation_issues: ApiIssue[]
}

export type AccountProfile = {
  username: string
  email: string
  public_profile: boolean
  display_name: string | null
  metrics: {
    total_pnl: number | null
    return_percent: number | null
    win_rate: number | null
    discipline: number | null
    portfolio_value: number | null
    closed_trades: number
    reviewed_trades: number
  }
}

export type PortfolioHolding = {
  id: string
  source: string
  account_reference: string
  symbol: string
  description: string | null
  quantity: number
  price: number | null
  market_value: number | null
  cost_basis: number | null
  asset_type: string
  imported_at: string
}

export type PortfolioSummary = {
  portfolio_value: number | null
  holdings: PortfolioHolding[]
}

export type PortfolioImportResult = PortfolioSummary & {
  created: number
  updated: number
  holding_count: number
  imported_at: string
}

export type AffectedTrade = {
  trade_id: string
  trade_revision_id: string
  change_type: 'created' | 'updated'
  analysis_eligible: boolean
  symbol: string
  direction: 'long' | 'short'
  opened_at: string
  closed_at: string | null
}

export type ImportResult = {
  id: string
  status: string
  created_at: string
  accepted_execution_count: number
  affected_trade_count: number
  duplicate_count: number
  error_count: number
  affected_trades: AffectedTrade[]
  candidate_trades?: Array<{
    id: string
    trade_revision_id: string
    symbol: string
    direction: 'long' | 'short'
    opened_at: string
    closed_at: string | null
  }>
  trades?: Array<{
    id: string
    trade_revision_id: string
    symbol: string
    direction: 'long' | 'short'
    opened_at: string
    closed_at: string | null
  }>
}

export type ImportSummary = {
  id: string
  display_name: string
  status: string
  accepted_execution_count: number
  affected_trade_count: number
  duplicate_count: number
  error_count: number
  created_at: string
}

export type TradeHistory = AffectedTrade & {
  analyzed: boolean
  score: number | null
}

export type AnalysisRun = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  failure_code: string | null
  retryable: boolean
  retry_of_run_id: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  trade_analysis_id: string | null
}

export type AnalysisRunCreated = {
  id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  reused?: boolean
}

export type AnalysisRequest = {
  trade_id: string
  trade_revision_id?: string
  retry_of_run_id?: string
  strategy_slug?: string
}

export type TradeAnalysis = {
  id: string
  trade_id: string
  trade_revision_id: string
  symbol: string
  direction: 'long' | 'short'
  entry_time: string
  strategy: { slug: string; name: string; version: number }
  score: number | null
  data_sufficiency: 'sufficient' | 'insufficient'
  derived_context: Record<string, unknown>
  rules: RuleEvaluation[]
  feedback: FeedbackItem[]
  comparison: Comparison
}

export type RuleEvaluation = {
  rule: string
  label?: string
  result: 'PASS' | 'FAIL' | 'NOT_APPLICABLE' | 'INSUFFICIENT_DATA'
  measurement: string | null
  threshold: string | null
  weight: number
}

export type FeedbackItem = {
  rule: string
  category: 'matched' | 'missed' | 'review'
  sentence: string
}

export type Comparison = {
  status: string
  minimum: number
  available: number
  message: string
}
