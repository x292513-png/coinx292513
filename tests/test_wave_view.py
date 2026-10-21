import unittest
from wave_monitor.worker import validate_wave_view,SCHEMA
from wave_monitor.presentation import wave_blocks
from wave_monitor.analysis import TF_MS

class WaveViewTests(unittest.TestCase):
    def views(self):
        return [dict(tf=tf,trend='하락',count='상위 상승 내 C파 후보',weights=dict(impulse=20,abc=50,wxy=10,triangle=10,unclear=10),evidence='내부 구조 추가 확인') for tf in ['1d','4h','1h','15m']]
    def test_order_and_total(self):
        v=self.views();validate_wave_view(v)
        with self.assertRaises(ValueError):validate_wave_view(v[::-1])
        v[0]['weights']['abc']=51
        with self.assertRaises(ValueError):validate_wave_view(v)
    def test_hourly_data_and_disclosure(self):
        self.assertEqual(TF_MS['1h'],3600000)
        self.assertIn('1h',SCHEMA['properties']['frames']['items']['properties']['tf']['enum'])
        blocks=wave_blocks({'wave_view':self.views()})
        self.assertIn('1시간',blocks[0]);self.assertNotIn('50%',blocks[0])
        self.assertIn('ABC 50%',blocks[1]);self.assertIn('통계적 적중률 아님',blocks[1])
        self.assertIn('<blockquote expandable>',blocks[1])
        self.assertEqual(wave_blocks({}),[])
