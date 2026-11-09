import json,time
from test_paper import PaperTests
from wave_monitor import paper,store,position_management as pm

class ManagementTests(PaperTests):
 def opened(self):
  p=self.plan();self.runbar(p);return p
 def decision(self,**kw):
  return dict(action='hold',reason='15분봉 지지와 파동 가설이 유효하여 종가까지 관찰',stop_mode='close',stop_tf='15m',stop=95,emergency_stop=90,tp1=115,tp2=125,entry_low=98,entry_high=105,add_margin_pct=5,reduce_pct=50,review_hours=2,**kw)
 def attach(self,p,d,created=179):
  p['pending_management']=dict(created=created,expires=created+300,expected=pm.fingerprint(p),decision=d,team_complete=True)
 def test_future_only_and_wick_not_close(self):
  p=self.opened();self.attach(p,self.decision(),created=180)
  self.runbar(p,t=180,o=100,l=94,h=101,c=98)
  self.assertEqual(p['status'],'open');self.assertEqual(p['stop_mode'],'close')
  self.assertEqual(p['management_revision'],1)
  self.runbar(p,t=240,o=98,l=94,h=99,c=97)
  self.assertEqual(p['management_revision'],1)
 def test_no_retroactive_review(self):
  p=self.opened();self.attach(p,self.decision(),created=250)
  self.runbar(p,t=180,o=100,l=99,h=101)
  self.assertNotIn('stop_mode',p);self.assertIn('pending_management',p)
 def test_emergency_wick_exits(self):
  p=self.opened();self.attach(p,self.decision())
  self.runbar(p,t=180,o=100,l=89,h=101)
  self.assertEqual(p['status'],'closed')
  with store.db() as c:self.assertEqual(c.execute("SELECT price FROM paper_events WHERE kind='stop'").fetchone()[0],90)
 def test_completed_thesis_candle_exits(self):
  p=self.opened();self.attach(p,self.decision());self.runbar(p,t=180,o=100,l=98,h=101)
  store.save_candles('BTCUSDT','15m',[[0,100,102,92,94,1,899999,1]])
  self.runbar(p,t=840,o=97,l=93,h=98,c=94)
  self.assertEqual(p['status'],'closed')
 def test_old_gap_protection_not_erased(self):
  p=self.opened();self.attach(p,self.decision());self.runbar(p,t=180,o=94,l=92,h=96)
  self.assertEqual(p['status'],'closed');self.assertNotIn('management_revision',p)
 def test_reduce_at_future_open(self):
  p=self.opened();d=self.decision();d['action']='reduce';self.attach(p,d)
  self.runbar(p,t=180,o=101,l=100,h=102)
  self.assertAlmostEqual(p['qty'],.05)
  with store.db() as c:self.assertAlmostEqual(paper.account(c),100.05)
 def test_exit_future_open(self):
  p=self.opened();d=self.decision();d['action']='exit';self.attach(p,d)
  self.runbar(p,t=180,o=101,l=100,h=102)
  self.assertEqual(p['status'],'closed')
 def test_stale_or_changed_position_no_apply(self):
  p=self.opened();self.attach(p,self.decision());p['qty']/=2
  self.runbar(p,t=180,o=100,l=99,h=101);self.assertNotIn('management_revision',p)
  self.attach(p,self.decision(),created=0)
  self.runbar(p,t=600,o=100,l=99,h=101);self.assertNotIn('management_revision',p)
 def test_add_requires_band_rr_and_complete_team(self):
  p=self.opened();d=self.decision();d['action']='add';d['tp1']=120;d['tp2']=130
  pm.validate(d,p,100)
  with self.assertRaises(ValueError):pm.validate(d,p,106)
  with self.assertRaises(ValueError):pm.validate(d,p,100,False)
  self.attach(p,d);self.runbar(p,t=180,o=100,l=99,h=101)
  self.assertAlmostEqual(p['qty'],.15)
 def test_liquidation_boundary_rejected(self):
  p=self.opened();p.update(margin_mode='isolated',leverage=10,maintenance_rate=.005)
  d=self.decision();d['emergency_stop']=80
  with self.assertRaises(ValueError):pm.validate(d,p,100)
 def test_short_close_stop_and_risk_uses_emergency(self):
  p=self.opened();p.update(sign=-1,stop=105,stop_mode='close',stop_tf='15m',emergency_stop=110,management_since=180)
  with store.db() as c:
   self.assertIsNone(pm.close_stop(c,p,self.bar(t=180,o=100,h=106,l=99)))
   self.assertEqual(pm.close_stop(c,p,self.bar(t=240,o=100,h=111,l=99)),110)
  self.assertAlmostEqual(paper.reserve(p)[1],1)
