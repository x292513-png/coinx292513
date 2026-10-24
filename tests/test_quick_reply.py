import time
import unittest
from unittest.mock import patch,AsyncMock
from wave_monitor.quick_reply import short_answer,wants_quick
from test_integration import InboxTests

class QuickRoutingTests(InboxTests):
    async def test_ambiguous_stop_question_does_not_queue_full_analyses(self):
        r=await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=60,text='지금 들어간다면 손절 어디?'),headers={'X-Wave-Key':'test-secret'})
        self.assertTrue((await r.json())['quick_reply'])
        from wave_monitor import store
        with store.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
            self.assertIn('어느 종목',c.execute('SELECT text FROM outbox').fetchone()[0])
    async def test_single_symbol_context_routes_short_reply(self):
        from wave_monitor import store
        store.put('conversation_symbol',{'symbol':'ETHUSDT','time':time.time()})
        with patch('wave_monitor.quick_reply.answer',new_callable=AsyncMock) as answer:
            await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=61,text='지금 들어간다면 손절 어디?'),headers={'X-Wave-Key':'test-secret'})
        answer.assert_awaited_once_with('ETHUSDT',None,'지금 들어간다면 손절 어디?',61)
        with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)

class QuickAnswerTests(unittest.TestCase):
    def setUp(self):
        self.a={'id':1,'symbol':'BTCUSDT','created':1000,'snapshot':{'asof':1000},'result':{'bias':'bullish','invalidation_price':90,'invalidation_side':'below','trade_plan':{'enabled':True,'entry_low':99,'entry_high':101,'stop':90,'tp1':110,'tp2':120,'take_pct':50,'entry_rule':'5분봉 조건 확인','stop_reason':'파동 원점','breakeven_rule':'1차 익절 후','hold_rule':'구조 유지'}}}
    def test_stop_first_and_out_of_zone_no_chase(self):
        with patch('wave_monitor.store.get',return_value=None):
            msg=short_answer(self.a,{'price':105,'time':1010},1010,'손절 어디')
        self.assertTrue(msg.startswith('⛔ <b>롱 손절 기준 90.00'))
        self.assertIn('추격 진입은 대기',msg)
        self.assertIn('14.29%',msg)
    def test_old_and_invalidated_plans_are_not_reused(self):
        with patch('wave_monitor.store.get',return_value=None):
            self.assertIn('쓸 수 없습니다',short_answer(self.a,{'price':100,'time':9000},9000,'손절'))
        with patch('wave_monitor.store.get',return_value=1001):
            self.assertIn('쓸 수 없습니다',short_answer(self.a,{'price':100,'time':1010},1010,'손절'))
    def test_explicit_full_analysis_still_uses_full_path(self):
        self.assertTrue(wants_quick('지금 들어간다면 손절 어디?'))
        self.assertFalse(wants_quick('손절 포함 새로 분석해줘'))
