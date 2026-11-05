import unittest
from wave_monitor.channels import channel_candidates, line
from wave_monitor.entry_context import display, measured_levels


class ChannelTests(unittest.TestCase):
    def points(self):
        return [dict(t=t,price=p,kind=k,confirmed=True,confirmed_at=t+1)
                for t,p,k in [(10,100,'L'),(20,130,'H'),(30,110,'L')]]

    def rows(self, close=115):
        return [dict(t=39,close_t=40,l=close-2,h=close+2,c=close)]

    def test_parallel_geometry_and_break(self):
        m=channel_candidates('15m',self.points(),self.rows())[0]
        self.assertEqual((m['lower'],m['mid'],m['upper']),(115,127.5,140))
        self.assertEqual(m['status'],'inside')
        broken=channel_candidates('15m',self.points(),self.rows(112))[0]
        self.assertEqual(broken['status'],'below')
        self.assertEqual(broken['outside_closes'],1)
        self.assertEqual(line(*m['baseline'],50),120)

    def test_future_confirmation_cannot_create_channel(self):
        points=self.points();points[-1]['confirmed_at']=41
        self.assertEqual(channel_candidates('15m',points,self.rows()),[])
        points[-1]['confirmed_at']=31;points[-1]['confirmed']=False
        self.assertEqual(channel_candidates('15m',points,self.rows()),[])

    def test_descending_upper_anchored_channel(self):
        points=[dict(t=t,price=p,kind=k,confirmed=True) for t,p,k in [(10,130,'H'),(20,100,'L'),(30,120,'H')]]
        m=channel_candidates('1h',points,self.rows(120))[0]
        self.assertEqual((m['lower'],m['upper'],m['status']),(90,115,'above'))

    def test_display_channel_and_extended_ratios(self):
        m=channel_candidates('15m',self.points(),self.rows(112))[0]
        logic=dict(shared_path='test',supporting_scenarios=[],confluence='test',trigger='test',failure_case='test',measured_evidence=[m])
        self.assertIn('115.00',''.join(display({'entry_logic':logic})))
        levels=measured_levels({'frames':{'15m':{'pivots':self.points()}}},{'15m':self.rows()})['levels']
        f=next(v for v in levels if v['id']=='15m:fib:10:20:1.272')
        self.assertAlmostEqual(f['price'],91.84)
        self.assertEqual(f['kind'],'retracement_extension')
