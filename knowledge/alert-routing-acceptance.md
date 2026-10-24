# Sharp-alert request routing and HTML repair

- The request “급락 이나 급등 최소 2% 이상 5분안에 진행시 바로 브리핑해줘” had incorrectly reached focused inference, which denied the existing collector alert capability.
- Explicit sharp-alert requests now resolve before AI routing, persist per-symbol thresholds, and resume notifications. Supported observation windows remain 5/15/60 minutes. Missing/unsupported parameters produce a targeted reply.
- Cadence consumes persisted per-symbol rules. Its approximately five-second checks and existing duplicate/escalation suppression remain. Reference price is the available 1m open near the lookback, not exact tick-to-tick five-minute data.
- Focused inference now receives actual alert capabilities/settings. Focused and quick formatted replies use the HTML document envelope; user/model text remains escaped. Raw untrusted messages are not treated as HTML.
- Local suite 114 passed; VPS suite 111 passed. Server services active; deployed hashes matched local.
- Replayed the original request through the command handler: zero new AI jobs; BTCUSDT and ETHUSDT both persisted [5,2.0], pause false. Confirmation outbox 388 sent with zero retries.
- Corrected original Telegram message 9583 via editMessageText. API returned a bold entity and no literal <b> in displayed text. Removed the erroneous capability claim from the active dialogue context by replacing it with an explicitly labeled correction.
- Existing cadence tests cover +2%/-2% thresholds, budget-independent alerts, duplicate suppression and pause. No fake market movement was injected into production.
- Evidence: /opt/trading-wave-monitor/data/reports/alert-routing-acceptance.json.
