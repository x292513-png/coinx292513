import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from wave_monitor import store,opportunities as op


class OpportunityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=patch.object(store,'ROOT',Path(self.tmp.name));self.root.start();store.init()
        self.cfg={'paper_enabled':True,'paper_opportunity_enabled':True,'paper_calls_per_day':12,'symbols':['ETHUSDT']}
        self.settings=patch.object(store,'settings',return_value=self.cfg);self.settings.start()
        self.now=72001
        self.raw={}
        for tf,step in [('5m',300000),('15m',900000),('1h',3600000)]:
            self.raw[tf]=[dict(t=72000000-step*(12-i),close_t=72000000-step*(11-i)-1,o=100,h=102,l=99,c=100,v=1) for i in range(12)]
        self.raw['5m'][-1].update(c=102,h=103)
        self.snap={'symbol':'ETHUSDT','price':{'price':102,'time':self.now},'frames':{
            tf:{'atr14':3,'pivots':[],'candidates':[],'divergences':[],'ict':{'active':[]}} for tf in self.raw},'entry_measurements':{'levels':[]}}
    def tearDown(self):self.settings.stop();self.root.stop();self.tmp.cleanup()
    def jobs(self):
        with store.db() as c:return [dict(r) for r in c.execute('SELECT * FROM jobs')]
    def test_multiple_families_without_divergence(self):
        bar=self.raw['5m'][-1];p={'t':bar['t']-900000,'price':101,'kind':'H','confirmed':True,'confirmed_at':bar['t']-1}
        f=self.snap['frames']['5m'];f['pivots']=[p]
        f['candidates']=[{'pattern':'impulse_5_candidate','points':[dict(p,confirmed_at=bar['close_t'])]}]
        self.snap['entry_measurements']['levels']=[{'id':'fib','tf':'5m','kind':'retracement','price':101}]
        kinds={x['kind'] for x in op.candidates(self.snap,self.raw)}
        self.assertTrue({'wave_structure','displacement','swing_breakout','reference_reaction'}<=kinds)
    def test_new_review_queued_once_with_books_instruction(self):
        op.consider(self.snap,self.raw,self.now);op.consider(self.snap,self.raw,self.now+1)
        jobs=self.jobs();self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]['kind'],'paper')
        self.assertIn('서적',jobs[0]['question']);self.assertIn('채널',jobs[0]['question'])
    def test_paused_stale_and_gap_do_not_queue(self):
        store.put('paused',True);op.consider(self.snap,self.raw,self.now);self.assertEqual(self.jobs(),[])
        store.put('paused',False);self.snap['price']['time']=self.now-31
        op.consider(self.snap,self.raw,self.now);self.assertEqual(self.jobs(),[])
        self.snap['price']['time']=self.now;self.raw['15m'][-2]['t']-=1
        op.consider(self.snap,self.raw,self.now);self.assertEqual(self.jobs(),[])
    def test_pending_jobs_count_against_budget(self):
        self.cfg['paper_calls_per_day']=1;store.queue('BTCUSDT','paper_opportunity','paper')
        op.consider(self.snap,self.raw,self.now)
        self.assertEqual(len(self.jobs()),1);self.assertEqual(store.get('opportunity_status:ETHUSDT')['reason'],'paper_daily_budget')
    def test_live_position_blocks_but_unfilled_limit_does_not(self):
        with store.db() as c:c.execute('INSERT INTO paper_plans VALUES (1,1,?,?)',('ETHUSDT',json.dumps({'symbol':'ETHUSDT','status':'armed'})))
        op.consider(self.snap,self.raw,self.now);self.assertEqual(len(self.jobs()),1)
        with store.db() as c:
            c.execute('DELETE FROM jobs');c.execute('UPDATE paper_plans SET state=?',(json.dumps({'symbol':'ETHUSDT','status':'open'}),))
        store.put('opportunity_bar:ETHUSDT',0)
        op.consider(self.snap,self.raw,self.now+1);self.assertEqual(len(self.jobs()),0)
        self.assertEqual(store.get('opportunity_status:ETHUSDT')['reason'],'position_open')
    def test_old_and_developing_divergence_not_new_signal(self):
        self.raw['5m'][-1].update(c=100)
        self.snap['frames']['5m']['divergences']=[{'type':'regular_bullish','status':'developing','points':[{'t':1},{'t':2,'confirmed_at':72000000}]}]
        self.assertEqual(op.candidates(self.snap,self.raw),[])
    def test_idle_chart_does_not_consume_model_call(self):
        self.raw['5m'][-1].update(c=100)
        op.consider(self.snap,self.raw,self.now);self.assertEqual(self.jobs(),[])
    def test_channel_reaction_can_trigger_without_divergence(self):
        self.raw['5m'][-1].update(c=100.5,h=101,l=99.5)
        self.snap['entry_measurements']['levels']=[{'id':'ch','tf':'5m','kind':'channel','lower':100,'mid':105,'upper':110}]
        result=op.candidates(self.snap,self.raw)
        self.assertEqual(len(result),1);self.assertEqual(result[0]['detail']['family'],'channel')
    def test_paper_worker_paused_and_separate_daily_budget(self):
        from wave_monitor.worker import process
        self.cfg.update(auto_calls_per_day=4,manual_calls_per_day=12,notification_mode='twice_daily',paper_calls_per_day=1)
        job={'id':1,'kind':'paper','reason':'paper_opportunity','symbol':'ETHUSDT','reply_id':None}
        store.put('paused',True)
        with patch('wave_monitor.worker.refresh_for_analysis') as refresh:
            self.assertEqual(process(job),'canceled');refresh.assert_not_called()
        store.put('paused',False)
        import time
        with store.db() as c:c.execute("INSERT INTO calls(started,kind) VALUES (?,'paper')",(time.time(),))
        with patch('wave_monitor.worker.refresh_for_analysis') as refresh:
            self.assertEqual(process(job),'budget_limited');refresh.assert_not_called()
        with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
