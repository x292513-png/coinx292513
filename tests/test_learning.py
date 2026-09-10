import json
import math
import unittest
from unittest.mock import patch
import numpy as np
from wave_monitor.learning import analogs, fvg_samples, triangle_samples, stats, contiguous
from wave_monitor.presentation import pack,pages,quoted,units,format_analysis


def rows(n):
    return [dict(t=i*60000,close_t=(i+1)*60000-1,o=100+math.sin(i*.3),h=101+math.sin(i*.3),l=99+math.sin(i*.3),c=100+math.sin(i*.3),v=10) for i in range(n)]


class LearningTests(unittest.TestCase):
    def test_analog_has_no_future_or_overlap(self):
        data=rows(1000);query=data[-32:];a=analogs(data,query,12,data[-1]['close_t'])
        self.assertGreater(a['n'],0)
        for x in a['examples']:self.assertLess(x['outcome_end'],query[0]['t'])
        # Changing data at/after the query cannot change historical examples.
        altered=[dict(r) for r in data]
        for r in altered[-40:]:r['c']*=2
        b=analogs(altered,query,12,data[-1]['close_t'])
        self.assertEqual(a,b)

    def test_gaps_excluded_and_month_boundary_supported(self):
        data=rows(3);self.assertTrue(contiguous(data))
        self.assertFalse(contiguous([data[0],data[2]]))
        self.assertTrue(contiguous([{'t':0,'close_t':28*86400000-1},{'t':28*86400000,'close_t':59*86400000-1}]))

    def test_fvg_formation_not_counted_as_retouch_and_matures(self):
        data=rows(45)
        data[14].update(o=99,h=100,l=98,c=99)
        data[15].update(o=99,h=105,l=99,c=104)
        for r in data[16:]:r.update(o=105,h=107,l=104,c=106)
        a=fvg_samples(data,np.ones(len(data)),horizon=24)
        self.assertTrue(a)
        x=next(x for x in a if x['t']==data[16]['close_t'])
        self.assertFalse(x['CE_touched']);self.assertEqual(x['outcome'],'no_CE_touch')
        self.assertEqual(fvg_samples(data[:30],np.ones(30),24),[])

    def test_stats_excludes_unknown_future_outcomes(self):
        data=[{'kind':'k','t':10,'known_until':20,'outcome':'a'},{'kind':'k','t':11,'known_until':99,'outcome':'b'}]
        s=stats(data,50)['k']['all'];self.assertEqual(s['n'],1);self.assertTrue(s['small_sample'])

    def test_query_gap_prevents_retrieval(self):
        data=rows(200);query=data[-32:];query[10]={**query[10],'t':query[10]['t']+1}
        self.assertEqual(analogs(data,query,12,data[-1]['close_t'])['reason'],'current_query_has_data_gap')

    def test_triangle_early_turn_is_measured_after_D_confirmation(self):
        data=rows(80)
        points=[dict(t=data[i]['t'],price=p,kind=k,confirmed=True,confirmed_at=data[i+2]['close_t']) for i,p,k in [(15,90,'L'),(20,110,'H'),(25,92,'L'),(30,108,'H')]]
        for i in range(33,57):
            line=92+.2*(i-25)
            data[i].update(l=line+.3,h=line+1,c=line+.9,o=line+.6)
        with patch('wave_monitor.learning.pivots',return_value=points):
            x=triangle_samples(data,np.ones(80))[0]
        self.assertEqual(x['outcome'],'early_reversal');self.assertAlmostEqual(x['distance_ATR'],.3)
        self.assertEqual(x['t'],data[32]['close_t'])


class PresentationTests(unittest.TestCase):
    def test_long_unicode_preserves_html_boundaries(self):
        blocks=quoted('🧩 상세 <조건>',('<a> & "조건" 🧭\n')*1000)
        ps=pages(pack(blocks));self.assertGreater(len(ps),1)
        for p in ps:
            self.assertLessEqual(units(p),3800)
            self.assertEqual(p.count('<blockquote expandable>'),p.count('</blockquote>'))
            self.assertNotIn('<a>',p);self.assertIn('&lt;',p)

    def test_plain_system_message_is_escaped(self):
        self.assertEqual(pages('가격 < 100 & 확인'),['가격 &lt; 100 &amp; 확인'])
        for p in pages('&'*5000):self.assertLess(units(p),3800)


if __name__=='__main__':unittest.main()
