from decimal import Decimal, InvalidOperation

WHEEL = (
    0,
    32,
    15,
    19,
    4,
    21,
    2,
    25,
    17,
    34,
    6,
    27,
    13,
    36,
    11,
    30,
    8,
    23,
    10,
    5,
    24,
    16,
    33,
    1,
    20,
    14,
    31,
    9,
    22,
    18,
    29,
    7,
    28,
    12,
    35,
    3,
    26,
)
RED = frozenset((1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36))


def number(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 36:
        raise ValueError("Le numéro doit être un entier entre 0 et 36.")
    return value


def cents(text):
    try:
        value = Decimal(str(text).replace(",", "."))
        if (
            not value.is_finite()
            or value <= 0
            or value * 100 != (value * 100).to_integral_value()
        ):
            raise ValueError()
        return int(value * 100)
    except (InvalidOperation, ValueError):
        raise ValueError(
            "Saisissez un montant positif, avec au plus deux décimales."
        ) from None


def sector(center, size):
    number(center)
    if size not in (9, 15, 19):
        raise ValueError("La zone doit contenir 9, 15 ou 19 numéros.")
    i = WHEEL.index(center)
    return tuple(WHEEL[(i + j) % 37] for j in range(-(size // 2), size // 2 + 1))


def attributes(n):
    number(n)
    return {
        "couleur": "vert" if n == 0 else "rouge" if n in RED else "noir",
        "parité": "—" if n == 0 else "pair" if n % 2 == 0 else "impair",
        "hauteur": "—" if n == 0 else "manque" if n <= 18 else "passe",
        "douzaine": 0 if n == 0 else (n - 1) // 12 + 1,
        "colonne": 0 if n == 0 else (n - 1) % 3 + 1,
    }


def payout(kind, target, stake, result):
    number(result)
    if isinstance(stake, bool) or not isinstance(stake, int) or stake <= 0:
        raise ValueError("Mise invalide.")
    a = attributes(result)
    if kind == "plein":
        number(int(target))
        win = result == int(target)
        multiplier = 36
    elif kind in ("couleur", "parité", "hauteur"):
        allowed = {
            "couleur": ("rouge", "noir"),
            "parité": ("pair", "impair"),
            "hauteur": ("manque", "passe"),
        }
        if target not in allowed[kind]:
            raise ValueError("Cible invalide.")
        win = a[kind] == target
        multiplier = 2
    elif kind in ("douzaine", "colonne"):
        if int(target) not in (1, 2, 3):
            raise ValueError("Cible invalide.")
        win = a[kind] == int(target)
        multiplier = 3
    else:
        raise ValueError("Type de mise inconnu.")
    return stake * multiplier if win else 0
