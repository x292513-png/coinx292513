# Conditional-order display and executability correction

User reported that ETH had crossed the displayed 2420 limit without a simulated fill. Live inspection at 2026-11-05 19:28 KST found plan 4 / analysis 538 waiting for a future 5m close above 2449.95 before arming a 2420.19 limit. The 124 closed eligible 5m candles had maximum close 2435.68; no armed or entry event existed. Feed price 2418.98 and paper heartbeat were current. This was not a missed fill on an active order.

Two actual defects were corrected:

- Presentation called the unarmed candidate a pending limit, burying the precondition in folded details. Reports now distinguish condition observation (no active order), active limit, and open position. Query responses place the precondition above folds.
- Analysis 538 explicitly admitted that a mandatory reversal check could not be encoded, yet enabled simulation. New schema requires `conditions_fully_encoded`; missing/false or contradictory unsupported-condition reasons reject registration. Pending legacy plans lacking verification are canceled with an audit event; existing open positions retain protective management. No retroactive trades or PnL are fabricated.

Local 165 / server 162 tests passed. Added tests verify an identical price cross does not fill an unarmed plan but does fill an active limit; unsupported/missing execution attestations reject; legacy pending cancellation creates no entry. Services restarted after confirming no pending/running AI jobs. Backup: backups/paper-activation-20261105.
