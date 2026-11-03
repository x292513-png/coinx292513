import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from aiohttp.test_utils import TestClient,TestServer
from aiohttp import web
from wave_monitor import store
from wave_monitor.engine import inbox


class InboxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=store.ROOT;store.ROOT=Path(self.tmp.name)
        (store.ROOT/'config').mkdir()
        (store.ROOT/'config/runtime.json').write_text(json.dumps({'bridge_key':'test-secret','allowed_user':10,'chat_id':-100,'topic_id':50}))
        (store.ROOT/'config/settings.json').write_text(json.dumps({'symbols':['BTCUSDT','ETHUSDT'],'auto_calls_per_day':4,'manual_calls_per_day':12,'notification_mode':'twice_daily','briefing_hours_kst':[9,21]}))
        store.init();app=web.Application();app.router.add_post('/inbox',inbox)
        self.client=TestClient(TestServer(app));await self.client.start_server()
    async def asyncTearDown(self):
        await self.client.close();store.ROOT=self.old;self.tmp.cleanup()
    async def test_natural_eth_outlook_is_full_eth_only(self):
        r=await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=27,text='지금 현재 이더리움 어떻게 보고 있는지'),headers={'X-Wave-Key':'test-secret'})
        self.assertEqual(r.status,200)
        with store.db() as c:rows=c.execute('SELECT symbol,reason FROM jobs').fetchall()
        self.assertEqual([(r['symbol'],r['reason']) for r in rows],[('ETHUSDT','user_followup')])

    async def test_auth_and_unrelated_topics_are_rejected(self):
        payload=dict(user_id=10,chat_id=-100,topic_id=50,message_id=1,text='BTC 분석')
        r=await self.client.post('/inbox',json=payload);self.assertEqual(r.status,403)
        for field in ['user_id','chat_id','topic_id']:
            wrong={**payload,field:999}
            r=await self.client.post('/inbox',json=wrong,headers={'X-Wave-Key':'test-secret'});self.assertEqual(r.status,403)
        with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
    async def test_reply_resolves_original_analysis_and_deduplicates(self):
        with store.db() as c:
            c.execute("INSERT INTO analyses(id,symbol) VALUES (7,'ETHUSDT')")
            c.execute("INSERT INTO messages VALUES (99,7,1,'outgoing')")
        payload=dict(user_id=10,chat_id=-100,topic_id=50,message_id=12,text='나는 이거 C파 같은데?',reply_id=99)
        for _ in range(2):
            r=await self.client.post('/inbox',json=payload,headers={'X-Wave-Key':'test-secret'});self.assertEqual(r.status,200)
        with store.db() as c:
            rows=c.execute('SELECT symbol,analysis_ref,question FROM jobs').fetchall()
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['symbol'],'ETHUSDT');self.assertEqual(rows[0]['analysis_ref'],7)
    async def test_stop_and_start_aliases_change_only_wave_state(self):
        for mid,text,state in [(1,'/stop',True),(2,'start',False),(3,'스탑',True),(4,'/start@wave_bot',False),(5,'/pause',True),(6,'/resume',False)]:
            r=await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=mid,text=text),headers={'X-Wave-Key':'test-secret'})
            self.assertEqual(r.status,200);self.assertEqual(store.get('paused'),state)

    async def test_other_command_restarts_paused_briefings(self):
        store.put('paused',True)
        payload=dict(user_id=10,chat_id=-100,topic_id=50,message_id=20,text='/status')
        r=await self.client.post('/inbox',json=payload,headers={'X-Wave-Key':'test-secret'})
        self.assertEqual(r.status,200);self.assertFalse(store.get('paused'))
        with store.db() as c:self.assertIn('다시 시작',c.execute('SELECT text FROM outbox').fetchone()[0])

    async def test_fractal_command_does_not_call_ai(self):
        payload=dict(user_id=10,chat_id=-100,topic_id=50,message_id=30,text='/fractal')
        r=await self.client.post('/inbox',json=payload,headers={'X-Wave-Key':'test-secret'})
        self.assertEqual(r.status,200)
        with store.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
            self.assertIn('프랙탈',c.execute('SELECT text FROM outbox').fetchone()[0])

    async def test_analyze_now_queues_both_symbols_without_waiting_for_briefing(self):
        with store.db() as c:
            for i in range(4):c.execute("INSERT INTO calls(started,kind) VALUES (1,'auto')")
        payload=dict(user_id=10,chat_id=-100,topic_id=50,message_id=40,text='분석해줘')
        with patch('wave_monitor.engine.time.time',return_value=10000):
            response=await self.client.post('/inbox',json=payload,headers={'X-Wave-Key':'test-secret'})
        self.assertEqual(response.status,200)
        with store.db() as c:
            jobs=c.execute('SELECT symbol,kind,status,created FROM jobs').fetchall()
            notice=c.execute('SELECT text FROM outbox').fetchone()[0]
        self.assertEqual({r['symbol'] for r in jobs},{'BTCUSDT','ETHUSDT'})
        self.assertTrue(all(r['kind']=='manual' and r['status']=='pending' and r['created']==10000 for r in jobs))
        self.assertIn('지금 기준',notice)

    async def test_named_analysis_only_requests_that_symbol(self):
        payload=dict(user_id=10,chat_id=-100,topic_id=50,message_id=41,text='이더 지금 분석해줘')
        response=await self.client.post('/inbox',json=payload,headers={'X-Wave-Key':'test-secret'})
        self.assertEqual(response.status,200)
        with store.db() as c:self.assertEqual([tuple(r) for r in c.execute('SELECT symbol,kind FROM jobs')],[('ETHUSDT','manual')])

    async def test_exact_korean_analysis_commands(self):
        for mid,text,symbol in [(51,'비트 분석','BTCUSDT'),(52,'이더 분석','ETHUSDT')]:
            response=await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=mid,text=text),headers={'X-Wave-Key':'test-secret'})
            self.assertEqual(response.status,200)
            with store.db() as c:
                row=c.execute('SELECT symbol,kind,question FROM jobs WHERE reply_id=?',(mid,)).fetchone()
            self.assertEqual(tuple(row),(symbol,'manual',text))

    async def test_freeform_rsi_question_is_not_full_analysis_or_cached_stop(self):
        from unittest.mock import AsyncMock
        question='지금 15분봉 기준 이더리움 전저점 살짝 깨고 올리면 RSI 다이버전스 컨펌 같은데 저점 손절 어때?'
        with patch('wave_monitor.quick_reply.answer',new_callable=AsyncMock) as quick:
            response=await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=71,text=question),headers={'X-Wave-Key':'test-secret'})
        self.assertTrue((await response.json())['focused_question']);quick.assert_not_awaited()
        with store.db() as c:
            row=c.execute('SELECT symbol,reason,question FROM jobs WHERE reply_id=71').fetchone()
        self.assertEqual(tuple(row),('ETHUSDT','focused_question',question))

    async def test_natural_alert_setting_bypasses_ai_and_persists_rules(self):
        cfg=store.settings();cfg['sharp_move_rules']=[[5,3],[15,3],[60,4]]
        (store.ROOT/'config/settings.json').write_text(json.dumps(cfg))
        store.put('paused',True)
        response=await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=81,text='급락 이나 급등 최소 2% 이상 5분안에 진행시 바로 브리핑해줘'),headers={'X-Wave-Key':'test-secret'})
        self.assertTrue((await response.json())['alert_settings'])
        for symbol in ['BTCUSDT','ETHUSDT']:self.assertIn([5,2.0],store.get('sharp_rules:'+symbol))
        self.assertFalse(store.get('paused'))
        with store.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)

    async def test_missing_chart_request_resends_saved_briefing_without_ai(self):
        chart=store.ROOT/'chart.png';chart.write_bytes(b'test placeholder')
        with store.db() as c:c.execute('INSERT INTO analyses(id,symbol,chart,snapshot) VALUES (?,?,?,?)',(99,'ETHUSDT',str(chart),'{}'))
        store.put('last_briefing_analyses',[99])
        response=await self.client.post('/inbox',json=dict(user_id=10,chat_id=-100,topic_id=50,message_id=91,text='사진은왜 안줘?'),headers={'X-Wave-Key':'test-secret'})
        self.assertTrue((await response.json())['chart_resend'])
        with store.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],0)
            self.assertEqual(tuple(c.execute('SELECT text,chart,analysis_id,reply_id FROM outbox').fetchone()),('',str(chart),99,91))


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_unrelated_topic_keeps_original_handler(self):
        source=Path(__file__).resolve().parents[1]/'integration/telegram_bridge.py'
        spec=importlib.util.spec_from_file_location('bridge_test',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        called=[]
        async def old(update,context):called.append('original')
        bot=SimpleNamespace(handle_text=old)
        with tempfile.TemporaryDirectory() as d:
            m.ROOT=Path(d);(m.ROOT/'config').mkdir();(m.ROOT/'config/runtime.json').write_text(json.dumps({'topic_id':50,'chat_id':-100,'allowed_user':10}))
            m.install(bot)
            update=SimpleNamespace(effective_message=SimpleNamespace(message_thread_id=2,is_topic_message=True),effective_chat=SimpleNamespace(id=-100))
            await bot.handle_text(update,None)
        self.assertEqual(called,['original'])


if __name__=='__main__':unittest.main()
