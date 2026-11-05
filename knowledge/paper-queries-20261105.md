# Paper account queries

The existing Telegram bridge now routes the configured paper topic to the monitor, in addition to the original analysis topic. Runtime `paper_topic_id` matches SQLite's topic ID 9724. All other topics retain their existing handler; allowed user and chat checks remain required.

Within the paper topic, `/start`, `/balance`, `/positions`, `/position`, `/status`, `/report`, and natural questions about balance, positions, profit, entry reasons, timing and exits return a read-only account report. Unknown requests return usage help instead of invoking AI. `/start` does not unpause notifications, create analyses or place simulated trades in this topic. The original analysis topic retains its existing command behavior.

Reports show combined equity, realized/unrealized PnL, available units, separately labeled pending orders, open position average/notional and PnL, entry time, timeframe labels, stop/targets, holding deadline, saved entry evidence and recent executions. Price and processing delays are labeled. No BTC/ETH coin quantity is fabricated because USDT per unit is undefined. Evidence is read from the exact analysis that created the plan.

Inbox update deduplication and response enqueue are one SQLite transaction for paper queries. Same update retries cannot queue duplicate replies.

Validation: 162 local and 159 VPS tests passed. Tests include authorization, bridge routing and preservation of other topics, natural questions and slash commands, no AI or trading side effects, pause state preservation, retries, open-position PnL, entry evidence escaping and absence of fake coin quantities.

Live acceptance: actual installed bridge routed `/start`, its duplicate, and a Korean balance/position question through the running authenticated HTTP inbox. Responses were paper_query / duplicate / paper_query. Outbox 480 and 481 target topic 9724; pause state was unchanged. This is a synthetic incoming update through the production bridge, not a claim that a human sent the test commands.

Backup: `/opt/trading-wave-monitor/backups/paper-queries-20261105` (directory restricted to root because runtime backup includes credentials). Trading monitor and Telegram bridge services restarted; AI worker remained active.
