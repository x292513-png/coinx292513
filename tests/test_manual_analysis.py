import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from wave_monitor import store
from wave_monitor.worker import process,run_codex


class ManualAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.refresh_patch=patch('wave_monitor.worker.refresh_for_analysis');self.refresh=self.refresh_patch.start();self.addCleanup(self.refresh_patch.stop)
        self.tmp=tempfile.TemporaryDirectory();self.old=store.ROOT;store.ROOT=Path(self.tmp.name);store.init()
        self.cfg={'auto_calls_per_day':4,'manual_calls_per_day':12,'notification_mode':'twice_daily'}
        self.job={'id':1,'kind':'manual','symbol':'BTCUSDT','reply_id':101,'question':'분석해줘','reason':'user_followup','analysis_ref':None}

    def tearDown(self):
        store.ROOT=self.old;self.tmp.cleanup()

    def test_auto_budget_does_not_block_manual_fresh_snapshot(self):
        now=time.time()
        with store.db() as c:
            for _ in range(4):c.execute("INSERT INTO calls(started,kind) VALUES (?,'auto')",(now,))
        with patch.object(store,'settings',return_value=self.cfg),patch('wave_monitor.worker.snapshot',return_value=({'price':{'time':now-60}},{})) as snapshot:
            with self.assertRaisesRegex(RuntimeError,'stale_price'):process(self.job)
        self.refresh.assert_called_once_with('BTCUSDT')
        snapshot.assert_called_once_with('BTCUSDT')
        with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM analyses').fetchone()[0],0)

    def test_every_manual_budget_rejection_gets_a_reply(self):
        now=time.time()
        with store.db() as c:
            for _ in range(12):c.execute("INSERT INTO calls(started,kind) VALUES (?,'manual')",(now,))
        with patch.object(store,'settings',return_value=self.cfg),patch('wave_monitor.worker.snapshot') as snapshot:
            self.assertEqual(process(self.job),'budget_limited')
            self.assertEqual(process({**self.job,'reply_id':102}),'budget_limited')
        snapshot.assert_not_called()
        with store.db() as c:self.assertEqual([r[0] for r in c.execute('SELECT reply_id FROM outbox ORDER BY id')],[101,102])

    def test_isolated_binary_and_actionable_model_error(self):
        import json
        from unittest.mock import Mock
        cfg={**self.cfg,'codex_binary':'/project/vendor/codex','model':'gpt-5.6-sol','reasoning_effort':'medium','ai_timeout_seconds':240}
        process_mock=Mock(returncode=1)
        process_mock.communicate.return_value=(json.dumps({'type':'error','message':"The model is not supported with this account"}),'')
        with patch.object(store,'settings',return_value=cfg),patch('wave_monitor.worker.subprocess.Popen',return_value=process_mock) as popen:
            with self.assertRaisesRegex(RuntimeError,'ai_model_unavailable'):run_codex('prompt','chart.png',1,[],[])
        self.assertEqual(popen.call_args.args[0][0],'/project/vendor/codex')
