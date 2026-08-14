export type StrategyCatalogEntry = { name: string; family: string; summary: string }

const engineCopy: Record<string, string> = {
  breakout: 'Default profile checks entry price beyond the prior completed 20-bar high or low.',
  trend: 'Default profile checks directional EMA 9 and EMA 20 alignment on completed bars.',
  reversion: 'Default profile checks the documented RSI 14 reversion zone on completed bars.',
  volume: 'Default profile checks relative volume at or above 1.50 on completed bars.',
  volatility: 'Default profile checks current range at or above 1.25 times the prior 20-bar average range.',
  needs_secondary_symbol: 'Requires a comparison symbol that this release does not collect; results report insufficient data.',
  needs_history: 'Requires multi-session history that this release does not reconstruct; results report insufficient data.'
}

const strategyProfiles: Array<[string, string]> = [
  ['Opening Range Breakout', 'breakout'], ['Moving Average Crossover', 'trend'], ['MACD Cross', 'trend'],
  ['RSI Reversion', 'reversion'], ['Bollinger Band Reversion', 'reversion'], ['Bollinger Band Squeeze', 'volatility'],
  ['Donchian Channel Breakout', 'breakout'], ['Keltner Channel Breakout', 'volatility'], ['Trendline Break', 'breakout'],
  ['Support and Resistance', 'breakout'], ['Pullback to Moving Average', 'trend'], ['Higher-Timeframe Alignment', 'trend'],
  ['ADX Trend Filter', 'trend'], ['Parabolic SAR Trail', 'trend'], ['Supertrend', 'trend'],
  ['Ichimoku Cloud Breakout', 'breakout'], ['Pivot Point Reversal', 'reversion'], ['Fibonacci Retracement', 'reversion'],
  ['Fibonacci Extension', 'breakout'], ['VWAP Bounce', 'reversion'], ['VWAP Fade', 'reversion'],
  ['Anchored VWAP', 'trend'], ['Volume Breakout', 'volume'], ['Relative Volume Spike', 'volume'],
  ['Accumulation/Distribution', 'volume'], ['On-Balance Volume', 'volume'], ['Volume Profile Node', 'volume'],
  ['Gap and Go', 'breakout'], ['Gap Fill', 'reversion'], ['Inside Bar Breakout', 'breakout'],
  ['Pin Bar Reversal', 'reversion'], ['Engulfing Reversal', 'reversion'], ['Three-Bar Reversal', 'reversion'],
  ['Bull Flag', 'breakout'], ['Bear Flag', 'breakout'], ['Ascending Triangle', 'breakout'],
  ['Descending Triangle', 'breakout'], ['Cup and Handle', 'breakout'], ['Head and Shoulders', 'reversion'],
  ['Double Top', 'reversion'], ['Double Bottom', 'reversion'], ['Mean Reversion Z-Score', 'reversion'],
  ['Pairs Spread Reversion', 'needs_secondary_symbol'], ['Seasonality Window', 'needs_history'],
  ['Relative Strength Rotation', 'needs_secondary_symbol'], ['ATR Volatility Breakout', 'volatility'],
  ['ATR Trailing Exit', 'volatility'], ['Range Expansion', 'volatility'], ['Market Structure Shift', 'trend'],
  ['Liquidity Sweep Reversal', 'reversion'], ['Fair Value Gap Retest', 'reversion']
]

export const STRATEGY_CATALOG: StrategyCatalogEntry[] = strategyProfiles.map(([name, engine]) => {
  return { name, family: `${engine.replaceAll('_', ' ')} profile`, summary: engineCopy[engine] }
})
