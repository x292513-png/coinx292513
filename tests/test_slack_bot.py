import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock, Mock

from wave_monitor import slack_bot as bot


class SlackRoutingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = patch.object(bot.store, 'ROOT', Path(self.tmp.name))
        self.root.start()
        bot.init()
        self.cfg = {'channel_id': 'C1', 'allowed_user_ids': ['U1']}

    def tearDown(self):
        self.root.stop()
        self.tmp.cleanup()

    def event(self, **kw):
        return dict({'type': 'message', 'channel': 'C1', 'ts': '1.1', 'user': 'U1', 'text': '<@B1> 이더 손절 어디?'}, **kw)

    def test_retry_and_mention_duplicate_only_one_request(self):
        self.assertTrue(bot.ingest(self.event(), self.cfg, 'B1'))
        self.assertFalse(bot.ingest(self.event(type='app_mention'), self.cfg, 'B1'))
        self.assertFalse(bot.ingest(self.event(), self.cfg, 'B1'))

    def test_no_bot_loop_and_no_other_channel_or_user(self):
        for event in [self.event(bot_id='GROK'), self.event(channel='C2'), self.event(user='U2'), self.event(user='B1')]:
            self.assertFalse(bot.ingest(event, self.cfg, 'B1'))

    def test_followup_without_mention_and_grok_context(self):
        bot.ingest(self.event(), self.cfg, 'B1')
        self.assertFalse(bot.ingest(self.event(ts='1.2', thread_ts='1.1', bot_id='GROK', text='반등 관점'), self.cfg, 'B1'))
        self.assertTrue(bot.ingest(self.event(ts='1.3', thread_ts='1.1', text='그럼 익절은?'), self.cfg, 'B1'))
        self.assertEqual(len(bot.thread_context('C1', '1.1')), 3)
        self.assertFalse(bot.ingest(self.event(ts='1.4', thread_ts='1.1', text='<@GROK> 너는?'), self.cfg, 'B1'))
        self.assertTrue(bot.ingest(self.event(ts='1.5', thread_ts='1.1', text='익절은?\n다음을 사용하여 보냄 <@CONNECTOR>'), self.cfg, 'B1'))

    def test_unaddressed_messages_do_not_start_ai(self):
        self.assertFalse(bot.ingest(self.event(text='이더 어때?'), self.cfg, 'B1'))
        self.assertFalse(bot.ingest(self.event(ts='2.1', thread_ts='2.0', text='익절은?'), self.cfg, 'B1'))
        self.assertTrue(bot.ingest(self.event(ts='3.1', text='GPT 이더 어때?'), self.cfg, 'B1'))

    def test_restart_recovers_answer_without_reinference(self):
        bot.ingest(self.event(), self.cfg, 'B1')
        with bot.db() as c: c.execute("UPDATE requests SET status='running',answer='저장된 답'")
        bot.init()
        with bot.db() as c: row = c.execute('SELECT * FROM requests').fetchone()
        self.assertEqual(row['status'], 'ready')
        self.assertEqual(row['answer'], '저장된 답')

    def test_symbol_context_and_safe_formatting(self):
        history = [{'text': '비트 상승?'}, {'text': '그럼 손절은?'}]
        self.assertEqual(bot.symbols_for('그럼 손절은?', history), ['BTCUSDT'])
        self.assertEqual(bot.symbols_for('이더는?', history), ['ETHUSDT'])
        self.assertEqual(bot.clean_answer('<b>판단</b> **근거** <@U123>'), '*판단* *근거*')

    def test_chart_retry_keeps_text_and_avoids_new_ai_call(self):
        bot.ingest(self.event(), self.cfg, 'B1')
        with bot.db() as c:
            c.execute("UPDATE requests SET status='ready',answer='기존 답변',chart='chart.png'")
        slack = Mock()
        slack.send = AsyncMock(return_value={'ts': '2.0'})
        slack.upload = AsyncMock(side_effect=[RuntimeError('temporary_upload_failure'), None])

        async def once():
            with patch.object(bot.asyncio, 'sleep', AsyncMock(side_effect=asyncio.CancelledError)):
                with self.assertRaises(asyncio.CancelledError):
                    await bot.worker(slack, 'B1')

        with patch.object(bot, 'make_answer') as infer:
            asyncio.run(once())
            with bot.db() as c: row = c.execute('SELECT * FROM requests').fetchone()
            self.assertEqual((row['status'], row['reply_ts']), ('ready', '2.0'))
            asyncio.run(once())
            infer.assert_not_called()
        slack.send.assert_awaited_once()
        self.assertEqual(slack.upload.await_count, 2)
        with bot.db() as c: self.assertEqual(c.execute('SELECT status FROM requests').fetchone()[0], 'done')


if __name__ == '__main__': unittest.main()
