import unittest
import numpy as np
from wave_monitor.ict import detect,lifecycle


def candle(i,o,h,l,c):return dict(t=i*60000,close_t=(i+1)*60000-1,o=o,h=h,l=l,c=c,v=10)


class ICTTests(unittest.TestCase):
    def test_bearish_gap_correct_bounds_midpoint_and_later_retest(self):
        rows=[candle(0,110,112,108,109),candle(1,109,110,98,99),candle(2,99,102,96,98)]
        result=detect(rows,'5m',np.array([2.,2.,2.]))
        gap=result['active'][0]
        self.assertEqual((gap['low'],gap['high'],gap['mid']),(102,108,105))
        self.assertEqual(gap['status'],'untouched')
        rows.append(candle(3,101,105.5,100,102))
        g=next(z for z in detect(rows,'5m',np.full(4,2.))['active'] if z['id']==gap['id'])
        self.assertEqual(g['status'],'midpoint_touched');self.assertEqual(g['midpoint_touch'],180000)
    def test_bullish_gap_no_three_same_color_requirement(self):
        rows=[candle(0,99,101,98,100),candle(1,100,109,99,108),candle(2,108,110,104,105)]
        gap=detect(rows,'5m',np.full(3,2.))['active'][0]
        self.assertEqual(gap['direction'],'bullish');self.assertEqual(gap['mid'],102.5)
    def test_filled_and_invalidated_are_distinct(self):
        zone=dict(low=102,high=108,mid=105,direction='bearish')
        self.assertEqual(lifecycle(zone,[candle(3,103,109,102,107)])['status'],'filled')
        self.assertEqual(lifecycle(zone,[candle(3,103,110,102,109)])['status'],'invalidated')
    def test_ob_requires_displacement_gap_and_structure(self):
        rows=[candle(i,100,101,99,100.5) for i in range(8)]
        rows += [candle(8,100.5,101,98,99),candle(9,99,112,98.5,111),candle(10,111,114,108,113)]
        blocks=[z for z in detect(rows,'15m',np.full(len(rows),2.))['active'] if z['kind']=='OB']
        self.assertEqual(len(blocks),1)
        self.assertEqual((blocks[0]['low'],blocks[0]['high'],blocks[0]['mid']),(98,101,99.75))
        self.assertTrue(blocks[0]['local_range_break']);self.assertGreaterEqual(blocks[0]['formed_at'],rows[10]['close_t'])
        no_displacement=detect(rows,'15m',np.full(len(rows),100.))
        self.assertFalse(any(z['kind']=='OB' for z in no_displacement['active']))


if __name__=='__main__':unittest.main()
