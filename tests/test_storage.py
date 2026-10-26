from pathlib import Path
import tempfile
import unittest
from roulette19.storage import Store, read_csv, write_csv


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path=Path(self.tmp.name)

    def test_csv_roundtrip(self):
        p=self.path/'numbers.csv'; nums=[0,36,1,18,1]
        write_csv(p,nums); self.assertEqual(read_csv(p),nums)
        p.write_text('numéro\n0\n32\n36\n',encoding='utf-8'); self.assertEqual(read_csv(p),[0,32,36])
        p.write_text('0\n1\n36\n',encoding='utf-8'); self.assertEqual(read_csv(p),[0,1,36])
        p.write_text('',encoding='utf-8'); self.assertEqual(read_csv(p),[])

    def test_csv_invalid_transaction(self):
        p=self.path/'bad.csv'
        for text in ('numero\n1\n37\n','numero\n-1\n','numero\n1.5\n','numero\nabc\n','numero;date\n1;today\n'):
            p.write_text(text,encoding='utf-8')
            with self.assertRaises(ValueError): read_csv(p)

    def test_sessions_atomic_and_restore(self):
        p=self.path/'nested'/'sessions.json'; store=Store(p); first=store.active
        store.current['numbers']=[0,32,15]; store.save(); store.new('Deuxième'); store.current['numbers']=[36,1]; store.save(); store.save()
        restored=Store(p)
        self.assertEqual(restored.sessions,store.sessions); self.assertEqual(restored.active,store.active)
        self.assertEqual(restored.sessions[first]['numbers'],[0,32,15]); self.assertFalse(p.with_suffix('.tmp').exists())

    def test_corruption_preserved(self):
        p=self.path/'sessions.json'; p.write_text('{broken',encoding='utf-8')
        with self.assertRaises(ValueError): Store(p)
        self.assertEqual(p.read_text(),'{broken')
