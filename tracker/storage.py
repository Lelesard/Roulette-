import csv
import json
import sqlite3
from datetime import datetime, timezone
from .domain import number, payout, attributes, WHEEL


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, name TEXT NOT NULL, table_name TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS spins(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id), number INTEGER NOT NULL CHECK(number BETWEEN 0 AND 36), created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operations(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id), kind TEXT NOT NULL, amount INTEGER NOT NULL, stake INTEGER NOT NULL DEFAULT 0, gross INTEGER NOT NULL DEFAULT 0, spin_id INTEGER REFERENCES spins(id), note TEXT NOT NULL, created TEXT NOT NULL, voided INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, event TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS annotations(id INTEGER PRIMARY KEY, video TEXT NOT NULL, seconds REAL NOT NULL, note TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS profiles(name TEXT PRIMARY KEY, config TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ocr_state(session_id INTEGER PRIMARY KEY REFERENCES sessions(id), snapshot TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS spins_session ON spins(session_id,id);
        CREATE INDEX IF NOT EXISTS operations_session ON operations(session_id,id);
        """)

    def close(self):
        self.db.close()

    def sessions(self):
        return self.db.execute("SELECT * FROM sessions ORDER BY id DESC").fetchall()

    def create_session(self, name, table):
        if not name.strip() or not table.strip():
            raise ValueError("Nom et table requis.")
        with self.db:
            return self.db.execute(
                "INSERT INTO sessions(name,table_name,created) VALUES(?,?,?)",
                (name.strip(), table.strip(), now()),
            ).lastrowid

    def setting(self, key, default=None):
        row = self.db.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else default

    def save_setting(self, key, value):
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value))
            )

    def spins(self, sid, limit=100, offset=0):
        return self.db.execute(
            "SELECT * FROM spins WHERE session_id=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (sid, limit, offset),
        ).fetchall()

    def counts(self, sid):
        return dict(
            self.db.execute(
                "SELECT number,COUNT(*) FROM spins WHERE session_id=? GROUP BY number",
                (sid,),
            ).fetchall()
        )

    def add_spin(self, sid, n, bets=(), settle_pending=False):
        number(n)
        # Validate and calculate everything before starting the transaction.
        stake = sum(b["stake"] for b in bets)
        gross = sum(payout(b["kind"], b["target"], b["stake"], n) for b in bets)
        with self.db:
            spin = self.db.execute(
                "INSERT INTO spins(session_id,number,created) VALUES(?,?,?)",
                (sid, n, now()),
            ).lastrowid
            if bets:
                self.db.execute(
                    "INSERT INTO operations(session_id,kind,amount,stake,gross,spin_id,note,created) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        sid,
                        "tour",
                        gross - stake,
                        stake,
                        gross,
                        spin,
                        json.dumps(list(bets), ensure_ascii=False),
                        now(),
                    ),
                )
            if settle_pending:
                self.db.execute(
                    "INSERT OR REPLACE INTO settings VALUES(?,?)",
                    (f"pending_{sid}", "[]"),
                )
            return spin

    def edit_spin(self, spin, n=None):
        with self.db:
            row = self.db.execute("SELECT * FROM spins WHERE id=?", (spin,)).fetchone()
            if not row:
                raise ValueError("Résultat introuvable.")
            if n is not None:
                number(n)
            op = self.db.execute(
                "SELECT * FROM operations WHERE spin_id=? AND voided=0", (spin,)
            ).fetchone()
            if op:
                if n is None:
                    self.db.execute(
                        "UPDATE operations SET voided=1 WHERE id=?", (op["id"],)
                    )
                else:
                    bets = json.loads(op["note"])
                    gross = sum(
                        payout(b["kind"], b["target"], b["stake"], n) for b in bets
                    )
                    self.db.execute(
                        "UPDATE operations SET gross=?,amount=? WHERE id=?",
                        (gross, gross - op["stake"], op["id"]),
                    )
            self.db.execute(
                "INSERT INTO audit(event,detail,created) VALUES(?,?,?)",
                (
                    "correction résultat",
                    json.dumps({"avant": dict(row), "après": n}),
                    now(),
                ),
            )
            if n is None:
                self.db.execute(
                    "UPDATE operations SET spin_id=NULL WHERE spin_id=?", (spin,)
                )
                self.db.execute("DELETE FROM spins WHERE id=?", (spin,))
            else:
                self.db.execute("UPDATE spins SET number=? WHERE id=?", (n, spin))

    def cash(self, sid, kind, amount, note=""):
        if (
            kind not in ("initial", "dépôt", "retrait", "ajustement")
            or isinstance(amount, bool)
            or not isinstance(amount, int)
            or amount == 0
        ):
            raise ValueError("Opération invalide.")
        if kind != "ajustement" and amount < 0:
            raise ValueError("Montant positif requis.")
        with self.db:
            if (
                kind == "initial"
                and self.db.execute(
                    "SELECT 1 FROM operations WHERE session_id=? AND kind='initial' AND voided=0",
                    (sid,),
                ).fetchone()
            ):
                raise ValueError("Capital initial déjà saisi.")
            self.db.execute(
                "INSERT INTO operations(session_id,kind,amount,note,created) VALUES(?,?,?,?,?)",
                (sid, kind, -amount if kind == "retrait" else amount, note, now()),
            )

    def void(self, opid):
        with self.db:
            row = self.db.execute(
                "SELECT * FROM operations WHERE id=?", (opid,)
            ).fetchone()
            if not row or row["voided"]:
                raise ValueError("Opération absente ou déjà annulée.")
            self.db.execute("UPDATE operations SET voided=1 WHERE id=?", (opid,))
            self.db.execute(
                "INSERT INTO audit(event,detail,created) VALUES(?,?,?)",
                ("annulation opération", json.dumps(dict(row)), now()),
            )

    def operations(self, sid):
        return self.db.execute(
            "SELECT * FROM operations WHERE session_id=? ORDER BY id", (sid,)
        ).fetchall()

    def summary(self, sid=None):
        sql = "SELECT COALESCE(SUM(amount),0),COALESCE(SUM(stake),0),COALESCE(SUM(gross),0), COALESCE(SUM(CASE WHEN kind='tour' AND amount<0 THEN -amount ELSE 0 END),0), COALESCE(SUM(CASE WHEN kind='tour' AND amount>0 THEN amount ELSE 0 END),0) FROM operations WHERE voided=0"
        row = self.db.execute(
            sql + (" AND session_id=?" if sid is not None else ""),
            (sid,) if sid is not None else (),
        ).fetchone()
        return {
            "balance": row[0],
            "stake": row[1],
            "gross": row[2],
            "net": row[2] - row[1],
            "roi": 100 * (row[2] - row[1]) / row[1] if row[1] else 0,
            "losses": row[3],
            "profits": row[4],
        }

    def streaks(self, sid):
        current = {}
        longest = {}
        previous = {}
        run = {}
        for row in self.db.execute(
            "SELECT number FROM spins WHERE session_id=? ORDER BY id", (sid,)
        ):
            for kind, value in attributes(row[0]).items():
                run[kind] = run.get(kind, 0) + 1 if previous.get(kind) == value else 1
                previous[kind] = value
                current[kind] = (value, run[kind])
                longest[kind] = max(longest.get(kind, 0), run[kind])
        return current, longest

    def export(self, sid, path):
        rows = [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM spins WHERE session_id=? ORDER BY id", (sid,)
            )
        ]
        for r in rows:
            r.update(attributes(r["number"]))
            r["position_cylindre"] = WHEEL.index(r["number"])
        with open(path, "w", encoding="utf-8", newline="") as f:
            if str(path).lower().endswith(".json"):
                json.dump(rows, f, ensure_ascii=False, indent=2)
            else:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "id",
                        "session_id",
                        "number",
                        "created",
                        "couleur",
                        "parité",
                        "hauteur",
                        "douzaine",
                        "colonne",
                        "position_cylindre",
                    ],
                )
                writer.writeheader()
                writer.writerows(rows)

    def import_file(self, sid, path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = (
                json.load(f)
                if str(path).lower().endswith(".json")
                else list(csv.DictReader(f))
            )
        values = []
        if not isinstance(rows, list):
            raise ValueError("Le fichier doit contenir une liste de résultats.")
        for r in rows:
            if not isinstance(r, dict):
                raise ValueError("Chaque résultat doit être un objet.")
            v = r.get("number", r.get("numero", r.get("numéro")))
            if isinstance(v, bool) or (
                not isinstance(v, int)
                and (not isinstance(v, str) or not v.strip().isdigit())
            ):
                raise ValueError("Numéro importé invalide.")
            n = number(int(v))
            created = r.get("created") or now()
            try:
                stamp = datetime.fromisoformat(created)
                if stamp.tzinfo is None:
                    raise ValueError()
                created = stamp.astimezone(timezone.utc).isoformat()
            except (ValueError, TypeError):
                raise ValueError(
                    "Date invalide : utilisez ISO 8601 avec fuseau horaire."
                ) from None
            values.append((n, created))
        with self.db:
            self.db.executemany(
                "INSERT INTO spins(session_id,number,created) VALUES(?,?,?)",
                [(sid, n, created) for n, created in values],
            )
        return len(values)

    def annotate(self, video, seconds, note):
        if not note.strip():
            raise ValueError("Annotation vide.")
        with self.db:
            self.db.execute(
                "INSERT INTO annotations(video,seconds,note,created) VALUES(?,?,?,?)",
                (video, seconds, note, now()),
            )

    def profile(self, name):
        row = self.db.execute(
            "SELECT config FROM profiles WHERE name=?", (name,)
        ).fetchone()
        return json.loads(row[0]) if row else {}

    def save_profile(self, name, config):
        if not name.strip():
            raise ValueError("Nom du profil requis.")
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO profiles VALUES(?,?)",
                (name, json.dumps(config)),
            )

    def profile_names(self):
        return [
            r[0] for r in self.db.execute("SELECT name FROM profiles ORDER BY name")
        ]

    def ocr_snapshot(self, sid):
        row = self.db.execute(
            "SELECT snapshot FROM ocr_state WHERE session_id=?", (sid,)
        ).fetchone()
        return json.loads(row[0]) if row else []

    def commit_ocr(self, sid, snapshot, newest):
        """Persist the overlap cursor and new results in the same transaction; no bets settled."""
        for n in (*snapshot, *newest):
            number(n)
        with self.db:
            self.db.executemany(
                "INSERT INTO spins(session_id,number,created) VALUES(?,?,?)",
                [(sid, n, now()) for n in reversed(newest)],
            )
            self.db.execute(
                "INSERT OR REPLACE INTO ocr_state VALUES(?,?)",
                (sid, json.dumps(snapshot)),
            )
