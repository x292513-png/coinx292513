import asyncio,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from aiohttp import web
from wave_monitor import store,paper_queries
from wave_monitor.engine import inbox
from integration import telegram_bridge

class QueryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=patch.object(store,'ROOT',Path(self.tmp.name));self.root.start();store.init()
  self.cfg={'topic_id':10,'paper_topic_id':20,'chat_id':30,'allowed_user':40,'bridge_key':'test'}
  self.runtime=patch.object(store,'runtime',return_value=self.cfg);self.runtime.start()
  self.settings=patch.object(store,'settings',return_value={'symbols':['BTCUSDT','ETHUSDT']});self.settings.start()
  store.put('paper_topic_id',20);store.put('paper_started',time.time());store.put('paused',True)
 def tearDown(self):self.settings.stop();self.runtime.stop();self.root.stop();self.tmp.cleanup()
 def request(self,text,mid=1,**kw):
  data={'topic_id':20,'chat_id':30,'user_id':40,'message_id':mid,'text':text,**kw}
  return SimpleNamespace(headers={'X-Wave-Key':'test'},json=AsyncMock(return_value=data))
 def test_start_and_natural_queries_read_only_and_deduplicate(self):
  with patch.object(store,'queue') as queue:
   for i,text in enumerate(['/start@my_bot','지금 잔고 얼마야','현재 포지션','이더 언제 왜 들어갔어?']):
    request=self.request(text,i+1);asyncio.run(inbox(request));asyncio.run(inbox(request))
   queue.assert_not_called()
  self.assertTrue(store.get('paused'))
  with store.db() as c:
   rows=c.execute('SELECT * FROM outbox').fetchall();self.assertEqual(len(rows),4)
   self.assertTrue(all(r['topic_id']==20 and r['reply_id'] for r in rows))
   self.assertEqual(c.execute('SELECT COUNT(*) FROM paper_events').fetchone()[0],0)
 def test_forbidden_user_chat_topic(self):
  for kw in [{'user_id':41},{'chat_id':31},{'topic_id':21}]:
   with self.assertRaises(web.HTTPForbidden):asyncio.run(inbox(self.request('/start',**kw)))
 def test_unknown_command_does_not_execute(self):
  asyncio.run(inbox(self.request('/buy')))
  with store.db() as c:self.assertIn('조회용',c.execute('SELECT text FROM outbox').fetchone()[0])
 def test_open_position_details_and_no_fake_coin_units(self):
  now=time.time();p=dict(id=1,analysis_id=1,symbol='ETHUSDT',status='open',sign=1,qty=.1,average=100,stop=95,tp1=110,tp2=120,take=.5,amount=10,add_amount=0,added=False,tp1_done=False,entry_time=now-300,hold_hours=4,reason='confirmed close',rules={'confirmation_tf':'5m'})
  result={'trade_plan':{'entry_reason':'support <test>','position_plan':{'thesis_timeframe':'4h','entry_timeframe':'15m','stop_timeframe':'1h'}},'entry_logic':{'confluence':'wave and support'}}
  with store.db() as c:
   c.execute('INSERT INTO paper_plans VALUES (1,1,?,?)',('ETHUSDT',json.dumps(p)))
   c.execute('INSERT INTO analyses(id,result) VALUES (1,?)',(json.dumps(result),))
  store.put('price:ETHUSDT',{'price':105,'time':now});store.put('paper_heartbeat',now)
  from wave_monitor.presentation import pages
  text='\n'.join(pages(paper_queries.answer('이더 보유 포지션',now)))
  for expected in ['100.50','+0.500','진입 시각','4h','잔량 목표','support &lt;test&gt;','코인 수량']:self.assertIn(expected,text)
  self.assertNotIn('0.1 ETH',text)
 def test_bridge_routes_slash_and_natural_but_preserves_other_topics(self):
  bot=SimpleNamespace(handle_text=AsyncMock());original=bot.handle_text
  telegram_bridge.install(bot)
  def update(topic,user=40):
   return SimpleNamespace(effective_message=SimpleNamespace(message_thread_id=topic,is_topic_message=True,reply_to_message=None,message_id=5,text='/start'),effective_chat=SimpleNamespace(id=30),effective_user=SimpleNamespace(id=user))
  with patch.object(Path,'read_text',return_value=json.dumps(self.cfg)),patch.object(telegram_bridge,'forward',return_value={'ok':True}) as forward:
   asyncio.run(bot.handle_text(update(20),None));asyncio.run(bot.handle_text(update(10),None));asyncio.run(bot.handle_text(update(99),None));asyncio.run(bot.handle_text(update(20,41),None))
   self.assertEqual(forward.call_count,2);original.assert_awaited_once()
