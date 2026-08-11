import './styles.css'
import { ApiError, LunaApiClient } from './api'
import type { AccountProfile, AffectedTrade, AnalysisRun, ImportPreview, ImportResult, ImportSummary, PortfolioHolding, PortfolioSummary, TradeAnalysis, TradeHistory } from './contracts'
import { STRATEGY_CATALOG } from './strategy_catalog'
import { pollAnalysisRun } from './analysis_polling'
import { formatActivityTime } from './activity_time'

type Page = 'overview' | 'portfolio' | 'analyze' | 'trades' | 'strategies' | 'insights' | 'profile' | 'account'
type Trade = AffectedTrade & { analyzed?: boolean; score?: number | null; quantity?: number | null; entry_price?: number | null; exit_price?: number | null; realized_pnl?: number | null; return_percent?: number | null }
type Tokens = { access_token: string; refresh_token: string }
type Profile = { name: string; timezone: string; avatar: string; theme: 'light' | 'dark' }

const mountElement = document.querySelector<HTMLDivElement>('#app')
if (!mountElement) throw new Error('RuleMirror mount point is missing')
const mount: HTMLDivElement = mountElement
mount.setAttribute('aria-live', 'polite')

const api = new LunaApiClient()
const state: {
  page: Page
  authMode: 'login' | 'register'
  tokens: Tokens | null
  email: string
  file: File | null
  preview: ImportPreview | null
  mapping: Record<string, string>
  imports: Array<ImportResult | ImportSummary>
  trades: Trade[]
  activeTrade: Trade | null
  analysis: TradeAnalysis | null
  run: AnalysisRun | null
  busy: string | null
  notice: { tone: 'success' | 'error' | 'info'; text: string } | null
  profile: { name: string; timezone: string; avatar: string; theme: 'light' | 'dark' }
  hydrated: boolean
  selectedStrategy: string
  publicProfile: boolean
  publicProfilePending: boolean
  portfolio: PortfolioSummary
  portfolioFile: File | null
  tradeSearch: string
  accountSearch: string
  accountResults: AccountProfile[]
  viewedAccount: AccountProfile | null
} = {
  page: 'overview',
  authMode: 'login',
  tokens: readTokens(),
  email: sessionStorage.getItem('rulemirror.email') ?? '',
  file: null,
  preview: null,
  mapping: {},
  imports: [],
  trades: [],
  activeTrade: null,
  analysis: null,
  run: null,
  busy: null,
  notice: null,
  profile: readProfile(),
  hydrated: false,
  selectedStrategy: 'vwap-reclaim',
  publicProfile: localStorage.getItem('rulemirror.public') === 'true',
  publicProfilePending: false,
  portfolio: { portfolio_value: null, holdings: [] },
  portfolioFile: null,
  tradeSearch: '',
  accountSearch: '',
  accountResults: [],
  viewedAccount: null,
}

let navTrigger: HTMLButtonElement | null = null
let refreshPromise: Promise<Tokens> | null = null

function readTokens(): Tokens | null {
  const raw = sessionStorage.getItem('rulemirror.tokens')
  if (!raw) return null
  try {
    const value = JSON.parse(raw) as Tokens
    return value.access_token && value.refresh_token ? value : null
  } catch {
    sessionStorage.removeItem('rulemirror.tokens')
    return null
  }
}

function readProfile(): Profile {
  const fallback: Profile = { name: '', timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC', avatar: '', theme: 'light' }
  const raw = localStorage.getItem('rulemirror.profile')
  if (!raw) return fallback
  try {
    const value = JSON.parse(raw) as Partial<Profile>
    return { ...fallback, ...value, theme: value.theme === 'dark' ? 'dark' : 'light' }
  } catch {
    return fallback
  }
}

function setNotice(text: string, tone: 'success' | 'error' | 'info' = 'info') {
  state.notice = { text, tone }
  render()
  window.setTimeout(() => {
    if (state.notice?.text === text) {
      state.notice = null
      render()
    }
  }, 4800)
}

function persistProfile() {
  localStorage.setItem('rulemirror.profile', JSON.stringify(state.profile))
}

function persistTokens(tokens: Tokens | null) {
  state.tokens = tokens
  if (tokens) sessionStorage.setItem('rulemirror.tokens', JSON.stringify(tokens))
  else sessionStorage.removeItem('rulemirror.tokens')
}

function clearSession() {
  persistTokens(null)
  sessionStorage.removeItem('rulemirror.email')
  state.email = ''
  state.imports = []
  state.trades = []
  state.activeTrade = null
  state.analysis = null
  state.run = null
  state.hydrated = false
}

function escape(value: string | number | null | undefined): string {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] ?? character)
}

function initials() {
  const source = state.profile.name || state.email || 'R'
  return source.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
}

function avatarView(account: Pick<AccountProfile, 'display_name' | 'username'> & { avatar?: string }, size = 'small') {
  const label = account.display_name || account.username
  const letters = label.split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase()
  return `<span class="avatar avatar-${size}">${account.avatar ? `<img src="${account.avatar}" alt="">` : escape(letters)}</span>`
}

function formatMoney(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  return `${value >= 0 ? '+' : ''}$${value.toFixed(2)}`
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  return `${value.toFixed(value % 1 ? 1 : 0)}%`
}

function accountResultView(account: AccountProfile) {
  return `<button class="account-result" type="button" data-account-username="${escape(account.username)}">${avatarView({ ...account, avatar: account.username === state.email ? state.profile.avatar : '' })}<span class="account-result-main"><strong>${escape(account.display_name || account.username)}</strong><small>${escape(account.username)}</small></span><span class="account-result-stats"><b>${formatMoney(account.metrics.portfolio_value)}</b><small>${formatMoney(account.metrics.total_pnl)} P/L · ${formatPercent(account.metrics.win_rate)} WR</small></span></button>`
}

function formatDate(value: string | null | undefined) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value))
}

function scoreTone(score: number | null | undefined) {
  if (score === null || score === undefined) return 'neutral'
  if (score >= 80) return 'positive'
  if (score >= 60) return 'watch'
  return 'negative'
}

function scoreRing(score: number | null | undefined, label: string, compact = false) {
  const value = score === null || score === undefined ? 0 : Math.max(0, Math.min(100, score))
  const display = score === null || score === undefined ? '—' : String(Math.round(score))
  return `<div class="score-ring ${scoreTone(score)} ${compact ? 'compact' : ''}" style="--score:${value}" role="img" aria-label="${escape(label)}: ${escape(display)} out of 100"><div class="score-ring__inner"><strong>${display}</strong><span>/ 100</span></div></div>`
}

function icon(name: string) {
  const paths: Record<string, string> = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    upload: '<path d="M12 16V4m0 0L7 9m5-5 5 5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><path d="M3 6h.01M3 12h.01M3 18h.01"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
    compass: '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2.3 4.7-4.7 2.3 2.3-4.7 4.7-2.3Z"/>',
    user: '<circle cx="12" cy="8" r="3"/><path d="M5 20a7 7 0 0 1 14 0"/>',
    settings: '<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z"/><path d="m19.4 15 .1.1a2 2 0 1 1-2.8 2.8l-.1-.1a2 2 0 0 0-3.4 1.4v.2a2 2 0 1 1-4 0v-.2a2 2 0 0 0-3.4-1.4l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A2 2 0 0 0 3.7 12a2 2 0 0 0-.7-1.4l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A2 2 0 0 0 9.2 6.4h.2a2 2 0 1 1 4 0h.2a2 2 0 0 0 3.4 1.4l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a2 2 0 0 0 0 2.8l.1.1Z"/>',
    chevron: '<path d="m9 18 6-6-6-6"/>',
    arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    lock: '<rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
    briefcase: '<path d="M10 6V5a2 2 0 0 1 2-2h0a2 2 0 0 1 2 2v1"/><rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 12h18"/>',
    moon: '<path d="M20 15.5A8 8 0 0 1 8.5 4 8 8 0 1 0 20 15.5Z"/>',
    logout: '<path d="M10 17l5-5-5-5M15 12H3"/><path d="M21 19V5a2 2 0 0 0-2-2h-5"/>',
    trash: '<path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  }
  return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] ?? paths.grid}</svg>`
}

function logo() {
  return '<img class="brand-logo" src="/rulemirror-logo.png" alt="RuleMirror">'
}

function mascotState() {
  if (state.busy === 'preview' || state.busy === 'import' || state.busy === 'analyze') return 'thinking'
  if (state.analysis?.score === null) return 'warning'
  if (state.analysis) return 'success'
  if (state.notice?.tone === 'error') return 'error'
  return 'idle'
}

function authView() {
  const register = state.authMode === 'register'
  return `<main class="auth-layout"><section class="auth-story"><div class="brand-line">${logo()}</div><div class="story-content"><p class="eyebrow">A clearer record of your decisions</p><h1>Review the trade.<br><em>Keep the lesson.</em></h1><p class="story-copy">RuleMirror reconstructs your real executions against a consistent set of rules, so your process gets easier to see over time.</p><div class="story-note"><span class="note-dot"></span><span>Private by default. Built for reflection, not prediction.</span></div></div><div class="story-footer">Strategy adherence analytics · v0.1 foundation</div></section><section class="auth-panel"><div class="auth-card"><div class="mobile-brand">${logo()}</div><p class="eyebrow">${register ? 'Create your workspace' : 'Welcome back'}</p><h2>${register ? 'Start with your process.' : 'Sign in to continue.'}</h2><p class="muted">${register ? 'Your first review starts with one clean CSV export.' : 'Your data and notes stay tied to your account.'}</p><form id="auth-form" class="form-stack"><label>Email address<input name="email" type="email" autocomplete="email" required value="${escape(state.email)}" placeholder="you@example.com"></label><label>Password<input name="password" type="password" minlength="12" autocomplete="${register ? 'new-password' : 'current-password'}" required placeholder="At least 12 characters"></label>${register ? '<label class="check-line"><input name="terms" type="checkbox" required><span>I agree to the <a href="/terms.html" target="_blank">Terms</a> and <a href="/privacy.html" target="_blank">Privacy Policy</a>, and understand RuleMirror is analytics—not financial advice.</span></label>' : ''}<button class="button button-primary button-wide" type="submit" ${state.busy ? 'disabled' : ''}>${state.busy ? 'Working…' : register ? 'Create account' : 'Sign in'} ${icon('arrow')}</button></form><button class="text-button" id="auth-toggle" type="button">${register ? 'Already have an account? Sign in' : 'New here? Create an account'}</button><p class="form-footnote">By using RuleMirror, you agree to the <a href="/terms.html">Terms of Service</a> and <a href="/privacy.html">Privacy Policy</a>. No card required.</p></div></section></main>${noticeView()}`
}

function noticeView() {
  if (!state.notice) return ''
  return `<div class="toast toast-${state.notice.tone}" role="status">${state.notice.tone === 'success' ? icon('check') : ''}<span>${escape(state.notice.text)}</span><button type="button" id="dismiss-notice" aria-label="Dismiss">×</button></div>`
}

function navItem(page: Page, label: string, glyph: string) {
  return `<button class="nav-item ${state.page === page ? 'active' : ''}" data-page="${page}" type="button">${icon(glyph)}<span>${label}</span></button>`
}

function shellView() {
  const accounts = `<div class="account-results" id="account-results">${state.accountResults.map(accountResultView).join('')}</div>`
  return `<div class="app-shell"><aside class="sidebar" id="sidebar"><div class="sidebar-head"><div class="brand-line">${logo()}</div><button class="sidebar-close" id="close-nav" type="button" aria-label="Close navigation">×</button></div><div class="workspace-pill"><span class="avatar avatar-small">${state.profile.avatar ? `<img src="${state.profile.avatar}" alt="">` : initials()}</span><span><strong>${escape(state.profile.name || 'Your workspace')}</strong><small>Personal workspace</small></span></div><nav class="primary-nav" aria-label="Primary navigation">${navItem('overview', 'Overview', 'grid')}${navItem('portfolio', 'My portfolio', 'briefcase')}${navItem('analyze', 'Analyze', 'upload')}${navItem('trades', 'Trades', 'list')}${navItem('strategies', 'Strategies', 'layers')}${navItem('insights', 'Insights', 'compass')}</nav><div class="sidebar-bottom"><button class="nav-item ${state.page === 'profile' ? 'active' : ''}" data-page="profile" type="button">${icon('user')}<span>Profile & settings</span></button><div class="sidebar-rule"></div><button class="nav-item" id="sign-out" type="button">${icon('logout')}<span>Sign out</span></button><p class="sidebar-meta">RuleMirror v0.1<br><span>Analytics, not advice.</span></p></div></aside><div class="mobile-overlay" id="mobile-overlay"></div><section class="main-column"><header class="topbar"><button class="menu-button" id="open-nav" type="button" aria-label="Open navigation" aria-controls="sidebar" aria-expanded="false">☰</button><div class="breadcrumb"><span>Workspace</span>${state.page !== 'overview' ? `<b>/</b><strong>${pageTitle(state.page)}</strong>` : ''}</div><div class="topbar-actions"><form class="account-search-wrap" id="account-search-form"><input id="account-search" type="search" placeholder="Search usernames by email" value="${escape(state.accountSearch)}" aria-label="Search public usernames by email"><button type="submit" class="search-submit">Search</button>${accounts}</form><button class="icon-button" id="theme-toggle" type="button" aria-label="Toggle theme">${icon('moon')}</button><button class="avatar avatar-small" data-page="profile" type="button" aria-label="Open profile">${state.profile.avatar ? `<img src="${state.profile.avatar}" alt="">` : initials()}</button></div></header><main class="content">${pageView()}</main></section></div>${noticeView()}`
}

function pageTitle(page: Page) {
  return ({ overview: 'Overview', portfolio: 'My portfolio', analyze: 'Analyze', trades: 'Trades', strategies: 'Strategies', insights: 'Insights', profile: 'Profile & settings', account: 'Profile' })[page]
}

function pageView() {
  if (state.page === 'overview') return overviewView()
  if (state.page === 'portfolio') return portfolioView()
  if (state.page === 'analyze') return analyzeView()
  if (state.page === 'trades') return tradesView()
  if (state.page === 'strategies') return strategiesView()
  if (state.page === 'insights') return insightsView()
  if (state.page === 'account') return accountView()
  return profileView()
}

function accountView() {
  if (!state.viewedAccount) return `${pageHeader('Public profile', 'Profile unavailable', 'Choose a profile from search to view its public information.', '')}`
  const account = state.viewedAccount
  return `${pageHeader('Public profile', escape(account.display_name || account.username), account.public_profile ? 'This member has chosen to publish summary performance metrics. Private trades and account information are not shared.' : 'This is your private profile.', '')}<section class="panel profile-card"><div class="profile-heading">${avatarView(account, 'large')}<div><p class="eyebrow">RuleMirror profile</p><h2>${escape(account.display_name || account.username)}</h2><p>${escape(account.username)}</p></div></div><section class="metric-grid public-profile-metrics"><article class="metric-card"><span class="metric-label">P/L</span><strong class="metric-value ${account.metrics.total_pnl !== null && account.metrics.total_pnl < 0 ? 'negative-value' : ''}">${formatMoney(account.metrics.total_pnl)}</strong><span class="metric-foot">${account.metrics.closed_trades} closed trade${account.metrics.closed_trades === 1 ? '' : 's'}</span></article><article class="metric-card"><span class="metric-label">Win rate</span><strong class="metric-value">${formatPercent(account.metrics.win_rate)}</strong><span class="metric-foot">Closed realized trades</span></article><article class="metric-card"><span class="metric-label">Discipline</span><div class="metric-score">${scoreRing(account.metrics.discipline, 'Discipline score', true)}<span>${account.metrics.reviewed_trades ? `${account.metrics.reviewed_trades} reviewed` : 'No reviews yet'}</span></div></article></section></section>`
}

function pageHeader(eyebrow: string, title: string, copy: string, action = '') {
  return `<div class="page-header"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p class="page-copy">${copy}</p></div>${action}</div>`
}

function selectedStrategyName() {
  return state.selectedStrategy === 'vwap-reclaim' ? 'VWAP Reclaim' : STRATEGY_CATALOG.find((strategy) => strategy.name.toLowerCase().replace(/[^a-z0-9]+/g, '-') === state.selectedStrategy)?.name ?? 'Selected strategy'
}

function overviewView() {
  const analyzed = state.trades.filter((trade) => trade.analyzed)
  const average = analyzed.length ? analyzed.reduce((total, trade) => total + (trade.score ?? 0), 0) / analyzed.length : null
  const closed = state.trades.filter((trade) => trade.closed_at && trade.realized_pnl !== null && trade.realized_pnl !== undefined)
  const totalPnl = closed.length ? closed.reduce((total, trade) => total + (trade.realized_pnl ?? 0), 0) : null
  const winRate = closed.length ? closed.filter((trade) => (trade.realized_pnl ?? 0) > 0).length / closed.length * 100 : null
  return `${pageHeader('Your workspace', `Good to see you${state.profile.name ? `, ${escape(state.profile.name.split(' ')[0])}` : ''}.`, 'A calm view of what your execution data can teach you.', `<button class="button button-primary" data-page="analyze">${icon('upload')} Analyze trades</button>`)}<section class="metric-grid"><article class="metric-card"><span class="metric-label">Total profit / loss</span><strong class="metric-value ${totalPnl === null ? 'muted-value' : totalPnl < 0 ? 'negative-value' : ''}">${formatMoney(totalPnl)}</strong><span class="metric-foot">${closed.length ? `${closed.length} closed trade${closed.length === 1 ? '' : 's'} · net fees included` : 'Close a trade to calculate'}</span></article><article class="metric-card"><span class="metric-label">Win rate</span><strong class="metric-value ${winRate === null ? 'muted-value' : ''}">${formatPercent(winRate)}</strong><span class="metric-foot">${closed.length ? 'Closed realized trades' : 'Close a trade to calculate'}</span></article><article class="metric-card"><span class="metric-label">Discipline score</span><div class="metric-score">${scoreRing(average, 'Discipline score', true)}<span>${analyzed.length ? `${analyzed.length} analyzed` : 'Awaiting first analysis'}</span></div></article><article class="metric-card metric-card-accent"><span class="metric-label">Current strategy</span><strong class="metric-value">${escape(selectedStrategyName())}</strong><span class="metric-foot">Version 1 · deterministic rules</span></article></section><section class="overview-grid"><article class="panel panel-large"><div class="panel-heading"><div><p class="eyebrow">The review loop</p><h2>Turn a fill into a feedback loop.</h2></div><span class="panel-index">01 — 03</span></div><div class="loop-grid"><div class="loop-step"><span>01</span><div><strong>Import</strong><p>Bring a CSV export from your broker. Nothing is shared publicly.</p></div></div><div class="loop-step"><span>02</span><div><strong>Reconstruct</strong><p>Executions are grouped into trades with revisions you can trace.</p></div></div><div class="loop-step"><span>03</span><div><strong>Review</strong><p>See how one explicit rule set matched the decisions you made.</p></div></div></div><button class="inline-link" data-page="analyze">Start with an import ${icon('arrow')}</button></article><article class="panel"><div class="panel-heading"><div><p class="eyebrow">Recent activity</p><h2>${state.imports.length ? 'Your latest imports' : 'Your workspace is ready'}</h2></div>${state.imports.length ? `<span class="status-dot">${state.imports.length}</span>` : ''}</div>${state.imports.length ? `<div class="activity-list">${state.imports.slice(-3).reverse().map((item) => `<div class="activity-row"><span class="activity-icon">${icon('upload')}</span><div><strong>${escape(item.id.slice(0, 8))}…</strong><small>${item.accepted_execution_count} executions · ${item.affected_trade_count} trades</small></div><span class="activity-date">${formatActivityTime(item.created_at)}</span></div>`).join('')}</div>` : `<div class="empty-copy"><span class="empty-mark">＋</span><p>Your first import will appear here with accepted executions, duplicates, and reconstructed trades.</p><button class="inline-link" data-page="analyze">Import a CSV ${icon('arrow')}</button></div>`}</article></section><section class="trust-strip"><div>${icon('lock')}<span><strong>Private by default</strong> Your account data is scoped to you.</span></div><div>${icon('compass')}<span><strong>Evidence over opinion</strong> Feedback is generated from explicit rules.</span></div><div>${icon('layers')}<span><strong>Revision-aware</strong> Imported changes never erase history.</span></div></section>`
}

function portfolioView() {
  const holdings = state.portfolio.holdings
  const bySource = Array.from(holdings.reduce((map, holding) => map.set(holding.source, (map.get(holding.source) ?? 0) + (holding.market_value ?? 0)), new Map<string, number>()))
  return `${pageHeader('My portfolio', 'All holdings in one place.', 'Import holdings snapshots and purchase-history CSVs. These holdings are not used for strategy scoring.', '')}<section class="metric-grid profile-metrics"><article class="metric-card"><span class="metric-label">Portfolio value</span><strong class="metric-value">${formatMoney(state.portfolio.portfolio_value)}</strong><span class="metric-foot">${holdings.length} holding${holdings.length === 1 ? '' : 's'} imported</span></article><article class="metric-card"><span class="metric-label">Sources</span><strong class="metric-value">${bySource.length || '—'}</strong><span class="metric-foot">${bySource.map(([source]) => source).join(', ') || 'Upload a holdings CSV'}</span></article><article class="metric-card"><span class="metric-label">Public profile</span><strong class="metric-value">${state.publicProfile ? 'On' : 'Off'}</strong><span class="metric-foot">Shares summary metrics: portfolio value, P/L, win rate, and discipline</span></article></section><section class="portfolio-layout"><article class="panel"><div class="panel-heading"><div><p class="eyebrow">Import holdings</p><h2>Upload a portfolio CSV.</h2></div></div><label class="dropzone compact-dropzone" for="portfolio-file"><input id="portfolio-file" type="file" accept=".csv,text/csv"><span class="drop-icon">${icon('upload')}</span><strong>${state.portfolioFile ? escape(state.portfolioFile.name) : 'Choose a holdings CSV'}</strong><span>${state.portfolioFile ? `${Math.round(state.portfolioFile.size / 1024)} KB ready` : 'Holdings snapshots stay separate from trade analysis'}</span></label><div class="import-foot"><span>CSV only · 2 MB maximum</span><button class="button button-primary" id="import-portfolio" type="button" ${state.portfolioFile && !state.busy ? '' : 'disabled'}>Import portfolio ${icon('arrow')}</button></div></article><article class="panel"><div class="panel-heading"><div><p class="eyebrow">Breakdown</p><h2>${holdings.length ? 'Current snapshots' : 'No holdings yet'}</h2></div></div>${holdings.length ? `<div class="holding-list">${holdings.map(holdingRow).join('')}</div>` : `<div class="table-empty"><span class="empty-mark">◌</span><h3>Your holdings will appear here.</h3><p>Upload a holdings or purchase-history report to build a combined portfolio view.</p></div>`}</article></section>`
}

function holdingRow(holding: PortfolioHolding) {
  return `<div class="holding-row"><div><strong>${escape(holding.symbol)}</strong><small>${escape(holding.description || holding.source)}</small></div><span>${holding.quantity.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span><span>${holding.price === null ? '—' : `$${holding.price.toFixed(2)}`}</span><b>${formatMoney(holding.market_value)}</b></div>`
}

function analyzeView() {
  if (state.analysis) return analysisResultView()
  const eligible = state.trades.filter((trade) => trade.closed_at)
  const preview = state.preview
  return `${pageHeader('Analysis workspace', 'See the decision clearly.', 'Start with a CSV export. RuleMirror maps executions, reconstructs trades, and evaluates one deterministic strategy.', '')}<div class="analysis-layout"><section class="panel import-panel"><div class="stepper"><span class="step active">01 <b>Import</b></span><span class="step ${preview ? 'active' : ''}">02 <b>Map</b></span><span class="step ${state.activeTrade ? 'active' : ''}">03 <b>Review</b></span></div>${state.busy === 'preview' ? '<div class="progress-note"><span class="spinner"></span>Reading your export…</div>' : ''}${!preview ? uploadView() : mappingView()}</section><aside class="panel context-panel"><p class="eyebrow">What happens next</p><h2>A small, traceable loop.</h2><div class="context-list"><div><span>1</span><p><strong>Preview first</strong><br>We inspect headers before accepting anything.</p></div><div><span>2</span><p><strong>Map once</strong><br>Confirm the fields and your timezone.</p></div><div><span>3</span><p><strong>Analyze a trade</strong><br>Choose a closed trade for a VWAP Reclaim review.</p></div></div><div class="privacy-callout">${icon('lock')}<p>We never turn your executions into signals or recommendations.</p></div></aside></div>${eligible.length ? `<section class="panel selection-panel"><div class="panel-heading"><div><p class="eyebrow">Ready for review</p><h2>${eligible.length} closed trade${eligible.length === 1 ? '' : 's'} available</h2></div><span class="panel-index">Select one</span></div><div class="trade-select-list">${eligible.slice(-6).map((trade) => tradeRow(trade)).join('')}</div></section>` : ''}`
}

function uploadView() {
  return `<div class="upload-copy"><p class="eyebrow">Step 01</p><h2>Bring in your executions.</h2><p>Use a CSV from your broker or trading platform. A header row and execution time are required.</p></div><label class="dropzone" for="csv-file" id="dropzone"><input id="csv-file" type="file" accept=".csv,text/csv"><span class="drop-icon">${icon('upload')}</span><strong>${state.file ? escape(state.file.name) : 'Drop a CSV here'}</strong><span>${state.file ? `${Math.round(state.file.size / 1024)} KB ready to preview` : 'or choose a file from your computer'}</span></label><div class="import-foot"><span>CSV only · 2 MB maximum</span><button class="button button-primary" id="preview-file" type="button" ${state.file && !state.busy ? '' : 'disabled'}>Preview file ${icon('arrow')}</button></div>`
}

function mappingView() {
  const formatLabel = state.preview?.detected_format === 'schwab_order_status' ? '<div class="privacy-callout">Order status export detected. Fill price, filled quantity, last activity time, and order number were mapped automatically.</div>' : ''
  if (state.preview?.detected_format === 'schwab_transaction_ledger') {
    return `<div class="upload-copy"><p class="eyebrow">Date-only transaction ledger</p><h2>Use an execution export for review.</h2><p>This file contains calendar dates, not execution times. RuleMirror will not invent midnight timestamps, so minute-level VWAP and timing review is unavailable from this file.</p>${state.preview.ignored_nontrade_count ? `<div class="issue-box"><p>${state.preview.ignored_nontrade_count} non-trade ledger row${state.preview.ignored_nontrade_count === 1 ? '' : 's'} will be ignored.</p></div>` : ''}<div class="privacy-callout">Export account activity or executions with a timestamp, side, quantity, and price, then choose that file here.</div></div><div class="import-foot"><button class="text-button" id="reset-import" type="button">Choose another export</button></div>`
  }
  const fields = ['symbol', 'side', 'quantity', 'price', 'executed_at']
  if (state.preview?.detected_format === 'positions_snapshot') {
    return `<div class="upload-copy"><p class="eyebrow">Positions snapshot detected</p><h2>These are current holdings, not executions.</h2><p>RuleMirror recognized a positions export, including symbols, quantities, market value, and cost basis. It will not invent entry times or buy/sell history from a snapshot.</p></div><div class="issue-box"><p>Export <strong>History</strong>, <strong>Transactions</strong>, or <strong>Account activity</strong> CSV data with action, quantity, price, and execution time to analyze trades.</p></div><div class="import-foot"><button class="button button-secondary" id="reset-import" type="button">Choose a transaction export</button></div>`
  }
  return `<div class="upload-copy"><p class="eyebrow">Step 02</p><h2>Confirm the field map.</h2><p>We suggested a match from your header row. Check the required fields before importing.</p>${formatLabel}</div><div class="mapping-list">${fields.map((field) => `<label><span>${field.replace('_', ' ')}</span><select data-map-field="${field}"><option value="">Choose a column</option>${(state.preview?.headers ?? []).map((header) => `<option value="${escape(header)}" ${state.mapping[field] === header ? 'selected' : ''}>${escape(header)}</option>`).join('')}</select></label>`).join('')}</div>${state.preview?.validation_issues.length ? `<div class="issue-box">${state.preview.validation_issues.map((issue) => `<p>${escape(issue.message)}</p>`).join('')}</div>` : ''}<label class="timezone-field"><span>Timezone for timestamps</span><select id="timezone"><option value="${escape(state.profile.timezone)}">${escape(state.profile.timezone)}</option><option value="America/New_York">America/New_York</option><option value="America/Chicago">America/Chicago</option><option value="America/Los_Angeles">America/Los_Angeles</option><option value="UTC">UTC</option></select></label><div class="import-foot"><button class="text-button" id="reset-import" type="button">Choose another file</button><button class="button button-primary" id="import-file" type="button" ${state.busy || !state.file ? 'disabled' : ''}>Import executions ${icon('arrow')}</button></div>`
}

function tradeRow(trade: Trade, showDelete = false) {
  const actionAttributes = trade.analysis_eligible ? `data-trade-id="${trade.trade_id}" aria-label="Review ${escape(trade.symbol)} trade"` : 'disabled aria-label="Trade is not ready for review"'
  const erase = showDelete ? `<span class="trade-delete" data-delete-trade="${trade.trade_id}" role="button" tabindex="0" aria-label="Erase ${escape(trade.symbol)} trade">${icon('trash')} Erase trade</span>` : ''
  return `<button class="trade-row ${showDelete ? 'trade-row-with-delete' : ''} ${state.activeTrade?.trade_id === trade.trade_id ? 'selected' : ''}" type="button" ${actionAttributes}><span class="trade-symbol">${escape(trade.symbol)}</span><span class="trade-direction direction-${trade.direction}">${trade.direction}</span><span>${formatDate(trade.opened_at)}</span><span>${trade.closed_at ? formatDate(trade.closed_at) : 'Open'}</span><span class="trade-state">${trade.analyzed ? 'Reviewed' : trade.analysis_eligible ? 'Ready' : 'Needs close'} ${trade.analysis_eligible ? icon('chevron') : ''}</span>${erase}</button>`
}

function tradesView() {
  const visibleTrades = state.trades.filter((trade) => !state.tradeSearch || trade.symbol.toLowerCase().includes(state.tradeSearch.toLowerCase()))
  return `${pageHeader('Trade history', 'The source record.', 'Every row comes from an imported execution set. Review status stays separate from performance claims.', `<button class="button button-primary" data-page="analyze">${icon('upload')} Import trades</button>`)}<section class="panel table-panel"><div class="table-toolbar"><div><p class="eyebrow">All reconstructed trades</p><h2>${state.trades.length ? `${state.trades.length} trade${state.trades.length === 1 ? '' : 's'}` : 'No trades yet'}</h2></div><input id="trade-search" type="search" placeholder="Search symbol" value="${escape(state.tradeSearch)}"><span class="filter-pill">${state.trades.filter((trade) => trade.closed_at).length} closed</span></div>${state.trades.length ? `<div class="trade-table"><div class="trade-head"><span>Symbol</span><span>Side</span><span>Opened</span><span>Closed</span><span>Status</span></div>${visibleTrades.map((trade) => tradeRow(trade, true)).join('')}</div>` : `<div class="table-empty"><span class="empty-mark">◌</span><h3>Your trade history will take shape here.</h3><p>Import an execution CSV to reconstruct closed and open trades without losing the original record.</p><button class="inline-link" data-page="analyze">Import your first CSV ${icon('arrow')}</button></div>`}</section>`
}

function strategiesView() {
  const cards = STRATEGY_CATALOG.map((strategy) => { const slug = strategy.name.toLowerCase().replace(/[^a-z0-9]+/g, '-'); return `<article class="strategy-card catalog-card ${state.selectedStrategy === slug ? 'active-strategy' : ''}"><div class="strategy-card-top"><span class="strategy-icon muted">${escape(strategy.name.slice(0, 1))}</span><span class="tag">Default profile</span></div><p class="eyebrow">${escape(strategy.family)}</p><h2>${escape(strategy.name)}</h2><p>${escape(strategy.summary)}</p><button class="button button-secondary strategy-select" data-strategy="${slug}" type="button">${state.selectedStrategy === slug ? 'Selected' : 'Select for review'}</button></article>` }).join('')
  return `${pageHeader('Strategy library', 'One rule set at a time.', 'Every strategy uses a visible, versioned default rule profile against completed historical bars. Missing required context is reported as insufficient data—not a prediction.', '')}<section class="strategy-grid"><article class="strategy-card active-strategy"><div class="strategy-card-top"><span class="strategy-icon">V</span><span class="tag tag-active">Active</span></div><p class="eyebrow">Built-in strategy · v1</p><h2>VWAP Reclaim</h2><p>Checks completed-bar VWAP reclaim, EMA alignment, relative volume, entry timing, and extension.</p><div class="rule-chips"><span>VWAP</span><span>EMA 9 / 20</span><span>RVOL</span><span>Timing</span></div><button class="inline-link" data-page="analyze">Run a review ${icon('arrow')}</button></article><article class="strategy-card locked-strategy"><div class="strategy-card-top"><span class="strategy-icon muted">＋</span><span class="tag">Coming later</span></div><p class="eyebrow">Your library</p><h2>Custom strategy</h2><p>Define a reviewable rule set after the foundation is proven. No black-box scoring.</p><div class="locked-line">${icon('lock')} Custom rules are not available yet.</div></article>${cards}</section><section class="panel philosophy-panel"><div><p class="eyebrow">Design principle</p><h2>Useful restraint creates trust.</h2></div><p>Scores are only as defensible as the context behind them. RuleMirror keeps the strategy definition visible, the evidence bounded, and the conclusion yours.</p></section>`
}

function insightsView() {
  const analyzed = state.trades.filter((trade) => trade.analyzed).length
  return `${pageHeader('Pattern review', 'Insights, when the sample earns them.', 'Comparisons stay locked until there is enough of your own history to make them meaningful.', '')}<section class="insight-hero panel"><div class="insight-ring">${scoreRing(null, 'History comparison')}</div><div><p class="eyebrow">History comparison</p><h2>${analyzed < 20 ? `${20 - analyzed} more reviewed trade${20 - analyzed === 1 ? '' : 's'} to unlock.` : 'Your comparison is ready.'}</h2><p>${analyzed < 20 ? 'RuleMirror needs at least 20 analyzed trades before showing personal baselines. That keeps a small sample from pretending to be a pattern.' : 'Your personal baseline can now be compared with new reviews.'}</p><div class="progress-track"><span style="width:${Math.min(100, analyzed / 20 * 100)}%"></span></div><small>${analyzed} of 20 reviewed</small></div></section><div class="insight-grid"><article class="panel locked-insight">${icon('lock')}<div><p class="eyebrow">Most consistent rule</p><h3>Not enough history yet</h3><p>Keep reviewing trades to see which parts of your process hold up.</p></div></article><article class="panel locked-insight">${icon('lock')}<div><p class="eyebrow">Most common miss</p><h3>Not enough history yet</h3><p>Feedback will call out repeatable misses only when the evidence supports it.</p></div></article></div>`
}

function profileView() {
  const reviewed = state.trades.filter((trade) => trade.analyzed && trade.score !== null)
  const average = reviewed.length ? Math.round(reviewed.reduce((total, trade) => total + (trade.score ?? 0), 0) / reviewed.length) : null
  const closed = state.trades.filter((trade) => trade.closed_at && trade.realized_pnl !== null && trade.realized_pnl !== undefined)
  const totalPnl = closed.length ? closed.reduce((total, trade) => total + (trade.realized_pnl ?? 0), 0) : null
  const entryNotional = closed.reduce((total, trade) => total + ((trade.quantity ?? 0) * (trade.entry_price ?? 0)), 0)
  const realizedReturn = totalPnl !== null && entryNotional > 0 ? (totalPnl / entryNotional) * 100 : null
  return `${pageHeader('Workspace settings', 'Make it yours.', 'Your profile and display preferences stay local to this browser. Account deletion affects server data.', '')}<section class="metric-grid profile-metrics"><article class="metric-card"><span class="metric-label">Total profit / loss</span><strong class="metric-value ${totalPnl !== null && totalPnl < 0 ? 'negative-value' : ''}">${totalPnl === null ? '—' : `${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}`}</strong><span class="metric-foot">${closed.length ? `${closed.length} closed trade${closed.length === 1 ? '' : 's'} · net fees included` : 'Close a trade to calculate'}</span></article><article class="metric-card"><span class="metric-label">Return percentage</span><strong class="metric-value">${realizedReturn === null ? '—' : `${realizedReturn >= 0 ? '+' : ''}${realizedReturn.toFixed(2)}%`}</strong><span class="metric-foot">Realized P/L ÷ matched entry notional</span></article><article class="metric-card"><span class="metric-label">Strategy performance</span><strong class="metric-value">${average === null ? '—' : `${average}/100`}</strong><span class="metric-foot">${reviewed.length ? `${reviewed.length} reviewed strategies` : 'No reviewed trades yet'}</span></article></section><div class="settings-layout"><section class="panel profile-card"><div class="profile-heading"><div class="avatar avatar-large">${state.profile.avatar ? `<img src="${state.profile.avatar}" alt="Profile photo">` : initials()}</div><div><p class="eyebrow">Your profile</p><h2>${escape(state.profile.name || 'Add your name')}</h2><p>${escape(state.email)}</p></div></div><label class="photo-upload" for="avatar-file">${icon('upload')} Upload profile picture<input id="avatar-file" type="file" accept="image/png,image/jpeg,image/webp"></label><form id="profile-form" class="form-stack"><label>Display name<input name="name" value="${escape(state.profile.name)}" placeholder="Your name"></label><label>Timezone<select name="timezone"><option value="${escape(state.profile.timezone)}">${escape(state.profile.timezone)}</option><option value="America/New_York">America/New_York</option><option value="America/Chicago">America/Chicago</option><option value="America/Los_Angeles">America/Los_Angeles</option><option value="UTC">UTC</option></select></label><button class="button button-secondary" type="submit">Save profile</button></form></section><section class="panel preference-card"><p class="eyebrow">Preferences</p><h2>Quiet by design.</h2><div class="setting-row"><div><strong>Appearance</strong><span>Use a light or dark workspace.</span></div><button class="switch ${state.profile.theme === 'dark' ? 'on' : ''}" id="theme-setting" type="button" role="switch" aria-checked="${state.profile.theme === 'dark'}"><span></span></button></div><div class="setting-row"><div><strong>Public profile</strong><span>${state.publicProfile ? 'Your profile shares summary metrics: portfolio value, P/L, win rate, and discipline.' : 'Private by default; no account details are shared.'}</span></div><button class="switch ${state.publicProfile ? 'on' : ''}" id="public-profile" type="button" role="switch" aria-checked="${state.publicProfile}" aria-busy="${state.publicProfilePending}" ${state.publicProfilePending ? 'disabled' : ''}><span></span></button></div><div class="danger-zone"><p class="eyebrow">Danger zone</p><h3>Delete account and data</h3><p>Removes your imports, reconstructed trades, analyses, and sessions. This cannot be undone.</p><button class="button button-danger" id="delete-account" type="button">${icon('trash')} Delete account</button></div></section></div>`
}

function analysisResultView() {
  const result = state.analysis
  if (!result) return ''
  const score = result.score
  return `${pageHeader('Trade review', `${escape(result.symbol)} · ${result.direction}`, `A deterministic review of the ${escape(result.strategy.name)} default rule profile at the recorded entry.`, `<button class="button button-secondary" id="new-analysis" type="button">Review another trade</button>`)}<section class="result-hero panel"><div>${scoreRing(score, 'Trade adherence score')}</div><div class="result-copy"><p class="eyebrow">${escape(result.strategy.name)} · Version ${result.strategy.version}</p><h2>${score === null ? 'More required context is needed for a score.' : score >= 80 ? 'The documented rule aligned well.' : score >= 60 ? 'A mixed rule-adherence signal.' : 'Several documented rules were missed.'}</h2><p>Entry recorded ${formatDate(result.entry_time)}. This score describes rule adherence, not expected outcome.</p><div class="result-meta"><span>${result.data_sufficiency === 'sufficient' ? icon('check') + ' Context reconstructed' : icon('lock') + ' Context incomplete'}</span><span>${result.comparison.message}</span></div></div></section><section class="result-grid"><article class="panel"><div class="panel-heading"><div><p class="eyebrow">Rule breakdown</p><h2>What the review found</h2></div><span class="panel-index">${result.rules.length} checks</span></div><div class="rule-list">${result.rules.map((rule) => `<div class="rule-row"><span class="rule-status status-${rule.result.toLowerCase()}">${rule.result === 'PASS' ? '✓' : rule.result === 'FAIL' ? '×' : '·'}</span><div><strong>${escape(rule.label || rule.rule)}</strong><small>${escape(rule.measurement || 'No measurement')} ${rule.threshold ? `· threshold ${escape(rule.threshold)}` : ''}</small></div><span class="rule-weight">${rule.weight} pts</span></div>`).join('')}</div></article><article class="panel"><div class="panel-heading"><div><p class="eyebrow">Feedback</p><h2>Keep the useful part.</h2></div></div><div class="feedback-list">${result.feedback.map((item) => `<div class="feedback-item feedback-${item.category}"><span>${item.category === 'matched' ? 'Matched' : item.category === 'missed' ? 'Missed' : 'Review'}</span><p>${escape(item.sentence)}</p></div>`).join('')}</div><div class="context-summary"><p class="eyebrow">Derived context</p><span>${escape(String(result.derived_context.method ?? 'Completed-bar market context'))}</span><span>${escape(String(result.derived_context.completed_bars ?? 0))} completed bars evaluated</span></div></article></section>`
}

function render() {
  document.documentElement.dataset.theme = state.profile.theme
  mount.innerHTML = state.tokens ? shellView() : authView()
  bindEvents()
  if (state.tokens && !state.hydrated) {
    state.hydrated = true
    void hydrateWorkspace()
  }
}

function bindEvents() {
  const sidebarHead = mount.querySelector('.sidebar-head')
  if (sidebarHead && !sidebarHead.querySelector('rule-mirror-mascot')) {
    const mascot = document.createElement('rule-mirror-mascot')
    mascot.setAttribute('aria-hidden', 'true')
    mascot.setAttribute('size', '54')
    mascot.setAttribute('theme', state.profile.theme === 'dark' ? 'dark' : 'light')
    mascot.setAttribute('green', '#145c4a')
    mascot.setAttribute('state', mascotState())
    sidebarHead.prepend(mascot)
  }
  mount.querySelectorAll<HTMLButtonElement>('[data-account-username]').forEach((button) => button.addEventListener('click', () => void openAccountProfile(button.dataset.accountUsername ?? '')))
  mount.querySelector<HTMLFormElement>('#account-search-form')?.addEventListener('submit', (event) => {
    event.preventDefault()
    const input = mount.querySelector<HTMLInputElement>('#account-search')
    state.accountSearch = input?.value.trim() ?? ''
    void searchAccounts(state.accountSearch)
  })
  mount.querySelector<HTMLInputElement>('#trade-search')?.addEventListener('input', (event) => { state.tradeSearch = (event.target as HTMLInputElement).value; render() })
  mount.querySelectorAll<HTMLElement>('[data-strategy]').forEach((element) => element.addEventListener('click', () => {
    state.selectedStrategy = element.dataset.strategy ?? 'vwap-reclaim'
    setNotice('Strategy selected. Its versioned default rule profile will be used for your next review.', 'success')
  }))
  mount.querySelectorAll<HTMLElement>('[data-page]').forEach((element) => element.addEventListener('click', () => {
    state.page = element.dataset.page as Page
    state.notice = null
    closeNav()
    render()
  }))
  mount.querySelector('#auth-toggle')?.addEventListener('click', () => {
    state.authMode = state.authMode === 'login' ? 'register' : 'login'
    render()
  })
  mount.querySelector<HTMLFormElement>('#auth-form')?.addEventListener('submit', (event) => void submitAuth(event))
  mount.querySelector('#dismiss-notice')?.addEventListener('click', () => { state.notice = null; render() })
  mount.querySelector('#open-nav')?.addEventListener('click', openNav)
  mount.querySelector('#close-nav')?.addEventListener('click', closeNav)
  mount.querySelector('#mobile-overlay')?.addEventListener('click', closeNav)
  mount.querySelector('#sign-out')?.addEventListener('click', () => void signOut())
  mount.querySelector('#theme-toggle')?.addEventListener('click', toggleTheme)
  mount.querySelector('#theme-setting')?.addEventListener('click', toggleTheme)
  mount.querySelector('#public-profile')?.addEventListener('click', () => void togglePublicProfile())
  mount.querySelector<HTMLInputElement>('#csv-file')?.addEventListener('change', (event) => {
    selectFile((event.target as HTMLInputElement).files?.[0] ?? null)
  })
  mount.querySelector<HTMLInputElement>('#portfolio-file')?.addEventListener('change', (event) => {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null
    if (file && file.size > 2_000_000) {
      setNotice('Choose a CSV smaller than 2 MB.', 'error')
      return
    }
    state.portfolioFile = file
    render()
  })
  mount.querySelector('#import-portfolio')?.addEventListener('click', () => void importPortfolioFile())
  const dropzone = mount.querySelector('#dropzone')
  dropzone?.addEventListener('dragover', (event) => { event.preventDefault(); dropzone.classList.add('dragging') })
  dropzone?.addEventListener('dragleave', () => dropzone.classList.remove('dragging'))
  dropzone?.addEventListener('drop', (event) => {
    event.preventDefault()
    dropzone.classList.remove('dragging')
    const dropEvent = event as DragEvent
    selectFile(dropEvent.dataTransfer?.files?.[0] ?? null)
  })
  mount.querySelector('#preview-file')?.addEventListener('click', () => void previewFile())
  mount.querySelector('#reset-import')?.addEventListener('click', () => { state.file = null; state.preview = null; state.mapping = {}; render() })
  mount.querySelectorAll<HTMLSelectElement>('[data-map-field]').forEach((select) => select.addEventListener('change', () => { state.mapping[select.dataset.mapField ?? ''] = select.value }))
  mount.querySelector<HTMLSelectElement>('#timezone')?.addEventListener('change', (event) => { state.profile.timezone = (event.target as HTMLSelectElement).value; persistProfile() })
  mount.querySelector('#import-file')?.addEventListener('click', () => void importFile())
  mount.querySelectorAll<HTMLButtonElement>('[data-trade-id]').forEach((button) => button.addEventListener('click', () => {
    state.activeTrade = state.trades.find((trade) => trade.trade_id === button.dataset.tradeId && trade.analysis_eligible) ?? null
    if (!state.activeTrade) return
    state.page = 'analyze'
    render()
    void analyzeTrade(state.activeTrade)
  }))
  mount.querySelectorAll<HTMLElement>('[data-delete-trade]').forEach((element) => {
    const erase = (event: Event) => {
      event.stopPropagation()
      void eraseTrade(element.dataset.deleteTrade ?? '')
    }
    element.addEventListener('click', erase)
    element.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') erase(event)
    })
  })
  mount.querySelector('#new-analysis')?.addEventListener('click', () => { state.analysis = null; state.activeTrade = null; state.page = 'analyze'; render() })
  mount.querySelector<HTMLInputElement>('#avatar-file')?.addEventListener('change', (event) => {
    const file = (event.target as HTMLInputElement).files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.addEventListener('load', () => { state.profile.avatar = String(reader.result ?? ''); persistProfile(); render(); setNotice('Profile picture saved on this browser.', 'success') })
    reader.readAsDataURL(file)
  })
  mount.querySelector<HTMLFormElement>('#profile-form')?.addEventListener('submit', (event) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget as HTMLFormElement)
    state.profile.name = String(form.get('name') ?? '').trim()
    state.profile.timezone = String(form.get('timezone') ?? state.profile.timezone)
    persistProfile()
    void saveAccountProfile()
  })
  mount.querySelector('#delete-account')?.addEventListener('click', () => void deleteAccount())
  syncNavA11y()
  document.onkeydown = (event) => {
    if (event.key === 'Escape') closeNav()
  }
}

function selectFile(file: File | null) {
  if (file && file.size > 2_000_000) {
    setNotice('Choose a CSV smaller than 2 MB.', 'error')
    return
  }
  state.file = file
  state.preview = null
  render()
}

async function withAuth<T>(operation: (accessToken: string) => Promise<T>): Promise<T> {
  if (!state.tokens) throw new Error('Authentication is required.')
  try {
    return await operation(state.tokens.access_token)
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || !state.tokens) throw error
    try {
      refreshPromise ??= api.refresh(state.tokens.refresh_token).finally(() => { refreshPromise = null })
      const rotated = await refreshPromise
      persistTokens(rotated)
      return await operation(rotated.access_token)
    } catch (refreshError) {
      clearSession()
      setNotice('Your session expired. Sign in again to continue.', 'error')
      throw refreshError
    }
  }
}

async function hydrateWorkspace() {
  try {
    const [imports, trades, account, portfolio] = await Promise.all([
      withAuth((accessToken) => api.importHistory(accessToken)),
      withAuth((accessToken) => api.tradeHistory(accessToken)),
      withAuth((accessToken) => api.accountProfile(state.email, accessToken)).catch(() => null),
      withAuth((accessToken) => api.portfolio(accessToken)),
    ])
    state.imports = imports as ImportSummary[]
    state.trades = trades as TradeHistory[]
    state.portfolio = portfolio
    if (account) {
      state.profile.name = account.display_name || state.profile.name
      state.publicProfile = account.public_profile
      localStorage.setItem('rulemirror.public', String(account.public_profile))
      persistProfile()
    }
    render()
  } catch (error) {
    if (state.tokens) setNotice(errorMessage(error), 'error')
  }
}

async function saveAccountProfile() {
  if (!state.tokens) return
  try {
    await withAuth((accessToken) => api.updateProfile(state.profile.name, accessToken))
    render()
    setNotice('Profile saved to your account.', 'success')
  } catch (error) {
    render()
    setNotice(errorMessage(error), 'error')
  }
}

async function submitAuth(event: SubmitEvent) {
  event.preventDefault()
  const form = new FormData(event.currentTarget as HTMLFormElement)
  const email = String(form.get('email') ?? '').trim()
  const password = String(form.get('password') ?? '')
  state.busy = 'auth'
  render()
  try {
    const tokens = state.authMode === 'register' ? await api.register(email, password) : await api.login(email, password)
    persistTokens(tokens)
    state.email = email
    sessionStorage.setItem('rulemirror.email', email)
    state.busy = null
    setNotice(state.authMode === 'register' ? 'Your workspace is ready.' : 'Signed in successfully.', 'success')
  } catch (error) {
    state.busy = null
    setNotice(errorMessage(error), 'error')
  }
}

async function previewFile() {
  if (!state.file || !state.tokens) return
  state.busy = 'preview'
  render()
  try {
    state.preview = await withAuth((accessToken) => api.preview(state.file as File, accessToken))
    state.mapping = { ...state.preview.suggested_mapping }
    state.busy = null
    render()
  } catch (error) {
    state.busy = null
    setNotice(errorMessage(error), 'error')
  }
}

async function importPortfolioFile() {
  if (!state.portfolioFile || !state.tokens) return
  state.busy = 'portfolio'
  render()
  try {
    const result = await withAuth((accessToken) => api.importPortfolio(state.portfolioFile as File, accessToken))
    state.portfolio = { portfolio_value: result.portfolio_value, holdings: result.holdings }
    state.portfolioFile = null
    state.busy = null
    render()
    setNotice(`${result.holding_count} holding${result.holding_count === 1 ? '' : 's'} imported.`, 'success')
  } catch (error) {
    state.busy = null
    setNotice(errorMessage(error), 'error')
  }
}

async function importFile() {
  if (!state.file || !state.tokens) return
  const required = ['symbol', 'side', 'quantity', 'price', 'executed_at']
  if (required.some((field) => !state.mapping[field])) {
    setNotice('Choose a column for every required field.', 'error')
    return
  }
  state.busy = 'import'
  render()
  try {
    const result = await withAuth((accessToken) => api.importExecutions(state.file as File, state.mapping, state.profile.timezone, accessToken))
    state.imports.push(result)
    const incoming = result.affected_trades.map((trade) => ({ ...trade, analyzed: false }))
    state.trades = [...state.trades.filter((trade) => !incoming.some((item) => item.trade_id === trade.trade_id)), ...incoming]
    state.file = null
    state.preview = null
    state.mapping = {}
    state.busy = null
    state.page = 'analyze'
    setNotice(`${result.accepted_execution_count} execution${result.accepted_execution_count === 1 ? '' : 's'} imported.`, 'success')
  } catch (error) {
    state.busy = null
    setNotice(errorMessage(error), 'error')
  }
}

async function analyzeTrade(trade: Trade) {
  if (!state.tokens) return
  state.busy = 'analysis'
  render()
  try {
    const created = await withAuth((accessToken) => api.createAnalysis({ trade_id: trade.trade_id, trade_revision_id: trade.trade_revision_id, strategy_slug: state.selectedStrategy }, accessToken))
    const run = await pollAnalysisRun(
      () => withAuth((accessToken) => api.analysisRun(created.id, accessToken)),
      (milliseconds) => new Promise((resolve) => window.setTimeout(resolve, milliseconds)),
    )
    state.run = run
    if (run.status === 'queued' || run.status === 'running') {
      state.busy = null
      setNotice('Analysis is still running. You can return to this trade and retry without starting a duplicate run.', 'info')
      return
    }
    if (run.status !== 'completed' || !run.trade_analysis_id) throw new Error(run.failure_code || 'The analysis did not complete.')
    state.analysis = await withAuth((accessToken) => api.tradeAnalysis(run.trade_analysis_id as string, accessToken))
    trade.analyzed = true
    trade.score = state.analysis.score
    state.busy = null
    render()
  } catch (error) {
    state.busy = null
    setNotice(errorMessage(error), 'error')
  }
}

async function signOut() {
  if (state.tokens) {
    try { await api.logout(state.tokens.refresh_token) } catch { }
  }
  clearSession()
  setNotice('You have been signed out.', 'success')
}

async function deleteAccount() {
  if (!state.tokens || !window.confirm('Delete your RuleMirror account and all stored data?')) return
  try {
    await withAuth((accessToken) => api.deleteAccount(accessToken))
    localStorage.removeItem('rulemirror.profile')
    await signOut()
  } catch (error) {
    setNotice(errorMessage(error), 'error')
  }
}

async function eraseTrade(tradeId: string) {
  const trade = state.trades.find((item) => item.trade_id === tradeId)
  if (!trade || !state.tokens || !window.confirm(`Erase the ${trade.symbol} trade from your history?`)) return
  try {
    await withAuth((accessToken) => api.deleteTrade(tradeId, accessToken))
    state.trades = state.trades.filter((item) => item.trade_id !== tradeId)
    if (state.activeTrade?.trade_id === tradeId) state.activeTrade = null
    setNotice('Trade erased from your history.', 'success')
  } catch (error) {
    setNotice(errorMessage(error), 'error')
  }
}

async function searchAccounts(query: string) {
  if (!state.tokens) return
  if (query.length < 2) {
    state.accountResults = []
    const results = mount.querySelector<HTMLElement>('#account-results')
    if (results) results.innerHTML = ''
    return
  }
  try {
    state.accountResults = await withAuth((accessToken) => api.searchAccounts(query, accessToken))
    const results = mount.querySelector<HTMLElement>('#account-results')
    if (results) {
      results.innerHTML = state.accountResults.map(accountResultView).join('') || '<div class="account-result-empty">No public usernames found.</div>'
      results.querySelectorAll<HTMLButtonElement>('[data-account-username]').forEach((button) => button.addEventListener('click', () => void openAccountProfile(button.dataset.accountUsername ?? '')))
    }
  } catch (error) {
    state.accountResults = []
    setNotice(errorMessage(error), 'error')
  }
}

async function openAccountProfile(username: string) {
  if (!state.tokens || !username) return
  try {
    state.viewedAccount = await withAuth((accessToken) => api.accountProfile(username, accessToken))
    state.page = 'account'
    state.accountResults = []
    state.accountSearch = ''
    render()
  } catch (error) {
    setNotice(errorMessage(error), 'error')
  }
}

function toggleTheme() {
  state.profile.theme = state.profile.theme === 'light' ? 'dark' : 'light'
  persistProfile()
  render()
}

async function togglePublicProfile() {
  if (state.publicProfilePending) return
  const next = !state.publicProfile
  state.publicProfilePending = true
  render()
  try {
    const result = await withAuth((accessToken) => api.setPublicProfile(next, accessToken))
    state.publicProfile = result.public_profile
    localStorage.setItem('rulemirror.public', String(result.public_profile))
    setNotice(result.public_profile ? 'Public profile visibility enabled.' : 'Public profile visibility disabled.', 'success')
  } catch (error) {
    setNotice(errorMessage(error), 'error')
  } finally {
    state.publicProfilePending = false
    render()
  }
}

function syncNavA11y() {
  const sidebar = mount.querySelector<HTMLElement>('#sidebar')
  if (!sidebar) return
  if (window.matchMedia('(max-width: 760px)').matches && !sidebar.classList.contains('open')) {
    sidebar.setAttribute('aria-hidden', 'true')
    sidebar.setAttribute('inert', '')
  } else {
    sidebar.setAttribute('aria-hidden', 'false')
    sidebar.removeAttribute('inert')
  }
}

function openNav() {
  navTrigger = mount.querySelector<HTMLButtonElement>('#open-nav')
  mount.querySelector('.sidebar')?.classList.add('open')
  mount.querySelector('#mobile-overlay')?.classList.add('visible')
  mount.querySelector<HTMLElement>('#sidebar')?.setAttribute('aria-hidden', 'false')
  mount.querySelector<HTMLElement>('#sidebar')?.removeAttribute('inert')
  navTrigger?.setAttribute('aria-expanded', 'true')
}

function closeNav() {
  mount.querySelector('.sidebar')?.classList.remove('open')
  mount.querySelector('#mobile-overlay')?.classList.remove('visible')
  if (window.matchMedia('(max-width: 760px)').matches) {
    mount.querySelector<HTMLElement>('#sidebar')?.setAttribute('aria-hidden', 'true')
    mount.querySelector<HTMLElement>('#sidebar')?.setAttribute('inert', '')
    navTrigger?.setAttribute('aria-expanded', 'false')
    navTrigger?.focus()
  }
}

function errorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong. Please try again.'
}

render()
