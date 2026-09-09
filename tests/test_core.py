import asyncio
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from wave_monitor.analysis import indicators,volume_profile,candidates,pivots
from wave_monitor import store
from wave_monitor.reports import evaluate


class MathTests(unittest.TestCase):
    def test_rsi_known_up_down_flat(self):
        for slope,expected in [(1,100),(-1,0),(0,50)]:
            rows=[dict(t=i*60000,close_t=(i+1)*60000-1,o=100+slope*i,c=100+slope*i,h=101+slope*i,l=99+slope*i,v=10) for i in range(40)]
            r,a=indicators(rows);self.assertEqual(r[-1],expected);self.assertGreater(a[-1],0)

    def test_profile_conserves_volume_and_70pct(self):
        rows=[dict(t=i,close_t=i+1,l=100+i,h=104+i,v=i+10) for i in range(20)]
        p=volume_profile(rows,bins=20)
        self.assertAlmostEqual(sum(p['volume']),sum(r['v'] for r in rows))
        included=sum(v for i,v in enumerate(p['volume']) if p['val']<=p['edges'][i] and p['edges'][i+1]<=p['vah'])
        self.assertGreaterEqual(included/sum(p['volume']),.7)

    def test_impulse_rules_overlap_and_shortest(self):
        def pats(prices):
            points=[dict(price=x,kind='L' if i%2==0 else 'H') for i,x in enumerate(prices)]
            return [x['pattern'] for x in candidates(points)]
        self.assertIn('impulse_5_candidate',pats([100,120,110,145,125,150]))
        self.assertNotIn('impulse_5_candidate',pats([100,120,110,145,115,150]))
        self.assertNotIn('impulse_5_candidate',pats([100,140,120,150,145,190]))

    def test_pivots_have_causal_confirmation(self):
        prices=[100+(i%20 if (i//20)%2==0 else 20-i%20) for i in range(160)]
        rows=[dict(t=i*60000,close_t=(i+1)*60000-1,o=p,c=p,h=p+.2,l=p-.2,v=1) for i,p in enumerate(prices)]
        for n in range(30,len(rows)):
            pts=pivots(rows[:n])
            for p in pts:
                if p['confirmed']:self.assertGreater(p['confirmed_at'],p['t']+60000)
            # Every confirmed pivot must exist unchanged when more candles are appended.
            future=pivots(rows[:min(n+5,len(rows))])
            for p in pts[:-2]:
                self.assertIn((p['t'],p['price']),[(q['t'],q['price']) for q in future])

    def test_evaluation_intrabar_ambiguity(self):
        r={'bias':'bullish','targets':[110],'invalidation_price':90,'invalidation_side':'below'}
        self.assertEqual(evaluate(r,100,[{'h':112,'l':89,'c':101}])['outcome'],'same_minute_ambiguous')
        self.assertEqual(evaluate(r,100,[{'h':105,'l':89,'c':95},{'h':112,'l':94,'c':111}])['outcome'],'invalidation_first')


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=store.ROOT;store.ROOT=Path(self.temp.name);store.init()
    def tearDown(self):store.ROOT=self.old;self.temp.cleanup()
    def test_closed_candle_cannot_be_replaced_by_stale_open(self):
        store.save_candles('BTCUSDT','1m',[[1,10,12,9,11,5,60000,1]])
        store.save_candles('BTCUSDT','1m',[[1,10,11,9,10,3,60000,0]])
        self.assertEqual(store.candles('BTCUSDT','1m')[0]['c'],11)
    def test_auto_jobs_deduplicate_without_losing_manual(self):
        self.assertIsNotNone(store.queue('BTCUSDT','a'))
        self.assertIsNone(store.queue('BTCUSDT','b'))
        self.assertIsNotNone(store.queue('BTCUSDT','q','manual'))
    def test_zone_visit_is_recorded_and_evaluated(self):
        from wave_monitor.reports import maintenance
        (store.ROOT/'config').mkdir()
        (store.ROOT/'config/settings.json').write_text(json.dumps({'symbols':['BTCUSDT'],'retention_days':45}))
        start=(int(time.time()//60)-62)*60
        store.record_zone_visit(start,'BTCUSDT',1,{'low':100,'high':105,'role':'support'},102,2)
        rows=[[int((start+i*60)*1000),102,106,101,105,10,int((start+(i+1)*60)*1000)-1,1] for i in range(60)]
        store.save_candles('BTCUSDT','1m',rows)
        maintenance()
        with store.db() as c:
            r=c.execute('SELECT outcome FROM zone_visits').fetchone()
        self.assertEqual(r['outcome'],'support_held')
    def test_seven_day_report_is_durable_and_sent_once(self):
        from wave_monitor.reports import maintenance
        (store.ROOT/'config').mkdir()
        (store.ROOT/'config/settings.json').write_text(json.dumps({'symbols':['BTCUSDT','ETHUSDT'],'retention_days':45}))
        store.put('started_at',time.time()-7*86400-10)
        maintenance()
        self.assertTrue(store.get('seven_day_report_sent'))
        self.assertTrue((store.ROOT/'data/reports/seven-day-review.txt').exists())
        with store.db() as c:before=c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]
        maintenance()
        with store.db() as c:after=c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]
        self.assertEqual(before,after)
    def test_ai_budget_stops_model_call_but_preserves_market_data(self):
        from wave_monitor.worker import process
        from unittest.mock import patch
        (store.ROOT/'config').mkdir()
        (store.ROOT/'config/settings.json').write_text(json.dumps({'auto_calls_per_day':0,'manual_calls_per_day':12}))
        store.save_candles('BTCUSDT','1m',[[1,10,12,9,11,5,60000,1]])
        with patch('wave_monitor.worker.run_codex') as model:
            self.assertEqual(process({'kind':'auto','reply_id':None}),'budget_limited')
            model.assert_not_called()
        self.assertEqual(store.candles('BTCUSDT','1m')[0]['c'],11)


if __name__=='__main__':unittest.main()
