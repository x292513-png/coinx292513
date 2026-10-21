import unittest
from wave_monitor.charts import chart_rows,displayed_label
from wave_monitor.worker import validate_label_coverage
class ChartLabelTests(unittest.TestCase):
 def test_old_anchor_is_not_clipped(self):
  rows=[{'t':i} for i in range(500)]
  visible=chart_rows(rows,[{'t':40},{'t':490}])
  self.assertEqual(visible[0]['t'],32)
  self.assertEqual(visible[-1]['t'],499)
  self.assertEqual(len(chart_rows(rows,[])),160)
 def test_developing_labels_are_distinct(self):
  self.assertEqual(displayed_label({'label':'C','confirmed':False}),'C?')
  self.assertEqual(displayed_label({'label':'C?','confirmed':False}),'C?')
  self.assertEqual(displayed_label({'label':'2','confirmed':True}),'2')
 def test_each_primary_frame_requires_grounded_labels(self):
  r={'frames':[{'tf':tf,'status':'developing'} for tf in ['1d','4h','1h','15m']], 'wave_labels':[{'tf':tf,'t':i} for tf in ['1d','4h','1h','15m'] for i in [1,2]]}
  validate_label_coverage(r)
  r['wave_labels'].pop()
  with self.assertRaisesRegex(ValueError,'15m'):validate_label_coverage(r)
  r['frames'][-1]['status']='unclear'
  validate_label_coverage(r)
