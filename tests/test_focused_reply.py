import unittest
from wave_monitor.focused_reply import focus_frames,is_full_request
from wave_monitor.quick_reply import wants_quick
class FocusedTests(unittest.TestCase):
    def test_precise_timeframe_not_substring(self):
        self.assertEqual(focus_frames('15분봉 다이버전스'),['15m'])
        self.assertEqual(focus_frames('4시간봉과 1시간봉'),['1h','4h'])
    def test_question_routing(self):
        for q in ['비트 분석','이더 분석','분석해줘','BTC ETH 현재 분석해줘','손절 포함 새로 분석해줘']:
            self.assertTrue(is_full_request(q),q)
        for q in ['이더 15분봉 전저점 깨고 올라오면 손절 어떻게?','BTC 3파 아닌가?','그런데 FVG까지 기다리는게 낫지 않아?']:
            self.assertFalse(is_full_request(q),q)
            self.assertFalse(wants_quick(q),q)
        self.assertTrue(wants_quick('지금 들어간다면 손절 어디?'))
