import random
import threading
import unittest
from roulette19.engine import *


class EngineTests(unittest.TestCase):
    def test_wheel(self):
        self.assertEqual(set(WHEEL),set(range(37)))
        self.assertEqual(WHEEL,(0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26))
        self.assertEqual(len(RED),18)

    def test_selections_always_19(self):
        rng=random.Random(42)
        for size in (0,1,2,20,50,200,1000):
            for history in (tuple([0]*size),tuple(rng.randrange(37) for _ in range(size))):
                for selection in selections(history):
                    self.assertEqual(len(selection),19); self.assertEqual(len(set(selection)),19)
                    self.assertTrue(set(selection)<=set(WHEEL))
                self.assertEqual(selections(history),selections(history))

    def test_ties_empty_and_rules(self):
        empty=selections(())
        self.assertTrue(all(s==WHEEL[:19] for s in empty))
        self.assertEqual(selections(WHEEL)[1],WHEEL[:19])
        self.assertEqual(selections(WHEEL)[2],WHEEL[:19])
        h=(5,)*20+(10,)*10+(25,)*5
        self.assertEqual(selections(h)[1][:3],(5,10,25))
        self.assertTrue({5,10,25}.isdisjoint(selections(h)[2]))
        self.assertIn(25,selections(h)[6])
        self.assertEqual(selections((3,1,3,4,1,3))[5][0],3)
        self.assertEqual(set(selections((26,))[6]),{WHEEL[(36+j)%37] for j in range(-9,10)})

    def test_money_roi_drawdown_streaks(self):
        r=summarize([False,False,True,True,False],2)
        self.assertEqual(r.balance,-46); self.assertEqual(r.wagered,190)
        self.assertAlmostEqual(r.roi,-46/190*100)
        self.assertEqual(r.drawdown,76); self.assertEqual(r.longest_loss,2); self.assertEqual(r.longest_hit,2)
        self.assertEqual(r.curve,(0,-38,-76,-42,-8,-46))
        self.assertEqual(summarize([True]).balance,17); self.assertEqual(summarize([False]).balance,-19)
        self.assertEqual(summarize([]).roi,0)
        self.assertAlmostEqual((19/37*17+18/37*(-19))/19,-1/37)
        for stake in (0,-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError): summarize([True],stake)

    def test_no_future_leak(self):
        rng=random.Random(72); nums=tuple(rng.randrange(37) for _ in range(80))
        e=Evaluator(20).sync(nums)
        for i,n in enumerate(nums):
            self.assertEqual(e.recorded[i][:7],selections(nums[max(0,i-20):i]))
            for j in range(8): self.assertEqual(e.outcomes[j][i],n in e.recorded[i][j])
        prefix=Evaluator(20).sync(nums[:45])
        self.assertEqual(e.recorded[:45],prefix.recorded)
        changed=Evaluator(20).sync(nums[:45]+(36,)*35)
        self.assertEqual(e.recorded[:46],changed.recorded[:46])

    def test_incremental_undo_reset_and_period(self):
        nums=tuple(range(37))*2
        e=Evaluator(20).sync(nums[:10]); e.sync(nums)
        fresh=Evaluator(20).sync(nums)
        self.assertEqual(e.results(),fresh.results())
        e.sync(nums[:-1]); self.assertEqual(e.results(),Evaluator(20).sync(nums[:-1]).results())
        e.sync((2,3,4)); self.assertEqual(e.results(),Evaluator(20).sync((2,3,4)).results())
        self.assertEqual(fresh.results(20)[0].hits+fresh.results(20)[0].misses,20)

    def test_scanner(self):
        sc=scanner((1,1,2,3,1,2,4,1))
        self.assertEqual(sc['immediate'],1); self.assertEqual(sc['short5'],4); self.assertEqual(sc['short10'],4)
        self.assertEqual(sc['intervals'],{1:[1,3,3],2:[3]})
        self.assertEqual(sc['max_gap'],3); self.assertEqual(sc['distinct37'],4)
        self.assertEqual(sc['last_repeat'],(1,3,8)); self.assertEqual(sc['unique_run'],4)
        self.assertEqual(sc['current_unique'],3)
        self.assertEqual(scanner(())['last_repeat'],None)

    def test_sectors(self):
        sc=sectors(WHEEL)
        self.assertEqual(len(sc),37)
        self.assertTrue(all(s['count']==19 and s['frequency']==19/37 and s['deviation']==0 for s in sc))
        history=SECTORS[4]*3
        self.assertEqual(selections(history)[4],SECTORS[4])
        self.assertEqual(max(x['count'] for x in sectors(history)),57)

    def test_monte_carlo_reproducibility_and_maximum(self):
        h=(0,32,15,19,4,21)
        a=monte_carlo(h,runs=500,seed=9); b=monte_carlo(h,runs=500,seed=9)
        self.assertEqual(a,b); self.assertEqual(a['observed'],6)
        rng=random.Random(9)
        scores=[]
        # Independent naive maximum over all 37 sectors.
        for _ in range(500):
            sample=[rng.randrange(37) for _ in h]
            scores.append(max(sum(n in sector for n in sample) for sector in SECTORS))
        self.assertEqual(a['mean'],sum(scores)/500)
        self.assertEqual(a['p'],(1+sum(x>=6 for x in scores))/501)
        c=threading.Event(); c.set(); self.assertIsNone(monte_carlo(h,cancel=c))
        with self.assertRaises(ValueError): monte_carlo(())
        for kind in METRICS[1:]:
            result=monte_carlo(h,kind,seed=8)
            self.assertTrue(0<result['p']<=1)
            self.assertEqual(result,monte_carlo(h,kind,seed=8))

    def test_validation(self):
        for values in ((37,),(-1,),('2',),(True,)):
            with self.assertRaises(ValueError): Evaluator().sync(values)
