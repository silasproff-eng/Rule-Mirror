import { describe, expect, it } from 'vitest'

import { filterWorkspaceCommands } from '../src/command_search'

describe('mascot command search', () => {
  it('matches keywords across command labels and descriptions', () => {
    expect(filterWorkspaceCommands('public handles').map((command) => command.id)).toEqual(['accounts'])
    expect(filterWorkspaceCommands('portfolio').map((command) => command.id)).toEqual(['portfolio'])
    expect(filterWorkspaceCommands('')).toHaveLength(9)
  })
})
