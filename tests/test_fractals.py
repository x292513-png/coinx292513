import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from wave_monitor import store,fractals
from wave_monitor.learning import db


class FractalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=store.ROOT;store.ROOT=Path(self.tmp.name)
        (store.ROOT/'config').mkdir();(store.ROOT/'config/settings.json').write_text(json.dumps({'symbols':['BTCUSDT']}));store.init()
        self.values=np.exp(4.5+.05*np.sin(np.arange(400)*2*np.pi/24)+.001*np.arange(400))
        with db() as c:
            c.executemany('INSERT INTO bars VALUES (?,?,?,?,?,?,?,?,?,?)',[('futures','BTCUSDT','1h',i*3600000,float(v),float(v*1.001),float(v*.999),float(v),1,(i+1)*3600000-1) for i,v in enumerate(self.values)])
    def tearDown(self):store.ROOT=self.old;self.tmp.cleanup()

    def test_price_scale_and_duration_normalization(self):
        x=np.exp(.1*np.linspace(0,1,24)+.05*np.sin(np.linspace(0,4*np.pi,24)))
        f,_=fractals.features([x,x*1000]);np.testing.assert_allclose(f[0],f[1],atol=1e-5)
        y=np.exp(.1*np.linspace(0,1,96)+.05*np.sin(np.linspace(0,4*np.pi,96)))
        g,_=fractals.features([y]);self.assertLess(float(np.sqrt(np.mean((f[0]-g[0])**2))),.1)

    def test_future_return_never_changes_past_shape(self):
        d=fractals.build_dataset('futures','BTCUSDT','1h',48)
        shape=np.load(fractals.root()/d['features'])[0].copy();old=np.load(fractals.root()/d['meta'])[0]['return_pct']
        with db() as c:c.execute("UPDATE bars SET c=c*1.2 WHERE t=?",(71*3600000,))
        with patch.object(fractals,'VERSION',fractals.VERSION+1):new=fractals.build_dataset('futures','BTCUSDT','1h',48)
        np.testing.assert_array_equal(shape,np.load(fractals.root()/new['features'])[0])
        self.assertNotEqual(old,np.load(fractals.root()/new['meta'])[0]['return_pct'])

    def test_cross_frame_match_and_knowledge_are_persistent(self):
        index=fractals.build()
        query=[{'t':2000000000000+i*86400000,'close_t':2000000000000+(i+1)*86400000-1,'c':float(v*10)} for i,v in enumerate(self.values[:48])]
        result=fractals.match_context('BTCUSDT',{'1d':query},query[-1]['close_t']/1000+1)
        found=result['queries']['1d'];self.assertGreater(found['n'],0)
        for e in found['examples']:
            self.assertNotEqual(e['source_tf'],'1d');self.assertLess(e['known'],query[0]['t'])
            self.assertIn(e['id'],json.dumps(result))
        self.assertTrue((store.ROOT/'data/knowledge/fractal-knowledge.md').exists())
        self.assertEqual(index['native_bars'],400)

    def test_resampling_preserves_close_and_excludes_gap(self):
        fractals.resample_history()
        with db() as c:
            row=c.execute("SELECT * FROM bars WHERE tf='2h' ORDER BY t LIMIT 1").fetchone()
            self.assertEqual(row['c'],self.values[1]);self.assertEqual(row['close_t'],7200000-1)
            c.execute("DELETE FROM bars WHERE tf='2h'")
            c.execute("DELETE FROM bars WHERE tf='1h' AND t=3600000")
        fractals.resample_history()
        with db() as c:self.assertIsNone(c.execute("SELECT 1 FROM bars WHERE tf='2h' AND t=0").fetchone())

    def test_overlapping_markets_and_frames_count_once(self):
        rows=[{'start':0,'known':10,'distance':.1},{'start':5,'known':12,'distance':.01},{'start':13,'known':20,'distance':.2}]
        self.assertEqual(len(fractals.distinct(rows)),2)
        self.assertEqual(len(fractals.diverse_nearest(rows,6)),2)

    def test_gap_windows_are_not_indexed_as_valid(self):
        d=fractals.build_dataset('futures','BTCUSDT','1h',24)
        with db() as c:c.execute('UPDATE bars SET t=t+1 WHERE t=?',(30*3600000,))
        with patch.object(fractals,'VERSION',fractals.VERSION+1):broken=fractals.build_dataset('futures','BTCUSDT','1h',24)
        self.assertLess(broken['indexed_windows'],d['indexed_windows'])

    def test_recent_dialogue_is_same_symbol_and_precedes_current_job(self):
        from wave_monitor.worker import recent_dialogue
        with store.db() as c:
            for i in range(1,10):
                symbol='ETHUSDT' if i==7 else 'BTCUSDT'
                c.execute('INSERT INTO jobs(id,created,symbol,kind,question) VALUES (?,?,?,?,?)',(i,i,symbol,'manual','질문'+str(i)))
                c.execute('INSERT INTO analyses(job_id,result) VALUES (?,?)',(i,json.dumps({'answer_to_user':'답'+str(i)})))
        result=recent_dialogue('BTCUSDT',9)
        self.assertEqual(len(result),6)
        self.assertEqual(result[-1]['question'],'질문8')
        self.assertNotIn('질문7',[r['question'] for r in result]);self.assertNotIn('질문9',[r['question'] for r in result])


if __name__=='__main__':unittest.main()
