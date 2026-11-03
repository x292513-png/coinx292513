import unittest,time
from unittest.mock import patch
from wave_monitor import news
from wave_monitor.learning import period_stats
from wave_monitor.focused_reply import is_full_request
from wave_monitor.cadence import can_alert

class RegimeNewsTests(unittest.TestCase):
 def test_three_percent_escalation(self):
  self.assertTrue(can_alert({'time':10,'change':-2.7},11,-3.0,1800))
  self.assertFalse(can_alert({'time':10,'change':-2.1},11,-2.9,1800))
 def test_outlook_not_specific_question(self):
  for q in ['지금 현재 이더리움 어떻게 보고 있는지','이더 어떻게 봐?','비트 전망 알려줘']:
   self.assertTrue(is_full_request(q),q)
  for q in ['이더 15분 RSI 다이버 어떻게 봐?','손절 어떻게 보고 있어?','이더 FVG 어떻게 봐?']:
   self.assertFalse(is_full_request(q),q)
 def test_disjoint_periods(self):
  original={'fvg':{'all':{'n':100,'counts':{'win':60}},'recent_365d':{'n':20,'counts':{'win':15}}}}
  result=period_stats(original)['fvg']
  self.assertEqual(result['before_365d']['n'],80)
  self.assertEqual(result['before_365d']['counts']['win'],45)
  self.assertEqual(result['recent_365d']['outcome_fractions']['win'],.75)
  self.assertNotIn('before_365d',original['fvg'])
 def test_feed_time_domain_and_relevance(self):
  from email.utils import formatdate
  now=time.time()
  def entry(url,age,title='Bitcoin ETF approval'):
   return f'<item><title>{title}</title><link>{url}</link><pubDate>{formatdate(now-age,usegmt=True)}</pubDate></item>'
  body='<rss><channel>'+entry('https://coindesk.com/a',60)+entry('https://evil.invalid/a',60)+entry('https://coindesk.com/old',49*3600)+entry('https://coindesk.com/random',60,'Celebrity gossip')+'</channel></rss>'
  self.assertEqual(len(news.parse_feed(body,'CoinDesk',now)),1)
 def test_stale_news_never_latest(self):
  with patch.object(news.store,'settings',return_value={'news_enabled':True}),patch.object(news.store,'get',return_value={'asof':0,'status':'ready','items':[]}):
   self.assertIn('확인 대기',news.blocks(86400)[0])
 def test_fresh_outlook_with_photo_is_not_old_chart_resend(self):
  from wave_monitor.chart_delivery import handle
  self.assertTrue(is_full_request('이더 지금 분석해서 사진도 줘'))
  self.assertFalse(handle('이더 지금 어떻게 봐? 사진도 줘',None,1))
 def test_pair_comparison_uses_matching_times_only(self):
  from wave_monitor.market_pair import context
  def candles(s,tf,limit):
   return [{'t':i*1000,'close_t':i*1000+999,'c':100+i*(1 if s=='BTCUSDT' else 2)} for i in range(6 if s=='BTCUSDT' else 5)]
  with patch('wave_monitor.market_pair.store.candles',side_effect=candles):r=context(10)
  self.assertEqual(r['15m']['bars'],5)
  self.assertEqual(r['15m']['last_close_t'],4999)
  self.assertGreater(r['15m']['return_correlation'],.99)
