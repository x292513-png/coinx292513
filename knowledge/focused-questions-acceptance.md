# Free-form focused questions acceptance

- Short exact stop/target lookups retain the deterministic price lookup. Questions about RSI, Elliott counts, conditions, ICT and proposed entries use focused inference with fresh candles, closed vs open-bar RSI, reference analysis, last three focused exchanges and retrieved book-reading context.
- Full analysis is reserved for explicit full-analysis requests. Ambiguous symbols ask for clarification; explicit ETH questions do not queue BTC.
- Focused inference shares the existing manual budget and model. It has no image/full report requirement and does not replace the latest full trade plan. Uses separate per-job JSON schemas.
- Open-bar pivot confirmation is downgraded to developing. Future low/stop levels must remain conditional. Conditions and present observations are explicitly separated in the prompt.
- Local suite: 110 tests; deployed suite: 107 tests. All passed. Source SHA-256 matches runtime and both services active.
- Production bridge submitted the user's ETH 15m divergence/stop example as job 902. Finished successfully, model latency 20.17 seconds, snapshot price age 0.209 seconds, focus_frames=['15m']. Book topics impulse/abc.
- Live response answered the proposed setup directly; did not create BTC analysis or a chart. It marked new-low divergence unobserved and the future stop unpriced until the low forms.
- Independently checked response reference low 2281.22 and RSI 8.18 against stored candles up to snapshot time; matched.
- Outbox 385 sent with zero retries; Telegram accepted message 9580. Native UI was not checked. Link: https://t.me/c/4324986998/4450/9580
- Evidence on VPS: data/reports/focused-live-acceptance.json and kv focused_result:902. Observed latency is one test, not a guaranteed response SLA. Free-form inference can still misinterpret a question; grounding and schema validation do not certify every financial interpretation.
