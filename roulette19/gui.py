"""Tk dashboard; all widgets are accessed on the main thread only."""
import logging
import os
import tkinter.font as tkfont
import math
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from collections import Counter
from .engine import WHEEL, RED, NAMES, METRICS, Evaluator, selections, sectors, scanner, monte_carlo, summarize
from .storage import Store, read_csv, write_csv, data_directory

FONT='Segoe UI' if os.name=='nt' else 'Helvetica'
BG='#10151d'; PANEL='#1b2430'; TEXT='#ecf1f8'; MUTED='#a2b1c4'; CYAN='#27d7e8'; GREEN='#39d49a'; ORANGE='#ffbb62'


class Tooltip:
    def __init__(self,widget,text):
        self.window=None; self.widget=widget; self.text=text; self.timer=None
        widget.bind('<Enter>',self.enter,add='+'); widget.bind('<Leave>',self.leave,add='+')
    def enter(self,event): self.timer=self.widget.after(600,self.show)
    def show(self):
        self.window=tk.Toplevel(self.widget); self.window.wm_overrideredirect(True)
        self.window.geometry(f'+{self.widget.winfo_rootx()+10}+{self.widget.winfo_rooty()+25}')
        tk.Label(self.window,text=self.text,bg=PANEL,fg=TEXT,padx=10,pady=6,wraplength=350).pack()
    def leave(self,event):
        if self.timer: self.widget.after_cancel(self.timer); self.timer=None
        if self.window: self.window.destroy(); self.window=None


class App(tk.Tk):
    def __init__(self,store=None):
        super().__init__()
        self.title('ROULETTE ANALYZER 19 PRO — ÉDITION PROFESSIONNELLE')
        self.geometry(f'{min(1560,self.winfo_screenwidth()-40)}x{min(1020,self.winfo_screenheight()-60)}'); self.minsize(980,600); self.configure(bg=BG)
        self.store=store or Store(); self.version=0; self.analysis=None; self.mc_cancel=threading.Event(); self.mc_running=False
        self.jobs=queue.Queue(maxsize=1); self.messages=queue.Queue(); self.closing=threading.Event()
        self.window=tk.StringVar(value='50'); self.period=tk.StringVar(value='200'); self.stake=tk.StringVar(value='1')
        self.strategy=tk.StringVar(value=NAMES[0]); self.sort=tk.StringVar(value='ROI'); self.live=tk.BooleanVar(value=True)
        self.session=tk.StringVar(); self.status=tk.StringVar(value='Chargement…'); self.mc_status=tk.StringVar(value='Aucune comparaison exécutée.')
        self.selected=set(); self.numbers=[]; self.last=None
        self._theme(); self._build(); self._sessions()
        threading.Thread(target=self._analysis_worker,daemon=True).start()
        self.protocol('WM_DELETE_WINDOW',self.close); self.poll_id=self.after(50,self.poll); self.refresh()

    def report_callback_exception(self,exc,value,tb):
        logging.error('Erreur interface',exc_info=(exc,value,tb)); messagebox.showerror('Erreur',str(value),parent=self)

    def _theme(self):
        for name in ('TkDefaultFont','TkTextFont','TkMenuFont','TkHeadingFont','TkCaptionFont','TkTooltipFont'):
            tkfont.nametofont(name).configure(family=FONT,size=10)
        style=ttk.Style(self); style.theme_use('clam')
        style.configure('.',background=BG,foreground=TEXT,font=(FONT,10))
        style.configure('TFrame',background=BG); style.configure('Panel.TFrame',background=PANEL)
        style.configure('TLabel',background=BG,foreground=TEXT)
        style.configure('Title.TLabel',font=(FONT,20,'bold'),foreground=CYAN)
        style.configure('TButton',background=PANEL,foreground=TEXT,padding=(9,6))
        style.map('TButton',background=[('active','#34475c')])
        style.configure('TCombobox',fieldbackground=PANEL,background=PANEL,foreground=TEXT,arrowcolor=CYAN)
        style.map('TCombobox',fieldbackground=[('readonly',PANEL)],foreground=[('readonly',TEXT)])
        style.configure('TEntry',fieldbackground=PANEL,foreground=TEXT)
        style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=26)
        style.configure('Treeview.Heading',background='#293747',foreground=TEXT)
        style.map('Treeview',background=[('selected','#20576b')])
        self.option_add('*TCombobox*Listbox.background',PANEL); self.option_add('*TCombobox*Listbox.foreground',TEXT)

    def _combo(self,parent,var,values,width=10,callback=None):
        c=ttk.Combobox(parent,textvariable=var,values=values,state='readonly',width=width)
        c.pack(side='left',padx=5); c.bind('<<ComboboxSelected>>',lambda e:(callback or self.refresh)()); return c

    def _build(self):
        viewport=tk.Canvas(self,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(self,orient='vertical',command=viewport.yview)
        scrollbar.pack(side='right',fill='y'); viewport.pack(fill='both',expand=True)
        viewport.configure(yscrollcommand=scrollbar.set)
        body=ttk.Frame(viewport)
        item=viewport.create_window((0,0),window=body,anchor='nw')
        def resize(event=None):
            viewport.itemconfigure(item,width=viewport.winfo_width(),height=max(viewport.winfo_height(),body.winfo_reqheight()))
            viewport.configure(scrollregion=viewport.bbox('all'))
        viewport.bind('<Configure>',resize); body.bind('<Configure>',resize)
        self.bind('<MouseWheel>',lambda event:viewport.yview_scroll(-int(event.delta/120),'units'))
        self.bind('<Button-4>',lambda event:viewport.yview_scroll(-1,'units'))
        self.bind('<Button-5>',lambda event:viewport.yview_scroll(1,'units'))
        head=ttk.Frame(body,padding=(14,10)); head.pack(fill='x')
        ttk.Label(head,text='ROULETTE / 19 PRO',style='Title.TLabel').pack(side='left')
        ttk.Label(head,text='  OBSERVATION • STATISTIQUES • SIMULATION VIRTUELLE',foreground=MUTED).pack(side='left')
        bar=ttk.Frame(body,padding=(14,2)); bar.pack(fill='x')
        ttk.Label(bar,text='Session').pack(side='left'); self.session_box=self._combo(bar,self.session,[],22,self.switch_session)
        for label,command in [('Nouvelle',self.new_session),('Renommer',self.rename_session),('Effacer',self.clear_session),('Importer CSV',self.import_csv),('Exporter CSV',self.export_csv)]:
            ttk.Button(bar,text=label,command=command).pack(side='left',padx=3)
        params=ttk.Frame(body,padding=(14,6)); params.pack(fill='x')
        ttk.Label(params,text='Fenêtre de sélection').pack(side='left'); c=self._combo(params,self.window,('20','50','100','200'),5)
        Tooltip(c,'La sélection utilise uniquement les tirages précédents, dans cette fenêtre.')
        ttk.Label(params,text='Période évaluée').pack(side='left'); c=self._combo(params,self.period,('20','50','100','200','Tout'),6)
        Tooltip(c,'Résultats des derniers tours. Le contexte antérieur reste utilisé pour chaque sélection.')
        ttk.Label(params,text='Mise €/numéro').pack(side='left')
        e=ttk.Entry(params,textvariable=self.stake,width=7); e.pack(side='left',padx=5); e.bind('<Return>',lambda ev:self.refresh()); e.bind('<FocusOut>',lambda ev:self.refresh())
        Tooltip(e,'Mise constante appliquée rétrospectivement au comparateur. 19 mises par tour, gain net +17 ou perte −19 unités.')
        ttk.Checkbutton(params,text='Enregistrer les mises virtuelles',variable=self.live,command=self.render).pack(side='left',padx=8)
        main=ttk.Frame(body,padding=(12,4)); main.pack(fill='both',expand=True)
        main.columnconfigure(0,weight=3,uniform='panels'); main.columnconfigure(1,weight=4,uniform='panels'); main.columnconfigure(2,weight=3,uniform='panels'); main.rowconfigure(1,weight=1,minsize=360)
        for i,text in enumerate(('01 / TAPIS EUROPÉEN','02 / CYLINDRE & CONCENTRATION','03 / SCANNER EN DIRECT')):
            ttk.Label(main,text=text,foreground=CYAN,font=(FONT,11,'bold')).grid(row=0,column=i,sticky='w',padx=5,pady=8)
        left=ttk.Frame(main); left.grid(row=1,column=0,sticky='nsew',padx=5); left.rowconfigure(0,weight=1); left.columnconfigure(0,weight=1)
        self.table=tk.Canvas(left,bg=PANEL,highlightthickness=0,height=270); self.table.grid(row=0,column=0,sticky='nsew'); self.table.bind('<Configure>',lambda e:self.draw_table())
        self.table.bind('<Button-1>',self.click_table)
        entrybar=ttk.Frame(left); entrybar.grid(row=1,column=0,sticky='ew',pady=8)
        self.input=tk.StringVar(); entry=ttk.Entry(entrybar,textvariable=self.input,width=5,font=(FONT,14)); entry.pack(side='left'); entry.bind('<Return>',lambda e:self.add_input())
        ttk.Button(entrybar,text='Ajouter',command=self.add_input).pack(side='left',padx=5)
        ttk.Button(entrybar,text='Annuler',command=self.undo).pack(side='left')
        ttk.Label(left,text='50 derniers tirages • plus récent en premier',foreground=MUTED).grid(row=2,column=0,sticky='w')
        self.history_label=ttk.Label(left,text='',wraplength=340,font=(FONT,10)); self.history_label.grid(row=3,column=0,sticky='ew',pady=5)
        self.wheel=tk.Canvas(main,bg=PANEL,highlightthickness=0,height=310); self.wheel.grid(row=1,column=1,sticky='nsew',padx=5)
        self.wheel.bind('<Configure>',lambda e:self.draw_wheel()); self.wheel.bind('<Button-1>',self.click_wheel)
        right=ttk.Frame(main); right.grid(row=1,column=2,sticky='nsew',padx=5)
        self._combo(right,self.strategy,NAMES,27,self.render).pack(side='top',fill='x',pady=(0,8))
        self.scan_text=tk.Text(right,bg=PANEL,fg=TEXT,relief='flat',wrap='word',font=(FONT,10),height=17,width=30,padx=10,pady=8,state='disabled')
        self.scan_text.pack(fill='both',expand=True)
        ttk.Button(right,text='Analyses détaillées & Monte-Carlo',command=self.details).pack(fill='x',pady=(6,0))
        compare=ttk.Frame(body,padding=(16,2)); compare.pack(fill='x')
        ttk.Label(compare,text='COMPARATEUR HISTORIQUE',foreground=CYAN,font=(FONT,11,'bold')).pack(side='left')
        ttk.Label(compare,text='   Classer par').pack(side='left'); self._combo(compare,self.sort,('ROI','Touches','Drawdown'),10,self.render)
        self.count_label=ttk.Label(compare,text='',foreground=MUTED); self.count_label.pack(side='right')
        treebox=ttk.Frame(body,padding=(16,4)); treebox.pack(fill='x')
        columns=('name','hit','miss','rate','balance','roi','dd','loss','win')
        self.tree=ttk.Treeview(treebox,columns=columns,show='headings',height=8)
        for col,title,width in zip(columns,('Stratégie','Touches','Ratés','Réussite','Solde €','ROI','Drawdown €','Série −','Série +'),(250,65,65,80,90,75,95,65,65)):
            self.tree.heading(col,text=title); self.tree.column(col,width=width,minwidth=50,anchor='w' if col=='name' else 'e')
        self.tree.pack(fill='x'); self.tree.bind('<<TreeviewSelect>>',self.select_row)
        self.curve=tk.Canvas(body,height=90,bg=PANEL,highlightthickness=0); self.curve.pack(fill='x',padx=16,pady=3); self.curve.bind('<Configure>',lambda e:self.draw_curve())
        ttk.Label(body,text='Sélection statistique — aucune garantie sur le prochain tirage.',foreground=ORANGE).pack()
        ttk.Label(body,text='Roulette équitable : touche 19/37 = 51,35 % • espérance −2,70 % des mises • aucune mise réelle',foreground=MUTED).pack()
        ttk.Label(body,textvariable=self.status,anchor='w',foreground=MUTED,padding=(16,4)).pack(fill='x')

    def _sessions(self):
        self.session_keys=list(self.store.sessions)
        labels=[f'{i+1}. {self.store.sessions[k]["name"]}' for i,k in enumerate(self.session_keys)]
        self.session_box['values']=labels; self.session.set(labels[self.session_keys.index(self.store.active)])

    def save(self):
        try: self.store.save(); return True
        except Exception as exc:
            logging.exception('Sauvegarde impossible'); messagebox.showerror('Sauvegarde impossible',f'{exc}\nLes données restent en mémoire. Exportez-les en CSV.',parent=self); return False

    def switch_session(self):
        self.store.active=self.session_keys[self.session_box.current()]; self.refresh()

    def new_session(self):
        name=simpledialog.askstring('Nouvelle session','Nom de la session :',parent=self)
        if name is not None: self.store.new(name); self._sessions(); self.refresh()

    def rename_session(self):
        name=simpledialog.askstring('Renommer','Nom :',initialvalue=self.store.current['name'],parent=self)
        if name and name.strip(): self.store.current['name']=name.strip(); self._sessions(); self.save()

    def clear_session(self):
        if messagebox.askyesno('Effacer la session','Effacer définitivement tous les tirages de cette session ?',parent=self):
            self.store.current['numbers'].clear(); self.store.current['bets']=[]; self.refresh()

    def import_csv(self):
        path=filedialog.askopenfilename(filetypes=[('CSV','*.csv'),('Tous','*')],parent=self)
        if not path: return
        try: values=read_csv(path)
        except Exception as exc: messagebox.showerror('Import refusé',str(exc),parent=self); return
        if not values: messagebox.showinfo('CSV vide','Aucun tirage à importer.',parent=self); return
        # A new session avoids overwriting existing observations.
        from pathlib import Path
        self.store.new(Path(path).stem); self.store.current['numbers']=values; self._sessions(); self.refresh()

    def export_csv(self):
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')],parent=self)
        if path:
            try: write_csv(path,self.store.current['numbers'])
            except Exception as exc: messagebox.showerror('Export impossible',str(exc),parent=self)

    def add_input(self):
        try: n=int(self.input.get())
        except ValueError: messagebox.showwarning('Saisie','Entrez un numéro de 0 à 36.',parent=self); return
        if not 0<=n<=36: messagebox.showwarning('Saisie','Entrez un numéro de 0 à 36.',parent=self); return
        self.input.set(''); self.add(n)

    def add(self,n):
        try:
            stake=float(self.stake.get().replace(',','.'))
            if not math.isfinite(stake) or not 0<stake<=1_000_000: raise ValueError()
        except ValueError:
            self.status.set('Mise invalide : tirage non enregistré.'); return
        history=self.store.current['numbers']
        if self.live.get():
            # Snapshot the exact pre-result selection; never reconstructed from a future window.
            window=int(self.window.get()); name=self.strategy.get()
            chosen=selections(tuple(history[-window:]))[NAMES.index(name)]
            self.store.current.setdefault('bets',[]).append({'spin':len(history)+1,'selection':list(chosen),
                'number':n,'stake':stake,'window':window,'strategy':name})
        history.append(n); self.refresh()
    def undo(self):
        if self.store.current['numbers']:
            self.store.current['numbers'].pop()
            self.store.current['bets']=[b for b in self.store.current.get('bets',[]) if b['spin']<=len(self.store.current['numbers'])]
            self.refresh()

    def refresh(self):
        try:
            stake=float(self.stake.get().replace(',','.'))
            if not math.isfinite(stake) or not 0<stake<=1_000_000: raise ValueError()
        except ValueError:
            self.status.set('Mise invalide : entrez une valeur entre 0 et 1 000 000 €, puis Entrée.'); return
        self.version+=1
        numbers=tuple(self.store.current['numbers']); window=int(self.window.get()); period=0 if self.period.get()=='Tout' else int(self.period.get())
        saved=self.save(); self.save_ok=saved
        self.numbers=numbers; self.last=numbers[-1] if numbers else None
        self.selected=set(selections(numbers[-window:])[NAMES.index(self.strategy.get())])
        self.history_label.configure(text='  '.join(map(str,reversed(numbers[-50:]))))
        self.count_label.configure(text=f'{len(numbers):,} tirages • évaluation {min(period or len(numbers),len(numbers))}')
        self.draw_table(); self.draw_wheel(); self.analysis=None
        self.scan_text.configure(state='normal'); self.scan_text.delete('1.0','end'); self.scan_text.insert('end','Actualisation des statistiques…'); self.scan_text.configure(state='disabled')
        self.tree.delete(*self.tree.get_children()); self.curve.delete('all')
        self.status.set('Calcul en arrière-plan…' if saved else 'Calcul… • ÉCHEC DE SAUVEGARDE : export CSV conseillé')
        job=(self.version,numbers,window,period,stake)
        try: self.jobs.get_nowait()
        except queue.Empty: pass
        self.jobs.put_nowait(job)

    def _analysis_worker(self):
        evaluator=None
        while not self.closing.is_set():
            try: version,nums,window,period,stake=self.jobs.get(timeout=.2)
            except queue.Empty: continue
            try:
                if evaluator is None or evaluator.window!=window: evaluator=Evaluator(window)
                evaluator.sync(nums)
                result={'numbers':nums,'selection':selections(nums[-window:]),'results':evaluator.results(period,stake),
                        'scanner':scanner(nums),'sectors':sectors(nums[-window:]),
                        'scales':{n:sectors(nums[-n:]) for n in (20,50,100,200)}}
                self.messages.put(('analysis',version,result))
            except Exception as exc:
                logging.exception('Analyse'); self.messages.put(('error',version,str(exc)))

    def poll(self):
        try:
            while True:
                kind,version,data=self.messages.get_nowait()
                if kind=='analysis' and version==self.version:
                    self.analysis=data; self.render(); self.status.set(f'Prêt • sauvegarde automatique : {self.store.path}' if self.save_ok else 'ÉCHEC DE SAUVEGARDE • exportez vos tirages en CSV')
                elif kind=='error' and version==self.version: self.status.set('Erreur : '+data)
                elif kind=='mc_progress': self.mc_status.set(f'Simulation : {data} tours Monte-Carlo terminés…')
                elif kind=='mc_done':
                    self.mc_running=False
                    if data is None: self.mc_status.set('Simulation annulée. Aucun résultat partiel interprété.')
                    else:
                        self.mc_result=data
                        self.mc_status.set(f'{data["kind"]}\nÉchantillon figé : {data["size"]} tirages • graine {data["seed"]}\nObservé : {data["observed"]} • moyenne hasard : {data["mean"]:.2f}\nPercentile médian des égalités : {data["percentile"]:.1f} %\nFréquence au moins aussi extrême : {data["extreme"]}/{data["runs"]}\np corrigée (+1) : {data["p"]:.4f} • queue {data["tail"]}\nUne rareté descriptive ne prouve ni biais ni prédiction.\nPlusieurs mesures explorées multiplient les chances de faux signal.\nValider sur une nouvelle série indépendante ; aucune correction globale multi-mesures.')
                elif kind=='mc_error': self.mc_running=False; self.mc_status.set('Erreur : '+data)
        except queue.Empty: pass
        if not self.closing.is_set(): self.poll_id=self.after(50,self.poll)

    def render(self):
        if not self.analysis: return
        a=self.analysis; idx=NAMES.index(self.strategy.get()); self.selected=set(a['selection'][idx]); r=a['results'][idx]; sc=a['scanner']; best=max(a['sectors'],key=lambda s:s['count'])
        repeat=sc['last_repeat']; rep=f'{repeat[0]} après {repeat[1]} tour(s), au tour {repeat[2]}' if repeat else 'Aucune'
        bets=self.store.current.get('bets',[])
        live_balance=sum((17 if b['number'] in b['selection'] else -19)*b['stake'] for b in bets)
        last_record=bets[-1] if bets and bets[-1]['spin']==len(self.numbers) else None
        last_bet=f"{(17 if last_record['number'] in last_record['selection'] else -19)*last_record['stake']:+.2f} €" if last_record else 'non enregistré'
        text=f'SÉLECTION DU PROCHAIN TOUR\n'+ ' · '.join(map(str,a['selection'][idx]))
        text+=f'\n\nTouches {r.hits} / Ratés {r.misses} • {100*r.hits/(r.hits+r.misses) if r.hits+r.misses else 0:.1f} %\nSolde {r.balance:+.2f} € • ROI {r.roi:+.2f} %\nEngagé {r.wagered:.2f} € • {r.hits+r.misses} tours\nDernier tour enregistré : {last_bet}\nJournal virtuel des saisies : {len(bets)} tours / {live_balance:+.2f} €\n\nRÉPÉTITIONS — SESSION ENTIÈRE\nImmédiates : {sc["immediate"]} • ≤ 5 : {sc["short5"]} • ≤ 10 : {sc["short10"]}\nDernière : {rep}\nDiversité / 37 derniers : {sc["distinct37"]}\nPlus grand intervalle : {sc["max_gap"]}\nSérie sans répétition : {sc["current_unique"]} (max {sc["unique_run"]})\n\nSECTEUR LE PLUS CONCENTRÉ\nDépart {best["start"]} • {best["count"]}/{min(len(self.numbers),int(self.window.get()))} • {best["frequency"]:.1%}\nÉcart théorique : {best["deviation"]*100:+.1f} points' if self.numbers else '\n\nAucun tirage : sélection initiale déterministe.\nCliquez sur le tapis ou entrez un numéro.'
        self.scan_text.configure(state='normal'); self.scan_text.delete('1.0','end'); self.scan_text.insert('end',text.replace('\n\n','\n')); self.scan_text.configure(state='disabled')
        self.tree.delete(*self.tree.get_children()); results=a['results']
        indices=sorted(range(8),key=lambda i:results[i].drawdown if self.sort.get()=='Drawdown' else -results[i].hits if self.sort.get()=='Touches' else -results[i].roi)
        for i in indices:
            x=results[i]; tours=x.hits+x.misses
            self.tree.insert('', 'end',iid=str(i),values=((NAMES+('Référence aléatoire (graine fixe)',))[i],x.hits,x.misses,f'{100*x.hits/tours:.1f} %' if tours else '—',f'{x.balance:+.2f}',f'{x.roi:+.2f} %',f'{x.drawdown:.2f}',x.longest_loss,x.longest_hit))
        self.draw_table(); self.draw_wheel(); self.draw_curve()

    def select_row(self,event):
        rows=self.tree.selection()
        if rows and int(rows[0])<7 and self.strategy.get()!=NAMES[int(rows[0])]:
            self.strategy.set(NAMES[int(rows[0])]); self.render()

    def draw_table(self):
        c=self.table; c.delete('all'); w=max(c.winfo_width(),300); h=max(c.winfo_height(),100); cw=w/13; ch=h/3
        self.table_boxes=[]
        for n in range(37):
            if n==0: x0,y0,x1,y1=2,2,cw-2,h-2
            else:
                col=(n-1)//3+1; row=2-(n-1)%3
                x0,y0,x1,y1=col*cw+2,row*ch+2,(col+1)*cw-2,(row+1)*ch-2
            color='#16694b' if n==0 else '#8f273b' if n in RED else '#0b1017'
            c.create_rectangle(x0,y0,x1,y1,fill=color,outline=CYAN if n in self.selected else '#344050',width=3 if n in self.selected else 1)
            c.create_text((x0+x1)/2,(y0+y1)/2,text=str(n),fill=TEXT,font=(FONT,10,'bold'))
            if n==self.last: c.create_oval(x0+3,y0+3,x0+9,y0+9,fill=ORANGE,outline='')
            self.table_boxes.append((n,x0,y0,x1,y1))

    def click_table(self,event):
        for n,x0,y0,x1,y1 in self.table_boxes:
            if x0<=event.x<=x1 and y0<=event.y<=y1: self.add(n); return

    def draw_wheel(self):
        c=self.wheel; c.delete('all'); w=c.winfo_width(); h=c.winfo_height(); cx=w/2; cy=h/2
        r=max(40,min(w,h)/2-28); counts=Counter(self.numbers[-20:]); self.wheel_centers=[]
        best=max(self.analysis['sectors'],key=lambda s:s['count'])['numbers'] if self.analysis and self.numbers else ()
        for i,n in enumerate(WHEEL):
            angle=-math.pi/2+2*math.pi*i/37; x=cx+r*math.cos(angle); y=cy+r*math.sin(angle)
            # Inner colored ring indicates the maximum-frequency sector.
            ix=cx+(r-29)*math.cos(angle); iy=cy+(r-29)*math.sin(angle)
            c.create_oval(ix-4,iy-4,ix+4,iy+4,fill=ORANGE if n in best else '#344050',outline='')
            rad=max(9,min(17,r*.073))
            c.create_oval(x-rad,y-rad,x+rad,y+rad,fill='#16694b' if n==0 else '#8f273b' if n in RED else '#0b1017',outline=CYAN if n in self.selected else '#526174',width=2)
            c.create_text(x,y,text=str(n),fill=TEXT,font=(FONT,max(8,int(rad*.72)),'bold'))
            if counts[n]>1: c.create_text(cx+(r-48)*math.cos(angle),cy+(r-48)*math.sin(angle),text=f'×{counts[n]}',fill=CYAN,font=(FONT,8))
            self.wheel_centers.append((n,x,y,rad+3))
        c.create_text(cx,cy-23,text='DERNIER NUMÉRO',fill=MUTED,font=(FONT,10))
        c.create_text(cx,cy+13,text='—' if self.last is None else str(self.last),fill=ORANGE,font=(FONT,34,'bold'))
        c.create_text(cx,cy+55,text='Cyan : sélection\nOrange : secteur maximal\n× : répétitions sur 20 tours',fill=MUTED,font=(FONT,9),justify='center')

    def click_wheel(self,event):
        for n,x,y,rad in self.wheel_centers:
            if (event.x-x)**2+(event.y-y)**2<=rad**2: self.add(n); return

    def draw_curve(self):
        c=self.curve; c.delete('all')
        if not self.analysis: return
        r=self.analysis['results'][NAMES.index(self.strategy.get())]; values=r.curve
        w=max(c.winfo_width(),100); h=max(c.winfo_height(),70); low=min(values); high=max(values); span=max(high-low,1)
        y=lambda v: h-17-(v-low)/span*(h-34)
        c.create_line(75,y(0),w-12,y(0),fill='#455467',dash=(3,4))
        c.create_text(8,12,text=f'{high:+.0f} €',fill=MUTED,anchor='w'); c.create_text(8,h-12,text=f'{low:+.0f} €',fill=MUTED,anchor='w')
        # Preserve extrema in screen-sized buckets for long histories.
        step=max(1,len(values)//max(int(w),1)); points=[]
        for start in range(0,len(values),step):
            chunk=values[start:start+step]
            indices=sorted(set((start,start+chunk.index(min(chunk)),start+chunk.index(max(chunk)),start+len(chunk)-1)))
            for i in indices: points.extend((75+i/max(len(values)-1,1)*(w-90),y(values[i])))
        if len(points)>=4: c.create_line(*points,fill=GREEN if r.balance>=0 else '#f37d89',width=2)
        c.create_text(w-15,10,text=f'Capital virtuel • départ 0 € • {len(values)-1} tours',fill=MUTED,anchor='e')

    def details(self):
        if hasattr(self,'detail') and self.detail.winfo_exists(): self.detail.lift(); return
        d=self.detail=tk.Toplevel(self); d.title('Analyses détaillées — instantané à l’ouverture'); d.geometry('1000x780'); d.configure(bg=BG)
        nb=ttk.Notebook(d); nb.pack(fill='both',expand=True,padx=12,pady=12)
        sectorframe=ttk.Frame(nb); scanframe=ttk.Frame(nb); mcframe=ttk.Frame(nb)
        nb.add(sectorframe,text='37 secteurs'); nb.add(scanframe,text='Intervalles & absences'); nb.add(mcframe,text='Comparaison au hasard')
        journal=ttk.Frame(nb); nb.add(journal,text='Journal virtuel')
        ledger=tk.Text(journal,bg=PANEL,fg=TEXT,wrap='word',padx=12,pady=12); ledger.pack(fill='both',expand=True)
        ledger.insert('end','Sélections enregistrées avant chaque saisie, avec les paramètres du moment.\nLes imports CSV n’inventent pas de mises antérieures.\n\n')
        for b in self.store.current.get('bets',[]):
            net=(17 if b['number'] in b['selection'] else -19)*b['stake']
            ledger.insert('end',f"Tour {b['spin']} • {b['strategy']} • fenêtre {b['window']} • {b['stake']:.2f} €/numéro\nSélection : {b['selection']}\nRésultat : {b['number']} • net {net:+.2f} €\n\n")
        ledger.configure(state='disabled')
        ttk.Label(sectorframe,text='Fenêtres tronquées à la taille disponible • écart en points face à 19/37.').pack(anchor='w',pady=6)
        cols=('start','count','freq','delta','20','50','100','200','numbers')
        tree=ttk.Treeview(sectorframe,columns=cols,show='headings',height=24)
        for col,title in zip(cols,('Départ','Touches','Fréq.','Écart','20','50','100','200','19 numéros')):
            tree.heading(col,text=title); tree.column(col,width=60 if col!='numbers' else 360,minwidth=35,stretch=col=='numbers')
        scroll=ttk.Scrollbar(sectorframe,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=scroll.set); scroll.pack(side='right',fill='y'); tree.pack(fill='both',expand=True)
        nums=tuple(self.numbers); window=int(self.window.get()); ss=sectors(nums[-window:]); scales={n:sectors(nums[-n:]) for n in (20,50,100,200)}
        for i,s in enumerate(ss):
            tree.insert('','end',values=(s['start'],s['count'],f'{s["frequency"]:.1%}' if nums else '—',f'{s["deviation"]*100:+.1f}' if nums else '—',*(f'{scales[n][i]["count"]}/{min(n,len(nums))}' for n in scales),' '.join(map(str,s['numbers']))))
        text=tk.Text(scanframe,bg=PANEL,fg=TEXT,wrap='word',padx=14,pady=14); text.pack(fill='both',expand=True)
        sc=scanner(nums)
        text.insert('end','ABSENCES (nombre de tours écoulés, jamais vu signalé)\n')
        for n,gap,seen in sc['absences']: text.insert('end',f'{n:2} : {gap}'+('' if seen else ' (jamais observé)')+'\n')
        text.insert('end','\nCYCLES HISTORIQUES — descriptifs, sans périodicité présumée\nNuméro : nombre d’intervalles / moyenne / écart-type / intervalles\n')
        for n,count,mean,sd in sc['cycles']: text.insert('end',f'{n} : {count} / {mean:.2f} / {sd:.2f} / {sc["intervals"][n]}\n')
        text.configure(state='disabled')
        ttk.Label(mcframe,text='Même taille et même mesure sur chaque série uniforme indépendante.\nPour la concentration, le maximum des 37 secteurs est recherché à chaque simulation.\nLes résultats portent sur un instantané ; la saisie peut continuer.',wraplength=850).pack(anchor='w',pady=12)
        controls=ttk.Frame(mcframe); controls.pack(fill='x')
        self.mc_kind=tk.StringVar(value=METRICS[0]); self.mc_runs=tk.StringVar(value='500'); self.mc_seed=tk.StringVar(value='19037'); self.mc_scope=tk.StringVar(value='Fenêtre')
        self._combo(controls,self.mc_kind,METRICS,38,lambda:None); self._combo(controls,self.mc_runs,('500','2000','10000'),7,lambda:None)
        self._combo(controls,self.mc_scope,('Fenêtre','Session entière'),14,lambda:None)
        ttk.Label(controls,text='Graine').pack(side='left'); ttk.Entry(controls,textvariable=self.mc_seed,width=9).pack(side='left')
        buttons=ttk.Frame(mcframe); buttons.pack(fill='x',pady=10)
        ttk.Button(buttons,text='Lancer',command=self.start_mc).pack(side='left'); ttk.Button(buttons,text='Annuler',command=self.mc_cancel.set).pack(side='left',padx=8)
        ttk.Label(mcframe,textvariable=self.mc_status,wraplength=850,justify='left',font=(FONT,11)).pack(anchor='w',pady=12)
        ttk.Label(mcframe,text='Les autres statistiques sont descriptives tant que leur référence aléatoire n’a pas été exécutée.\nLa référence aléatoire du comparateur est une seule trajectoire, pas un test de significativité.',foreground=ORANGE,wraplength=850).pack(anchor='w',pady=12)

    def start_mc(self):
        if self.mc_running: messagebox.showinfo('Simulation','Une simulation est déjà en cours.',parent=self.detail); return
        try: seed=int(self.mc_seed.get())
        except ValueError: messagebox.showwarning('Graine','Entier requis.',parent=self.detail); return
        history=tuple(self.numbers if self.mc_scope.get()=='Session entière' else self.numbers[-int(self.window.get()):])
        if not history: messagebox.showinfo('Simulation','Saisissez au moins un tirage.',parent=self.detail); return
        kind=self.mc_kind.get(); runs=int(self.mc_runs.get()); self.mc_cancel=threading.Event(); cancel=self.mc_cancel
        self.mc_running=True; self.mc_status.set(f'Simulation de {runs} séries de {len(history)} tirages…')
        def work():
            try:
                result=monte_carlo(history,kind,runs,seed,cancel,lambda i:self.messages.put(('mc_progress',0,i)))
                self.messages.put(('mc_done',0,result))
            except Exception as exc: logging.exception('Monte-Carlo'); self.messages.put(('mc_error',0,str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def close(self):
        if not self.save() and not messagebox.askyesno('Quitter sans sauvegarde','La sauvegarde a échoué. Quitter malgré tout ?',parent=self): return
        self.closing.set(); self.mc_cancel.set(); self.after_cancel(self.poll_id); self.destroy()


def main():
    data_directory().mkdir(parents=True,exist_ok=True)
    from logging.handlers import RotatingFileHandler
    handler=RotatingFileHandler(data_directory()/'errors.log',maxBytes=2_000_000,backupCount=2,encoding='utf-8')
    logging.basicConfig(level=logging.INFO,handlers=[handler],format='%(asctime)s %(levelname)s %(message)s')
    try: app=App()
    except Exception as exc:
        logging.exception('Démarrage impossible')
        root=tk.Tk(); root.withdraw(); messagebox.showerror('Démarrage impossible',f'{exc}\nSauvegarde préservée. Journal : {data_directory() / "errors.log"}',parent=root); root.destroy(); return
    app.mainloop()
