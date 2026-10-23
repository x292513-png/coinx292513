import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock,AsyncMock
from wave_monitor import store
from wave_monitor.freshness import refresh_price,track_outage

class FreshnessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=store.ROOT;store.ROOT=Path(self.tmp.name);store.init()
    def tearDown(self):
        store.ROOT=self.old;self.tmp.cleanup()
    async def test_exchange_timestamp_is_required_and_old_quote_rejected(self):
        session=MagicMock();response=AsyncMock();response.status=200
        session.get.return_value.__aenter__.return_value=response
        response.json.return_value={'time':1000000,'price':'123'}
        with patch('wave_monitor.freshness.time.time',return_value=1010):
            await refresh_price(session,'BTCUSDT')
        self.assertEqual(store.get('price:BTCUSDT')['time'],1000)
        with patch('wave_monitor.freshness.time.time',return_value=1040):
            with self.assertRaisesRegex(RuntimeError,'not_fresh'):await refresh_price(session,'BTCUSDT')
        self.assertEqual(store.get('price:BTCUSDT')['time'],1000)
    def test_transient_outage_silent_persistent_outage_only_once_and_recovery_resets(self):
        for now in [1000,1050,1121,5000]:track_outage('BTCUSDT',now)
        with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)
        store.put('price:BTCUSDT',{'time':5000});track_outage('BTCUSDT',5001)
        self.assertIsNone(store.get('data_outage:BTCUSDT'))
        for now in [6000,6121]:track_outage('BTCUSDT',now)
        with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],2)
