# Chart label acceptance — 2026-10-21

- Primary 1d/4h/1h/15m counts now require at least two grounded observed anchors unless the count is explicitly unclear. Prompt requests all observed count legs; future legs must not be fabricated.
- Charts retain older count anchors, show larger boxed labels and dashed count connections, distinguish unconfirmed anchors with `?`, and display the frame count above each panel.
- Local suite: 81 tests passed. VPS suite: 78 tests passed.
- Live manual job 878 produced BTC analysis 467; job 879 produced ETH analysis 468. Both completed without errors and outboxes were sent.
- BTC chart: https://t.me/c/4324986998/4450/9511
- ETH chart: https://t.me/c/4324986998/4450/9514
- Both generated PNGs visually inspected: labels present on all six panels, no truncated count start. Native Telegram screenshots verified receipt of each image.
- Local and VPS worker/charts SHA-256 matched; AI and monitor services active. Live JSON evidence is `/opt/trading-wave-monitor/data/reports/chart-labels-live.json`.
- Coverage checks validate coordinates and presence, not the predictive correctness of an Elliott interpretation.
