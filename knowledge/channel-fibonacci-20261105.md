# Channel and Fibonacci confluence

Elliott structure remains primary, in order 1d / 4h / 1h / 15m. Five-minute geometry assists execution. References do not independently trigger paper fills; the analysis converts a supported hypothesis into the existing explicit entry/stop/target plan.

Parallel channel candidates use the latest two confirmed same-side pivots and the intervening opposite pivot with maximum displacement. Swing and major degrees are considered; identical geometry is deduplicated. Calculations use linear price, not log price. Lower, middle and upper boundaries are projected at the latest closed candle time. Above/below/inside status and observed outside closes after formation are supplied to the model. These are geometric candidates, not automatically valid Elliott channels or statistical proof. No future confirmed pivots are used.

Fibonacci candidates retain explicit timestamped high/low anchors and ratios 0.236, 0.382, 0.5, 0.618, 0.786, 0.886, 1, 1.13, 1.272 and 1.618. Ratios above one extend beyond the starting anchor on the same retracement scale; they are not three-point ABC projections. A recent dominant high is retained alongside recent endpoints so the immediate micro-swing does not erase the larger upswing.

The model must assess relevant channels and ratios, justify chosen anchors/degree, distinguish touch from reversal, and not call a broken channel held support. Selected references are persisted as measured evidence and displayed in expandable Telegram text. The final chart draws at most one selected channel and four in-range selected Fibonacci lines per timeframe to limit clutter. The underlying measurements, anchor identities and invalidation reasoning remain available in text. Other channel candidates and out-of-frame lines are not silently presented as confirmed signals.

Unit tests cover parallel projection, upper/lower breaks, descending channels, future confirmation exclusion, extended ratios and report rendering. Existing paper execution and reporting schedules are preserved.

Production acceptance: 189 local and 186 VPS tests passed. Services restarted successfully after confirming no pending/running jobs. Fresh ETH job 963 completed as analysis 542, selecting 1h and 15m channels plus three Fibonacci references and a 4h SMA. Outbox 490 was sent with zero retries and message IDs 9761–9764; the generated chart was visually inspected. These identifiers record this deployment test, not a permanent trading recommendation. Source backup: `backups/channel-fib-20261105`.
