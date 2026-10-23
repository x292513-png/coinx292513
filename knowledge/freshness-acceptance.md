# Fresh request and price fallback acceptance

- Fixed missing independent price fallback: exchange timestamp checked on REST ticker; a stale quote cannot be re-stamped as current.
- All analysis jobs refresh configured candles and current price before the snapshot, with a 90-second bounded timeout. Failed refreshes do not proceed to model inference with cached data.
- Collector attempts price fallback after 15 seconds without fresh price, checking every 5 seconds. An outage needs 120 seconds to notify and only notifies once per uninterrupted episode; pause suppresses notices.
- Exact `비트 분석` and `이더 분석` routing tested through the authenticated production bridge/inbox using explicitly marked test messages, not a human-origin Telegram update.
- Local 84 tests and VPS 81 tests passed. Deployed files match local SHA-256, both services active.
- Job 888 / BTC analysis 477: snapshot 4.12 seconds after request, price age 0.265 seconds. Messages 9535/9536/9537 accepted by Telegram; outbox sent with zero retries.
- Job 889 / ETH analysis 478: queued behind BTC, refreshed at processing start 160.11 seconds after request, price age 0.133 seconds. Messages 9538/9539/9540 accepted by Telegram; outbox sent with zero retries.
- Neither analysis was stale/invalidated at publication. Production JSON evidence: data/reports/fresh-request-acceptance.json.
- Native Telegram was locked during this check. Delivery proof is Telegram API success/message IDs and persistent outbox readback, not native screen inspection.
- External connectivity failure remains possible. The fix provides fallback and episode-based notices; it does not promise perpetual exchange/network availability.
