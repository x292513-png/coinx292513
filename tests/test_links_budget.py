import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
from datetime import datetime,timezone
from wave_monitor import store
from wave_monitor.message_links import linkify,existing,message_url,ensure
from wave_monitor.budget import day_start,reset_label,notice

class LinkBudgetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=store.ROOT;store.ROOT=Path(self.tmp.name);store.init()
    def tearDown(self):store.ROOT=self.old;self.tmp.cleanup()
    def test_only_report_is_original(self):
        with store.db() as c:
            c.execute("INSERT INTO messages VALUES (50,102,20,'outgoing')")
        self.assertIsNone(existing(102))
        with store.db() as c:
            c.execute("INSERT INTO outbox(created,analysis_id,chart,status) VALUES (30,102,'chart.png','sent')")
            c.execute("INSERT INTO messages VALUES (70,102,31,'outgoing')")
        self.assertEqual(existing(102),70)
    def test_html_links_and_entities_preserved(self):
        page='<b>분석 #102의 조건</b> &amp; <a href="https://example.com/#102">#102</a><code>#102</code> #999'
        linked=linkify(page,{102:'https://t.me/c/1/2/70'})
        self.assertIn('<b>분석 <a href="https://t.me/c/1/2/70">#102</a>의 조건</b>',linked)
        self.assertIn('&amp;',linked);self.assertIn('<code>#102</code> #999',linked)
        self.assertEqual(linkify(linked,{102:'different'}),linked)
    def test_topic_url(self):
        with patch.object(store,'runtime',return_value={'chat_id':-1004324986998,'topic_id':4450}):
            self.assertEqual(message_url(70),'https://t.me/c/4324986998/4450/70')
    async def test_missing_analysis_not_linked(self):
        call=AsyncMock();self.assertIsNone(await ensure(999,call));call.assert_not_called()
    async def test_archive_is_restored_once_and_reply_mapping_saved(self):
        with store.db() as c:
            c.execute("INSERT INTO analyses(id,snapshot,result) VALUES (102,'{}','{}')")
        call=AsyncMock(return_value={'message_id':90})
        with patch.object(store,'runtime',return_value={'chat_id':-1004324986998,'topic_id':4450}), patch('wave_monitor.presentation.format_analysis',return_value='saved report'):
            first=await ensure(102,call)
            self.assertEqual(await ensure(102,call),first)
        call.assert_awaited_once()
        self.assertIn('현재 진입 신호 아님',call.call_args.args[1]['text'])
        with store.db() as c:self.assertEqual(c.execute('SELECT analysis_id FROM messages WHERE message_id=90').fetchone()[0],102)
    async def test_outbox_send_signature_and_original_registration(self):
        from wave_monitor import telegram
        call=AsyncMock(side_effect=[{'message_id':91},{'message_id':92}])
        with patch.object(store,'runtime',return_value={'chat_id':-1004324986998,'topic_id':4450}),patch.object(telegram,'call',call):
            ids=await telegram.send('분석 #102','chart.png',None,102)
        self.assertEqual(ids,[91,92]);self.assertEqual(existing(102),91)
        self.assertEqual(call.await_count,2)
    def test_korean_midnight_boundary(self):
        before=datetime(2026,9,11,14,59,59,tzinfo=timezone.utc).timestamp()
        self.assertEqual(reset_label(before),'2026-09-12 00:00 KST')
        self.assertEqual(day_start(before+1)-day_start(before),86400)
        self.assertEqual(reset_label(before+1),'2026-09-13 00:00 KST')
        self.assertIn('48/48',notice('auto',48,48,before))
