export function formatActivityTime(value: string | undefined) {
  if (!value) return 'Imported'
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(value))
}
