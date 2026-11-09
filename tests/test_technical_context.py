import unittest,statistics,json
from wave_monitor.technical_context import measure
class TechnicalTests(unittest.TestCase):
 def rows(self):return [dict(c=i+10,h=i+12,l=i+8,close_t=i*60000,closed=1) for i in range(40)]
 def test_bands_and_stochastic_against_known_linear_series(self):
  r=measure(self.rows());b=r['bollinger'];s=r['stochastic']
  self.assertAlmostEqual(b['mid'],39.5)
  self.assertAlmostEqual(b['upper'],39.5+2*statistics.pstdev(range(30,50)),places=5)
  self.assertAlmostEqual(s['k'],100*15/17,places=5);self.assertAlmostEqual(s['d'],s['k'])
  self.assertEqual(s['cross'],'none')
 def test_open_candle_excluded(self):
  rows=self.rows();base=measure(rows)
  rows.append(dict(c=999,h=999,l=0,close_t=999999,closed=0))
  self.assertEqual(base,measure(rows))
 def test_flat_data_is_undefined_not_fake_signal(self):
  rows=[dict(c=10,h=10,l=10,close_t=i,closed=1) for i in range(40)]
  r=measure(rows);self.assertIsNone(r['bollinger']['percent_b']);self.assertIsNone(r['stochastic']['k'])
  self.assertEqual(r['stochastic']['cross'],'none');json.dumps(r,allow_nan=False)
 def test_short_history_not_fabricated(self):self.assertEqual(measure(self.rows()[:10])['status'],'insufficient_closed_candles')

 def test_closed_cross_and_band_reentry(self):
  rows=[dict(c=v,h=10,l=0,close_t=i,closed=1) for i,v in enumerate([5]*36+[2,2,2,5])]
  self.assertEqual(measure(rows)['stochastic']['cross'],'bullish')
  rows=[dict(c=v,h=v,l=v,close_t=i,closed=1) for i,v in enumerate([10]*38+[20,10])]
  self.assertEqual(measure(rows)['bollinger']['reentry'],'from_above')
