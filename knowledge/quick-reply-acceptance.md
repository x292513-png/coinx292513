# Short stop/entry follow-ups

- Stop, entry-now, and take-profit questions route to a short existing-plan response with a new REST price quote; no new AI job is created. Explicit requests to reanalyze retain the full path.
- Symbol resolution: explicit symbol, replied-to analysis, then a recent unambiguous single-symbol conversation. Otherwise asks which symbol rather than queuing BTC and ETH.
- Existing enabled plans display stop first, current-price stop distance and target risk/reward, entry-zone status, and original entry/stop conditions. Entry conditions are not represented as freshly confirmed from the price alone.
- Plans older than two hours, invalidated plans, crossed stops/targets, and opposite-side requests cannot silently reuse a stop. Disabled plans show the original waiting reason and its age.
- Local full suite 105 passed; server suite 102 passed. After refining age checks and disabled-plan wording, focused suite 21 passed. Some integration cases inherited by the focused class run again.
- Live authenticated production bridge test returned quick_reply=true in 0.22 seconds and created zero AI jobs. Outbox 382 was sent with zero retries; Telegram accepted message 9574.
- Live BTC plan 487 was disabled, so the short answer reported entry waiting with its prior risk/reward reason. Valid-stop and stale/invalidated branches were tested with fixtures.
- Latest source hashes matched the server; collector restarted and active. Screenshot/native Telegram receipt was not checked in this task.
