# Independent specialist trading review

User approved all full analyses using specialists plus coordinator, approximately four model calls per full analysis. No claim that more agents improve returns.

Roles: wave/time proportion and book rules; ICT/OB/FVG/channel/Fibonacci; momentum/technical indicators and risk. All independently receive the same market snapshot, return strict-schema reports, and have no execution authority. Coordinator sees completed reports, explicitly treats missing reports as unavailable, refreshes candles and prices, and retains existing final plan validators and stale-at-publication rejection.

Specialists use independent ephemeral Codex invocations of configured model, tools disabled. Max two concurrent subprocesses under the existing service memory cap; each has a 90-second timeout, so specialist phase is bounded to approximately two timeout windows plus termination grace. Each specialist gets a dedicated calls row (kind=team), and report/call ID/status/usage/timestamp persist in team_reviews and analysis snapshot. Evidence references are schema-enumerated from actual input. Failed attempts count. Unstarted reservations don't count as actual calls and are abandoned on worker restart. Reservation of three slots is atomic.

Per-day chief limits unchanged: auto4/manual12/paper12, news2. Separate specialist ceiling84 supports three specialists for up to28 full analyses. Focused questions, balance queries and news do not launch specialists. If all three specialist slots cannot be reserved, the full analysis is budget_limited rather than silently labeled team-reviewed. Model failures produce partial review, visibly marked. Total /status shows specialist counts. KST daily reset remains.

Coordinator reads fresh frames after reports and must discard invalidated prior report evidence. Learning/fractal contexts retain their source timestamps. Team consensus is neither a win probability nor a leverage formula. Opposing views and the coordinator's choice appear in alternative; the expandable team section shows actual specialist summaries. Open positions and paper execution rules are unchanged.

Implementation also removes stale '1x paper account' text contradicting current per-trade 1..10x policy.
