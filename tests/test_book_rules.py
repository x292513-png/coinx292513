import json,unittest
from pathlib import Path
from unittest.mock import patch
from wave_monitor import store
from wave_monitor.book_rules import impulse_price_check,context,citations,load,reading_context

class BookRulesTests(unittest.TestCase):
    def points(self,prices):
        return [dict(t=i*1000,price=p,kind='L' if i%2==0 else 'H',confirmed=True,confirmed_at=i*1000+100) for i,p in enumerate(prices)]
    def test_real_source_ids_unique_and_bound(self):
        with patch.object(store,'ROOT',Path(__file__).resolve().parents[1]):
            d=load();ids=[r['id'] for r in d['rules']]
            self.assertEqual(len(ids),len(set(ids)))
            for r in d['rules']:self.assertIn(r['source'],d['sources']);self.assertTrue(r['locator'])
            self.assertIn('Balan',citations(['EW01'])[0])
            with self.assertRaises(ValueError):citations(['made_up'])
    def test_direction_symmetry(self):
        p=self.points([100,110,105,125,115,130])
        for points in [p,[dict(x,price=250-x['price'],kind='H' if x['kind']=='L' else 'L') for x in p]]:
            r=impulse_price_check(points,10000)
            self.assertEqual(r['failed_rules'],[])
            self.assertIn('unverified',r['status'])
    def test_wrong_count_price_rules(self):
        for values,rule in [([100,110,99,125,115,130],'EW01'),([100,110,105,125,109,130],'EW03'),([100,120,115,130,125,145],'EW02')]:
            self.assertIn(rule,impulse_price_check(self.points(values),10000)['failed_rules'])
    def test_unfinished_fifth_does_not_certify_shortest_rule(self):
        p=self.points([100,120,115,130,125,145]);p[-1].update(confirmed=False,confirmed_at=None)
        r=impulse_price_check(p,10000)
        self.assertNotIn('EW02',r['failed_rules']);self.assertEqual(r['status'],'developing_not_confirmed')
    def test_no_future_confirmation_and_invalid_input(self):
        p=self.points([100,110,105,125,115,130]);p[-1]['confirmed_at']=20000
        self.assertEqual(impulse_price_check(p,10000)['status'],'confirmation_not_known_at_asof')
        p[0]['price']=float('nan')
        self.assertEqual(impulse_price_check(p,10000)['status'],'invalid_input')
    def test_context_scoped_and_bounded(self):
        with patch.object(store,'ROOT',Path(__file__).resolve().parents[1]):
            s={'asof':10,'frames':{'1h':{'major_pivots':self.points([100,110,105,125,115,130]),'candidates':[{'pattern':'impulse_5_candidate'}]}}}
            c=context(s);ids=[r['id'] for r in c['rules']]
            self.assertIn('EW01',ids);self.assertIn('QA01',ids);self.assertNotIn('HA01',ids)
            self.assertLessEqual(len(json.dumps(c['rules'],ensure_ascii=False)),11000)
            self.assertIn('1h',c['point_checks'])

    def test_full_reading_reaches_final_model_input(self):
        from wave_monitor.worker import compact_input
        with patch.object(store,'ROOT',Path(__file__).resolve().parents[1]):
            s={'asof':10,'frames':{},'profiles':[],'question':'삼각수렴 E파와 손절 분석'}
            s['book_knowledge']=context(s)
            r=compact_input(s)['book_knowledge']['reading']
            self.assertIn('triangle',r['retrieval_topics'])
            self.assertIn('B–D',r['protocol'])
            self.assertIn('잔량',r['protocol'])
            self.assertTrue(any('삼각' in x['text'] for x in r['relevant_sections']))
            self.assertLessEqual(len(json.dumps(r['relevant_sections'],ensure_ascii=False)),8000)
            self.assertIn('누락',r['source_gap'])

    def test_harmonic_anchor_errata_are_available_without_overriding_wave_protocol(self):
        with patch.object(store,'ROOT',Path(__file__).resolve().parents[1]):
            r=reading_context({'question':'하모닉 Shark Cypher XA XC 앵커','frames':{}})
            self.assertTrue(any(x['record']=='06-harmonic.md' for x in r['relevant_sections']))
            self.assertIn('Shark',r['protocol']);self.assertIn('XC',r['protocol'])
            self.assertIn('파동부터',r['protocol'])
            ordinary=reading_context({'question':'현재 임펄스','frames':{}})
            self.assertFalse(any(x['record']=='06-harmonic.md' for x in ordinary['relevant_sections']))
