import json,tempfile,unittest,time,threading
from pathlib import Path
from unittest.mock import patch
from wave_monitor import store,team
class TeamTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=patch.object(store,'ROOT',Path(self.tmp.name));self.root.start();store.init()
  self.cfg=patch.object(store,'settings',return_value={'team_enabled':True,'team_calls_per_day':3,'team_timeout_seconds':15});self.cfg.start()
  self.snap={'symbol':'BTCUSDT','asof':time.time(),'price':{'price':100},'frames':{'15m':{'last_closed':{'c':100}}}}
 def tearDown(self):self.cfg.stop();self.root.stop();self.tmp.cleanup()
 def runner(self,*args,**kwargs):
  return dict(stance='mixed',summary='확정봉 구조 비교',evidence=[dict(reference='frame:15m',observation='입력 종가 100')],concerns=[],execution_constraints='구조 확인 필요'),{'input_tokens':10},.1
 def test_independent_calls_persist_usage_and_coordinator_ready_reports(self):
  report=team.review(self.snap,{'id':1},self.runner)
  self.assertEqual(report['status'],'complete');self.assertEqual(len(report['reports']),3)
  with store.db() as c:
   self.assertEqual(c.execute("select count(*) from calls where kind='team' and ok=1").fetchone()[0],3)
   self.assertEqual(c.execute("select count(*) from team_reviews where status='ok'").fetchone()[0],3)
  self.assertEqual(team.review(self.snap,{'id':2},self.runner)['status'],'not_run_budget_or_duplicate')
 def test_budget_requires_complete_reservation_before_any_call(self):
  with patch.object(store,'settings',return_value={'team_enabled':True,'team_calls_per_day':2}):
   r=team.review(self.snap,{'id':1},lambda *a,**k:self.fail('must not call'))
  self.assertEqual(r['reports'],[])
  with store.db() as c:self.assertEqual(c.execute('select count(*) from calls').fetchone()[0],0)
 def test_fabricated_reference_is_unavailable_and_counted(self):
  def wrong(*args,**kwargs):
   r,u,t=self.runner();r['evidence'][0]['reference']='invented';return r,u,t
  r=team.review(self.snap,{'id':1},wrong)
  self.assertEqual(r['status'],'partial');self.assertTrue(all(x['status']=='unavailable' for x in r['reports']))
  with store.db() as c:self.assertEqual(c.execute('select count(*) from calls').fetchone()[0],3)
  self.assertIn('응답 미확보',team.display(r))
 def test_failure_does_not_fabricate_agreement(self):
  def fail(*a,**k):raise RuntimeError('timeout')
  r=team.review(self.snap,{'id':1},fail)
  self.assertEqual(r['status'],'partial');self.assertNotIn('report',r['reports'][0])
 def test_restart_releases_only_unstarted_reservations(self):
  self.assertTrue(team.reserve(1,time.time(),3));team.recover()
  self.assertTrue(team.reserve(2,time.time(),3))
 def test_no_more_than_two_parallel_workers(self):
  lock=threading.Lock();active=0;peak=0
  def run(*a,**k):
   nonlocal active,peak
   with lock:active+=1;peak=max(peak,active)
   time.sleep(.02)
   with lock:active-=1
   return self.runner()
  team.review(self.snap,{'id':1},run);self.assertEqual(peak,2)
