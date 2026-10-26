"""Deterministic European roulette analysis. No prediction of independent spins."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
import random
import statistics

WHEEL = (0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26)
RED = frozenset((1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36))
NAMES = ('19 voisins fixes','19 chauds','19 froids','10 chauds + 9 froids','19 voisins fréquents','19 retours rapides','19 voisins du dernier')
SECTORS = tuple(tuple(WHEEL[(i+j)%37] for j in range(19)) for i in range(37))


def validate(values):
    values = tuple(values)
    if any(type(n) is not int or not 0 <= n <= 36 for n in values):
        raise ValueError('Les tirages doivent être des entiers de 0 à 36.')
    return values


def sectors(history):
    counts = Counter(history)
    size = len(history)
    return tuple({'start': WHEEL[i], 'numbers': s, 'count': sum(counts[n] for n in s),
                  'frequency': sum(counts[n] for n in s)/size if size else 0,
                  'deviation': sum(counts[n] for n in s)/size-19/37 if size else None}
                 for i,s in enumerate(SECTORS))


@lru_cache(maxsize=8192)
def selections(history):
    """history is the selection window, oldest first; ties follow wheel order."""
    counts = Counter(history)
    order = {n:i for i,n in enumerate(WHEEL)}
    hot = sorted(WHEEL, key=lambda n:(-counts[n], order[n]))
    cold = sorted(WHEEL, key=lambda n:(counts[n], order[n]))
    mixed = hot[:10] + [n for n in cold if n not in hot[:10]][:9]
    last = {}
    gaps = defaultdict(list)
    for i,n in enumerate(history):
        if n in last: gaps[n].append(i-last[n])
        last[n] = i
    # Repeated numbers first, ranked by mean recurrence gap (no invented intervals).
    rapid = sorted(WHEEL, key=lambda n:(statistics.fmean(gaps[n]) if gaps[n] else float('inf'),order[n]))
    best = max(range(37), key=lambda i:sum(counts[n] for n in SECTORS[i]))
    idx = WHEEL.index(history[-1]) if history else 0
    neighbors = tuple(WHEEL[(idx+j)%37] for j in range(-9,10)) if history else SECTORS[0]
    return (SECTORS[0],tuple(hot[:19]),tuple(cold[:19]),tuple(mixed),SECTORS[best],tuple(rapid[:19]),neighbors)


@dataclass(frozen=True)
class Result:
    hits: int
    misses: int
    balance: float
    wagered: float
    roi: float
    drawdown: float
    longest_loss: int
    longest_hit: int
    curve: tuple
    outcomes: tuple


def summarize(outcomes, stake=1):
    outcomes = tuple(bool(x) for x in outcomes)
    stake = float(stake)
    if not 0 < stake < float('inf'): raise ValueError('Mise positive et finie requise.')
    units = peak = dd = loss = hit = longest_loss = longest_hit = 0
    curve = [0.0]
    for won in outcomes:
        units += 17 if won else -19
        peak = max(peak,units)
        dd = max(dd,peak-units)
        loss = 0 if won else loss+1
        hit = hit+1 if won else 0
        longest_loss, longest_hit = max(longest_loss,loss),max(longest_hit,hit)
        curve.append(units*stake)
    wagered = 19*len(outcomes)*stake
    return Result(sum(outcomes),len(outcomes)-sum(outcomes),units*stake,wagered,
                  units/(19*len(outcomes))*100 if outcomes else 0,dd*stake,longest_loss,longest_hit,tuple(curve),outcomes)


class Evaluator:
    """Append-only cache. Each recorded selection precedes its evaluated result."""
    def __init__(self, window=50, seed=19037):
        self.window, self.seed = window, seed
        self.history = []
        self.outcomes = [[] for _ in range(8)]
        self.recorded = []
        self.rng = random.Random(seed)

    def sync(self, history):
        history = validate(history)
        if len(history)<len(self.history) or tuple(self.history)!=history[:len(self.history)]:
            self.__init__(self.window,self.seed)
        for n in history[len(self.history):]:
            chosen = selections(tuple(self.history[-self.window:])) + (tuple(self.rng.sample(WHEEL,19)),)
            self.recorded.append(chosen)
            for out, nums in zip(self.outcomes,chosen): out.append(n in nums)
            self.history.append(n)
        return self

    def results(self, period=200, stake=1):
        return tuple(summarize(o[-period:] if period else o,stake) for o in self.outcomes)


def scanner(history):
    last, intervals = {}, defaultdict(list)
    immediate = short5 = short10 = 0
    longest_unique = current_unique = 0
    left = 0
    last_repeat = None
    for i,n in enumerate(history):
        if n in last:
            gap = i-last[n]
            intervals[n].append(gap)
            immediate += gap==1
            short5 += gap<=5
            short10 += gap<=10
            left = max(left,last[n]+1)
            last_repeat = (n,gap,i+1)
        last[n] = i
        current_unique = i-left+1
        longest_unique = max(longest_unique,current_unique)
    absences = sorted(WHEEL, key=lambda n:(-(len(history)-1-last[n] if n in last else len(history)),WHEEL.index(n)))
    return {'immediate':immediate,'short5':short5,'short10':short10,
            'distinct37':len(set(history[-37:])), 'max_gap':max((g for gs in intervals.values() for g in gs),default=0),
            'unique_run':longest_unique,'current_unique':current_unique,'last_repeat':last_repeat,
            'absences':[(n,len(history)-1-last[n] if n in last else len(history),n in last) for n in absences],
            'cycles':[(n, len(gs), statistics.fmean(gs), statistics.pstdev(gs)) for n,gs in sorted(intervals.items())],
            'intervals':dict(intervals)}


METRICS = ('Concentration maximale (37 secteurs)','Répétitions immédiates','Retours ≤ 5 tirages','Retours ≤ 10 tirages','Plus grand intervalle','Plus longue série sans répétition','Absence maximale','Diversité sur 37 tirages (faible)')


def metric(history, kind):
    if kind==METRICS[0]: return max(s['count'] for s in sectors(history))
    sc = scanner(history)
    return {METRICS[1]:sc['immediate'], METRICS[2]:sc['short5'],METRICS[3]:sc['short10'],
            METRICS[4]:sc['max_gap'], METRICS[5]:sc['unique_run'],
            METRICS[6]:sc['absences'][0][1],METRICS[7]:sc['distinct37']}[kind]


def monte_carlo(history, kind=METRICS[0], runs=500, seed=19037, cancel=None, progress=None):
    history = validate(history)
    if not history: raise ValueError('Saisissez des tirages avant la comparaison au hasard.')
    if runs not in (500,2000,10000): raise ValueError('Choisir 500, 2 000 ou 10 000 simulations.')
    if kind not in METRICS: raise ValueError('Mesure inconnue.')
    rng = random.Random(seed)
    observed = metric(history,kind)
    scores = []
    for i in range(runs):
        if cancel is not None and cancel.is_set(): return None
        scores.append(metric(tuple(rng.randrange(37) for _ in history),kind))
        if progress and (i+1)%50==0: progress(i+1)
    low_tail = kind==METRICS[-1]
    extreme = sum(x<=observed if low_tail else x>=observed for x in scores)
    return {'observed':observed,'mean':statistics.fmean(scores),
            'percentile':100*(sum(x<observed for x in scores)+.5*sum(x==observed for x in scores))/runs,
            'p':(extreme+1)/(runs+1),'extreme':extreme,'runs':runs,'size':len(history),'seed':seed,'kind':kind,
            'tail':'inférieure' if low_tail else 'supérieure'}
