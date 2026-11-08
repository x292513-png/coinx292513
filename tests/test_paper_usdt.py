import unittest
import test_paper
from wave_monitor import paper,store

class USDTTests(unittest.TestCase):
 setUp=test_paper.PaperTests.setUp
 tearDown=test_paper.PaperTests.tearDown
 analysis=test_paper.PaperTests.analysis
 plan=test_paper.PaperTests.plan
 bar=test_paper.PaperTests.bar
 runbar=test_paper.PaperTests.runbar
 def test_new_account_preserves_history_and_is_idempotent(self):
  p=self.plan();self.runbar(p);self.runbar(p,t=180,l=90)
  self.assertTrue(paper.start_usdt_account(300));self.assertFalse(paper.start_usdt_account(400))
  with store.db() as c:
   self.assertEqual(paper.account(c),10000);self.assertEqual(paper.read_states(c),[])
   self.assertEqual(c.execute('select count(*) from paper_plans').fetchone()[0],1)
  self.assertEqual(store.get('paper_started'),300)
 def test_actual_qty_margin_and_risk(self):
  paper.start_usdt_account(60);a=self.analysis();a['result']['trade_plan']['stop']=99
  paper.register(a,60)
  with store.db() as c:p=paper.read_states(c)[0]
  self.assertEqual(p['amount'],5000);self.assertEqual(paper.reserve(p),(1000,50))
  self.runbar(p,l=99.5);self.assertEqual(p['qty'],50)
  self.runbar(p,t=180,o=105,l=104,h=111)
  self.assertEqual(p['qty'],25);self.assertEqual(paper.reserve(p)[0],500)
  with store.db() as c:self.assertEqual(paper.account(c),10250)
 def test_gap_loss_cannot_consume_other_collateral(self):
  paper.start_usdt_account(60);p=self.plan();self.runbar(p)
  margin=paper.reserve(p)[0]
  self.runbar(p,t=180,o=1,l=1,h=2,c=1)
  with store.db() as c:
   self.assertAlmostEqual(paper.account(c),10000-margin)
   self.assertEqual(c.execute('select kind from paper_events order by id desc limit 1').fetchone()[0],'liquidation')
 def test_stop_beyond_liquidation_rejected(self):
  paper.start_usdt_account(60);a=self.analysis();a['result']['trade_plan']['stop']=70
  paper.register(a,60)
  with store.db() as c:self.assertEqual(paper.read_states(c)[0]['status'],'skipped')
 def test_reports_new_account_only_and_currency(self):
  p=self.plan();self.runbar(p);paper.start_usdt_account(300)
  text=paper.summary(400,True)
  self.assertIn('10,000',text);self.assertIn('5배',text);self.assertIn('격리',text);self.assertNotIn('유닛',text)
  self.assertIn('현재 보유 없음',text)

 def test_short_profit_and_shared_portfolio_budget(self):
  paper.start_usdt_account(60);a=self.analysis();a['result']['bias']='bearish'
  a['result']['trade_plan'].update(stop=101,tp1=90,tp2=80)
  paper.register(a,60);paper.register(self.analysis(2,'ETHUSDT'),60)
  with store.db() as c:
   states=paper.read_states(c);p=states[0]
   self.assertLessEqual(sum(paper.reserve(x)[1] for x in states),100.000001)
   self.assertLessEqual(sum(paper.reserve(x)[0] for x in states),10000)
  self.runbar(p,o=100,h=100.5,l=99)
  self.runbar(p,t=180,o=95,h=96,l=89,c=90)
  with store.db() as c:self.assertEqual(paper.account(c),10250)
