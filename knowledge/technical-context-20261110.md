# Complementary indicator context

Closed-candle snapshot for all configured timeframes now includes Bollinger bands (20-period close SMA +/- 2 population standard deviations), %B, bandwidth%, previous values and close reentry; price stochastic (14,3,3 SMA) K/D and last closed crossover. Open candles are excluded. Flat denominators return null rather than fabricated oscillator readings. The context survives compact_input and is saved with each new analysis snapshot.

Elliott structure remains primary. RSI/pivot confirmation is separate from price confirmation. Bollinger tags and stochastic extremes/crossovers are not standalone trades, independent votes, or automatic leverage increases. Only relevant context is summarized in the expandable indicator section using the compatible rsi_comment field. This change adds measurements and interpretation; it does not add an entry gate, change stops, hold-time execution or overwrite open positions. No performance improvement is claimed without forward evidence.

References:
- https://www.bollingerbands.com/bollinger-band-rules
- https://www.tradingview.com/support/solutions/43000502332-stochastic-stoch/
- https://www.tradingview.com/support/solutions/43000592285-stochastic-slow-strategy/
