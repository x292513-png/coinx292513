# 10,000 USDT isolated 5x paper account

New forward-only account, initial equity 10,000 USDT, leverage 5. No real exchange orders.
`python -m scripts.start_usdt_paper` is idempotent; run while paper execution and AI services are stopped.
The account's plan/event ID floors preserve old records unchanged and exclude old open positions and realized PnL. No historical fills are scaled or copied. `paper_started` prevents replay of pre-reset analyses.

Allocation fields named `initial_units` and `add_units` now represent margin percentages. Notional = equity × allocation% × 5, quantity = notional/fill. Reserved margin = remaining entry notional/5, partial exits release margin proportionally, PnL = quantity × signed price change. Aggregate stop risk remains 1% of current realized equity; allocation preparation also considers 0.20% illustrative roundtrip costs. Paper ledger excludes fees/funding as previously requested.

Isolated loss never consumes more than that position's released collateral share. No automatic margin top-ups. Fixed 0.5% maintenance-rate approximation; stop must be inside estimated liquidation at registration and market fill. Gap opens beyond the estimate close the position and cap loss at collateral. Normal stop-first OHLC handling remains. This is not Binance's exact mark-price/tier/fee liquidation simulator.
Formula reference: https://www.binance.com/en-NZ/support/faq/detail/b3c689c1f50a44cabb3a84e663b81d93

Reports show USDT, coin quantity, notional, reserved margin and margin ROE. Old analysis allocation fields without leverage remain interpreted as 1x; newly prepared analyses record 5x explicitly. Historical account ledger retained in database backup and original rows.

Before migration audit: 7 entries, 31 cancellations (21 superseded by new analysis, 4 structure failures, 3 expiry/invalidation, 2 entry band/chase/RR failures, 1 unencoded). Two old open positions. This is not evidence of zero trading or of profitability. No entry criteria were weakened merely to force a fill.
