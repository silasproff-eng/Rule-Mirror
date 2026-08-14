export type WorkspaceCommand = {
  id: string
  label: string
  hint: string
  kind: 'page' | 'accounts' | 'theme'
  page?: string
}

export const WORKSPACE_COMMANDS: WorkspaceCommand[] = [
  { id: 'overview', label: 'Go to Overview', hint: 'Open your workspace summary', kind: 'page', page: 'overview' },
  { id: 'portfolio', label: 'Go to Portfolio', hint: 'Review holdings and sync status', kind: 'page', page: 'portfolio' },
  { id: 'analyze', label: 'Start an Analysis', hint: 'Import an execution CSV', kind: 'page', page: 'analyze' },
  { id: 'trades', label: 'Show Trades', hint: 'Review reconstructed execution history', kind: 'page', page: 'trades' },
  { id: 'strategies', label: 'Open Strategies', hint: 'Review visible rule profiles', kind: 'page', page: 'strategies' },
  { id: 'insights', label: 'Open Insights', hint: 'See evidence thresholds and history', kind: 'page', page: 'insights' },
  { id: 'profile', label: 'Open Profile and Settings', hint: 'Manage privacy and account settings', kind: 'page', page: 'profile' },
  { id: 'accounts', label: 'Search Public Handles', hint: 'Find published account summaries', kind: 'accounts' },
  { id: 'theme', label: 'Toggle Theme', hint: 'Switch between light and dark mode', kind: 'theme' },
]

export function filterWorkspaceCommands(query: string): WorkspaceCommand[] {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return WORKSPACE_COMMANDS
  return WORKSPACE_COMMANDS.filter((command) => {
    const haystack = `${command.label} ${command.hint}`.toLocaleLowerCase()
    return terms.every((term) => haystack.includes(term))
  })
}
