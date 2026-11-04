# Forward paper account

User requested chart-conditioned 24-hour simulated trading, with a separate Telegram topic and six-hour reports. Fees and funding are excluded. This is not an exchange account and cannot place orders.

## Accounting and execution

- Shared starting balance: 100 units for BTCUSDT and ETHUSDT, 1x notional. Realized PnL changes capital; mark-to-market adds unrealized PnL to equity. Remaining unallocated capital excludes reserved orders and open entry notional.
- Structured full-analysis `paper_execution` specifies a conditional close followed by a limit order, or an already-confirmed limit order. Arbitrary prose conditions cannot be silently simplified: unsupported rules disable the simulated plan.
- Only analyses created after account activation are eligible. No pre-registration candle or confirming candle can fill an entry. New analyses cancel pending orders but never silently rewrite an open position. Reports published while a position is open are consumed, not replayed after it exits.
- Initial/add amounts use the published position allocation, scaled to shared available capital and a maximum aggregate planned stop loss of 1% of realized capital. This is a risk budget, not a guaranteed loss cap across price gaps.
- Closed one-minute candles drive execution continuously. Stops take priority in ambiguous candles. Entry/add bars cannot take optimistic profits. An armed add and stop in the same candle includes the add before the stop when the open has not already crossed the stop.
- TP1 realizes the configured fraction. Remaining position uses TP2, optional immediate break-even stop, and a maximum holding time. This explicitly recorded simulation variant does not claim to implement arbitrary discretionary trailing rules.
- Missing minute history is recorded. Pending orders cancel; open positions close at the next observed open, labeled a data-gap exit. This is an explicit simulation convention, not evidence of the actual path during the gap.
- Pause cancels pending simulated entries and mutes reports; existing positions retain mechanical stop/exit management.
- SQLite transactions persist events, state, and last processed candle together. Restart does not replay fills.

## Reports and cost

Topic `코인 매매`: thread 9724 in the existing group. Reports at 03:00, 09:00, 15:00, 21:00 KST. Existing 09:00 and 21:00 briefings also include account totals. Monitoring and reporting make no extra model calls. Existing scheduled and manual full analyses provide plans. Two initial manual analyses were requested to validate the new schema.

Initial report: outbox 469, message 9725, sent to topic 9724 with zero retry. Initial capital 100.000, realized/unrealized 0, no positions.

## Verification

Local 157 tests and VPS 154 tests passed (existing local suite has three additional tests). New tests cover conditional confirmation, no retroactive or clock-based entry, shared capital risk, entry-stop ambiguity, short and long PnL, partial/break-even exits, gap stops, add-stop ordering, missing history, restart idempotence, existing-position plan handling, topic routing, report deduplication, and pause.

Backup on VPS: `/opt/trading-wave-monitor/backups/paper-20261105`.

## Live plan validation

Fresh manual jobs 954/955 both completed, analyses 535/536. BTC correctly recorded a skipped entry: the prior retest entry had passed. ETH registered a forward-only conditional plan for 39.15 units: future 5m close above 2446.76, then limit 2401.13; stop 2366.50; TP1 2493.48 (50%), TP2 2526.99; unfilled expiry 12h; maximum hold 48h. This is a timestamped acceptance observation, not a permanent current-market recommendation. At verification both actual position quantities remained zero, capital/equity 100.000, and 60.850 units were unallocated after reserving the conditional order.

Current production paper heartbeat and market feed were healthy. Detailed reports now use bold headings, paragraph spacing and an expandable Telegram block for recent trades and conditions.
