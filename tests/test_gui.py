"""Integration tests: run with an actual display (or Xvfb under Linux)."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from roulette19.engine import NAMES, selections
from roulette19.storage import Store, write_csv, read_csv


@unittest.skipUnless(os.name=='nt' or os.environ.get('DISPLAY'),'Écran nécessaire : utiliser Xvfb sous Linux')
class GuiTests(unittest.TestCase):
    def setUp(self):
        from roulette19.gui import App
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name); self.store=Store(self.path/'sessions.json')
        self.app=App(self.store); self.errors=[]
        self.app.report_callback_exception=lambda *args:self.errors.append(args)
        self.addCleanup(self.cleanup_app); self.wait(lambda:self.app.analysis is not None)

    def cleanup_app(self):
        if self.app.winfo_exists(): self.app.close()
        self.assertEqual(self.errors,[])

    def wait(self,predicate,timeout=10):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.app.update()
            if predicate(): return
            time.sleep(.01)
        self.fail('Interface : délai dépassé')

    def settled(self): self.wait(lambda:self.app.analysis is not None)

    def test_entry_clicks_selection_ledger_and_undo(self):
        a=self.app; a.input.set('32'); a.add_input(); self.settled()
        self.assertEqual(self.store.current['numbers'],[32])
        self.assertEqual(tuple(self.store.current['bets'][0]['selection']),selections(())[0])
        a.strategy.set(NAMES[6]); a.render(); selected=selections((32,))[6]
        from types import SimpleNamespace
        _,x,y,_=next(c for c in a.wheel_centers if c[0]==15)
        a.click_wheel(SimpleNamespace(x=x,y=y)); self.settled()
        self.assertEqual(self.store.current['numbers'],[32,15])
        self.assertEqual(tuple(self.store.current['bets'][-1]['selection']),selected)
        n,x0,y0,x1,y1=next(b for b in a.table_boxes if b[0]==0)
        a.click_table(SimpleNamespace(x=(x0+x1)/2,y=(y0+y1)/2)); self.settled()
        self.assertEqual(self.store.current['numbers'],[32,15,0]); a.undo(); self.settled()
        self.assertEqual(len(self.store.current['bets']),2)
        a.live.set(False); a.add(36); self.settled(); self.assertEqual(len(self.store.current['bets']),2)
        self.assertEqual(len(a.tree.get_children()),8)
        self.assertEqual(Store(self.store.path).sessions,self.store.sessions)
        a.geometry('980x600'); a.update(); a.draw_wheel()
        centers=a.wheel_centers
        for i,(_,x,y,r) in enumerate(centers):
            _,xx,yy,rr=centers[(i+1)%37]
            self.assertGreater(((x-xx)**2+(y-yy)**2)**.5,(r-3)+(rr-3))

    def test_import_export_sessions_confirm_and_monte_carlo(self):
        a=self.app; p=self.path/'import.csv'; write_csv(p,[0,32,15,0,1,1,36])
        with patch('roulette19.gui.filedialog.askopenfilename',return_value=str(p)): a.import_csv()
        self.settled(); self.assertEqual(len(self.store.sessions),2); self.assertEqual(self.store.current.get('bets',[]),[])
        out=self.path/'out.csv'
        with patch('roulette19.gui.filedialog.asksaveasfilename',return_value=str(out)): a.export_csv()
        self.assertEqual(read_csv(out),[0,32,15,0,1,1,36])
        a.details(); a.update(); a.start_mc(); self.wait(lambda:not a.mc_running)
        self.assertEqual(a.mc_result['size'],7); self.assertIn('p corrigée',a.mc_status.get())
        a.window.set('20'); a.period.set('20'); a.stake.set('2,5'); a.refresh(); self.settled()
        self.assertEqual(a.analysis['results'][0].wagered,7*19*2.5)
        with patch('roulette19.gui.messagebox.askyesno',return_value=False): a.clear_session()
        self.assertEqual(len(self.store.current['numbers']),7)
        with patch('roulette19.gui.messagebox.askyesno',return_value=True): a.clear_session()
        self.settled(); self.assertEqual(self.store.current['numbers'],[])

    def test_invalid_stake_does_not_consume_input(self):
        a=self.app; a.stake.set('NaN'); a.add(3)
        self.assertEqual(self.store.current['numbers'],[])
        a.stake.set('1'); a.input.set('37')
        with patch('roulette19.gui.messagebox.showwarning'): a.add_input()
        self.assertEqual(self.store.current['numbers'],[])
