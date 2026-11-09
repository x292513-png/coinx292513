# Forward paper leverage policy, 2026-11-10

New AI plans select integer isolated leverage 1..10 with an explicit reason. Above 5 requires all four wave-view directions aligned, worst-entry TP1 reward/risk >=2, and encoded execution conditions. Otherwise leverage is clamped to 5. Confidence scores and recent winners are not calibrated win rates and cannot drive leverage automatically.

New schema plans use structural risk: the model explicitly selects the per-plan loss allowance as a percentage, after defining the structural stop. Allocation retains available margin and timeframe allocation ceilings, but removes legacy fixed 0.5/0.75/1 percent loss ceilings. Registration uses the selected loss allowance, existing shared available margin and estimated isolated liquidation constraint. Next-open resizing retains the original planned absolute stop-risk budget; it no longer reimposes the legacy portfolio 1 percent ceiling. Ledger still excludes fees/funding; planning considers illustrative 0.20 percent roundtrip cost.

Runtime activation: add max_leverage=10 and risk_policy=structural to existing paper_account_v2, never reset account, balance, history or open positions. Existing plans retain their recorded leverage and legacy risk policy. The account header shows the allowed range; each open position shows its actual leverage.

Audit at task start: five entries; three completed trades with total realized +260.001385 USDT; two open. No stop or liquidation events in the new account. This small sample does not establish a durable win rate. The user's 10k-to-20k monthly target must not override setup validity or force exposure.
