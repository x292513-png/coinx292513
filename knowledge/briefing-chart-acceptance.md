# Scheduled briefing chart restoration

- Root cause: scheduled cadence enqueued only the briefing text, even though both quiet automatic analyses had already generated chart files.
- Briefing records the exact included analysis IDs and queues each corresponding saved chart immediately after the text. Reusing saved charts requires no additional AI calls.
- Photo requests such as “사진은왜 안줘?” are handled before focused inference; resolve an explicit symbol, replied analysis, last briefing references or latest saved symbol charts.
- Photo-only delivery now preserves reply context, remembers its analysis reference, and includes symbol, analysis number, chart-asof timestamp and saved-analysis wording in the caption.
- Local 118 tests and server 115 tests passed, including matching scheduled charts and chart-resend without an AI job.
- Replayed original photo request for user message 9589. Original morning BTC analysis 490 and ETH analysis 491 charts delivered via outboxes 391/392, both sent with zero retries. Telegram message IDs 9591/9592. No new AI jobs.
- These are the morning briefing charts, not a newly generated current-market analysis. Native UI was not inspected; verification uses API delivery and DB readback.
