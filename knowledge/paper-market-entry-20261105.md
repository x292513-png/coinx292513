# Wave-based reversal and acceleration paper entries

The user explicitly required implementing, not merely describing, non-limit entries such as a C-wave terminal fifth-wave reversal with a stop anchored to the prior low. Existing limit/pullback modes remain available; the model now compares C-wave reversal, wave-four reversal, impulse continuation and pullback setups.

## Execution

- `close_then_market`: future closed confirmation candle, then next eligible one-minute open. No return to the preferred limit price is required.
- `market`: a closed confirmation candle must already exist at registration; fill uses a future eligible one-minute open, never a historical analysis price.
- C-wave/wave-four reversal setups additionally require a directional confirmation body crossing from the other side of the level (confirmation candle open). A falling candle merely sitting above the level is not a bullish reversal.
- The wave setup is an analyst hypothesis derived from the existing chart/book context; a numerical crossing is an execution condition, not independent proof of a five-wave count.
- Confirmation can use 1m/5m/15m/1h/4h. One-minute data is execution assistance; top-down thesis remains 1d/4h/1h/15m. A local reversal level can be selected without requiring the whole prior third-wave high to break.
- Before filling, actual next-open price must remain on the confirmed side, inside the specified entry band, within the allowed adverse deviation (0.05–2%), and retain at least 1.5R to TP1. Otherwise cancel with a readable reason.
- Actual fill notional is recalculated against the originally reserved initial stop-risk budget, available shared capital, and aggregate 1% risk budget. Planned unit amounts are never silently treated as filled quantities.
- Optional pre-entry structure failure (`cancel_price`, `cancel_tf`) cancels waiting orders. Active orders only use closed information available by that minute's open, preventing retrospective cancellation with a later candle close.
- Stop remains structural and fixed until optional break-even after TP1; TP1 partial, TP2 residual, maximum hold. A same-minute stop has priority. Market-style add entries are disabled in this version; existing conditional-limit adds remain supported.
- Existing data-gap, deduplication, fees-excluded accounting, 100-unit shared account and report schedule remain in force. Continuous execution monitors registered plans; it is not continuous LLM inference. No retrospective synthetic profits or real exchange orders.

## Model/report integration

The structured schema and analysis prompt expose both new modes and explicit setup, chase allowance and failure line. The model is instructed to select a supported coherent management plan instead of arbitrarily adding unimplemented prerequisites; genuinely necessary unencoded conditions still disable execution. Late fifth-wave false breakouts must be compared with early impulse continuation. Telegram distinguishes next-open entries from active limits and shows cancellation reasons.

## Validation

185 local / 182 server tests pass. New tests cover causal confirmation/fills without retrace, already-confirmed immediate entries, failed reversals, bearish bars above the bullish level, short execution/profit, excessive chasing, actual-price RR checks, loss-budget recalculation, stop on entry bar, expiry at fill time, structure failure, future-close isolation, restart deduplication and rendering.

VPS backup: `backups/paper-market-20261105`. Existing AI jobs were empty before initial deployment. Fresh ETH full-analysis job 962 validates production schema, generation and plan registration.

Production job 962 completed as analysis 541 and outbox 488 was sent with zero retries. Plan 7 registered as `close_then_market` / `c_wave_reversal`: bullish 5m reclaim through 2397.42, then next 1m open within 2397.43–2399.40, initially 40 units, stop 2366, TP1 2449.95 (50%), TP2 2489.805, pre-entry 5m failure line 2384.26, expiry 2h, max hold 48h, break-even after TP1. This is a timestamped acceptance record, not a permanent recommendation. It was waiting/unfilled at verification; account remained 100 units, zero PnL. No past fill was manufactured for acceptance testing.
