"""Local atomic session persistence and strict, transactional CSV import."""
import csv
import io
import json
import os
from pathlib import Path
from uuid import uuid4
from .engine import validate, NAMES
import math


def data_directory():
    if os.environ.get('ROULETTE19_DATA_DIR'): return Path(os.environ['ROULETTE19_DATA_DIR'])
    return Path(os.environ.get('LOCALAPPDATA',Path.home()/'.local'/'share'))/'RouletteAnalyzer19Pro'


def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as stream:
        text=stream.read()
    try: dialect=csv.Sniffer().sniff(text[:4096],delimiters=',;\t')
    except csv.Error: dialect=csv.excel
    rows=csv.reader(io.StringIO(text),dialect)
    result=[]
    first=True
    for line,row in enumerate(rows,1):
        if not row or not any(c.strip() for c in row): continue
        if len(row)!=1: raise ValueError(f'Ligne {line} : une seule colonne « numero » est attendue.')
        value=row[0].strip()
        if first and value.lower() in ('numero','numéro','number'): first=False; continue
        first=False
        try: n=int(value)
        except ValueError: raise ValueError(f'Ligne {line} : entier attendu, reçu {value!r}.') from None
        if str(n)!=value and value not in (f'{n:02d}',f'+{n}'): raise ValueError(f'Ligne {line} : entier attendu.')
        validate([n]); result.append(n)
    return result


def write_csv(path,history):
    history=validate(history)
    with open(path,'w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream); writer.writerow(['numero']); writer.writerows((n,) for n in history)


class Store:
    def __init__(self,path=None):
        self.path=Path(path) if path else data_directory()/'sessions.json'
        self.sessions={}; self.active=None
        if self.path.exists():
            doc=json.loads(self.path.read_text(encoding='utf-8'))
            if doc.get('version')!=1: raise ValueError('Format de sauvegarde non pris en charge.')
            for key,session in doc['sessions'].items():
                validate(session['numbers'])
                if not isinstance(session['name'],str): raise ValueError('Nom de session invalide.')
                previous=0
                for bet in session.get('bets',[]):
                    chosen=validate(bet['selection'])
                    if len(chosen)!=19 or len(set(chosen))!=19: raise ValueError('Sélection enregistrée invalide.')
                    if type(bet['spin']) is not int or not previous<bet['spin']<=len(session['numbers']): raise ValueError('Tour enregistré invalide.')
                    if bet['number']!=session['numbers'][bet['spin']-1]: raise ValueError('Résultat enregistré incohérent.')
                    if not isinstance(bet['stake'],(int,float)) or not math.isfinite(bet['stake']) or not 0<bet['stake']<=1_000_000: raise ValueError('Mise enregistrée invalide.')
                    if bet['strategy'] not in NAMES or bet['window'] not in (20,50,100,200): raise ValueError('Paramètres enregistrés invalides.')
                    previous=bet['spin']
            self.sessions=doc['sessions']; self.active=doc['active']
            if self.active not in self.sessions: raise ValueError('Session active absente.')
        else: self.new('Session 1')

    @property
    def current(self): return self.sessions[self.active]

    def new(self,name):
        key=uuid4().hex
        self.sessions[key]={'name':name.strip() or 'Nouvelle session','numbers':[],'bets':[]}
        self.active=key
        return key

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        with tmp.open('w',encoding='utf-8') as stream:
            json.dump({'version':1,'active':self.active,'sessions':self.sessions},stream,ensure_ascii=False)
            stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp,self.path)
