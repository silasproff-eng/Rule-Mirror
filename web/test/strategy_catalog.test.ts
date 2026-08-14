import { describe, expect, it } from 'vitest'

import { STRATEGY_CATALOG } from '../src/strategy_catalog'

describe('strategy catalog', () => {
  it('describes the implemented calculation profile instead of a named-strategy claim', () => {
    const macd = STRATEGY_CATALOG.find((strategy) => strategy.name === 'MACD Cross')

    expect(macd).toEqual({
      name: 'MACD Cross',
      family: 'trend profile',
      summary: 'Default profile checks directional EMA 9 and EMA 20 alignment on completed bars.'
    })
  })
})
