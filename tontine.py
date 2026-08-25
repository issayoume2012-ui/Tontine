# ============================================================
# DEPENDANCES : uniquement celles de requirements.txt
# ============================================================
import os
import re
import hashlib
import secrets
from io import BytesIO
from datetime import date, datetime, timedelta
from urllib.parse import urlparse, unquote
import pandas as pd
import streamlit as st
from supabase import create_client, Client
# ============================================================
# BASE DE DONNEES : SUPABASE POSTGRESQL UNIQUEMENT
# ============================================================
# IMPORTANT : aucune base locale n'est utilisée.
# Toutes les opérations de l'application passent par PostgreSQL Supabase.
#
# Dans Streamlit Cloud, configurez au minimum :
# SUPABASE_DB_URL = "postgresql://postgres:PASSWORD@HOST:5432/postgres"
# SUPABASE_URL    = "https://xxxxx.supabase.co"
# SUPABASE_KEY    = "votre-cle-anon-ou-service"
#
# SUPABASE_DB_URL est la source de vérité pour les données.

def _secret(name, default=""):
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return os.getenv(name, value or default)

SUPABASE_URL = _secret("SUPABASE_URL", "")
SUPABASE_KEY = _secret("SUPABASE_KEY", "")
SUPABASE_DB_URL = _secret("SUPABASE_DB_URL", "")

# Compatibilité avec une configuration séparée.
SUPABASE_DB_HOST = _secret("SUPABASE_DB_HOST", "")
SUPABASE_DB_PORT = int(_secret("SUPABASE_DB_PORT", "5432") or "5432")
SUPABASE_DB_NAME = _secret("SUPABASE_DB_NAME", "postgres")
SUPABASE_DB_USER = _secret("SUPABASE_DB_USER", "postgres")
SUPABASE_DB_PASSWORD = _secret("SUPABASE_DB_PASSWORD", "")

if not SUPABASE_DB_URL and SUPABASE_DB_HOST and SUPABASE_DB_PASSWORD:
    from urllib.parse import quote
    SUPABASE_DB_URL = (
        f"postgresql://{SUPABASE_DB_USER}:{quote(SUPABASE_DB_PASSWORD)}"
        f"@{SUPABASE_DB_HOST}:{SUPABASE_DB_PORT}/{SUPABASE_DB_NAME}"
        "?sslmode=require"
    )

st.set_page_config(page_title="Tontine Manager", page_icon="💰", layout="wide")

_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None and SUPABASE_URL and SUPABASE_KEY:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

def supabase_configured():
    return bool(SUPABASE_URL and SUPABASE_KEY and SUPABASE_DB_URL)

class PGDictCursor:
    def __init__(self, cursor):
        self.cursor = cursor
    @property
    def description(self):
        return self.cursor.description
    @property
    def rowcount(self):
        return self.cursor.rowcount
    def _row_to_dict(self, row):
        if row is None:
            return None
        if isinstance(row, dict):
            return row
        columns = [d[0] for d in (self.cursor.description or [])]
        return dict(zip(columns, row))
    def fetchone(self):
        return self._row_to_dict(self.cursor.fetchone())
    def fetchall(self):
        return [self._row_to_dict(r) for r in self.cursor.fetchall()]
    def __iter__(self):
        for row in self.cursor:
            yield self._row_to_dict(row)
    def close(self):
        return self.cursor.close()

class PGConnection:
    """Adaptateur PostgreSQL utilisant pg8000, bibliothèque pure Python."""
    def __init__(self, connection):
        self.connection = connection
    def execute(self, sql, params=None):
        sql = sql.replace("?", "%s")
        cur = self.connection.cursor()
        cur.execute(sql, params or ())
        return PGDictCursor(cur)
    def cursor(self, *args, **kwargs):
        return self.connection.cursor(*args, **kwargs)
    def commit(self):
        return self.connection.commit()
    def rollback(self):
        return self.connection.rollback()
    def close(self):
        return self.connection.close()
    def __getattr__(self, name):
        return getattr(self.connection, name)

@contextmanager
def db():
    """
    Connexion directe à PostgreSQL/Supabase avec pg8000.
    """
    conn = None
    try:
        if not SUPABASE_DB_URL:
            raise RuntimeError(
                "SUPABASE_DB_URL n'est pas configurée dans Streamlit Secrets."
            )

        parsed = urlparse(SUPABASE_DB_URL)
        host = parsed.hostname
        port = parsed.port or 5432
        user = unquote(parsed.username or "")
        password = unquote(parsed.password or "")
        database = (parsed.path or "/postgres").lstrip("/") or "postgres"

        if not host or not user:
            raise RuntimeError("SUPABASE_DB_URL est incomplète.")

        import pg8000.dbapi as pg

        conn = pg.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
            ssl_context=True,
            timeout=15,
        )

        c = PGConnection(conn)
        yield c
        conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

def read_df(sql, params=()):
    with db() as c:
        cur = c.execute(sql, params)
        rows = cur.fetchall()
    return pd.DataFrame([dict(r) for r in rows])




def now(): return datetime.now().isoformat(timespec="seconds")
def money(v): return f"{float(v or 0):,.0f} FCFA".replace(","," ")

def dict_rows(rows):
    """Convertit les lignes PostgreSQL en dictionnaires avant de les passer à Streamlit.
    Les lignes PostgreSQL sont converties en dictionnaires pour être
    facilement sérialisables par Streamlit.
    """
    return [dict(r) for r in rows]
def password_hash(p,s=None):
    s=s or secrets.token_hex(16)
    return s,hashlib.pbkdf2_hmac("sha256",p.encode(),s.encode(),120000).hex()
def valid_password(p,s,h): return secrets.compare_digest(password_hash(p,s)[1],h)

def test_database_connection():
    """Teste la connexion PostgreSQL distante avant l'initialisation."""
    with db() as c:
        row = c.execute("SELECT current_database() AS database, current_user AS username, version() AS version").fetchone()
    return row


def supabase_sync_status():
    """Vérifie que l'application écrit/lit directement dans Supabase PostgreSQL."""
    if not SUPABASE_DB_URL:
        return False, "SUPABASE_DB_URL manquante"
    try:
        with db() as c:
            row = c.execute(
                "SELECT current_database() AS database, current_user AS username"
            ).fetchone()
        return True, f"Supabase connecté — base: {row['database']} — utilisateur: {row['username']}"
    except Exception as exc:
        return False, f"Connexion Supabase impossible : {exc}"

def render_sync_status():
    ok, message = supabase_sync_status()
    if ok:
        st.success("🟢 " + message)
    else:
        st.error("🔴 " + message)
        st.info(
            "Configurez SUPABASE_DB_URL dans Streamlit Cloud. "
            "L'application n'utilise plus une base locale de secours : "
            "Supabase est la base de données unique."
        )

def init_db():
    """
    Initialise la base PostgreSQL Supabase.
    La fonction est idempotente : elle peut être exécutée à chaque lancement.
    Elle crée les tables et ajoute les colonnes manquantes sans supprimer
    les données existantes.
    """
    with db() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            id BIGSERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            hash TEXT NOT NULL,
            role TEXT DEFAULT 'admin',
            tontine_id BIGINT
        );

        CREATE TABLE IF NOT EXISTS whitelist(
            id BIGSERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            description TEXT,
            active INTEGER DEFAULT 1,
            tontine_id BIGINT,
            username TEXT,
            salt TEXT,
            hash TEXT,
            nom_tontine TEXT,
            infos_tontine TEXT
        );

        CREATE TABLE IF NOT EXISTS tontines(
            id BIGSERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            nom TEXT NOT NULL,
            description TEXT,
            date_debut TEXT,
            date_fin TEXT,
            active INTEGER DEFAULT 1,
            verrouillee INTEGER DEFAULT 0,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS members(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT,
            code TEXT NOT NULL,
            prenom TEXT NOT NULL,
            nom TEXT NOT NULL,
            telephone TEXT,
            inscription TEXT,
            profil_id BIGINT,
            cotisation DOUBLE PRECISION DEFAULT 0,
            solidarite DOUBLE PRECISION DEFAULT 0,
            periodicite TEXT DEFAULT 'Hebdomadaire',
            date_debut TEXT,
            date_fin TEXT,
            active INTEGER DEFAULT 1,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS paiements(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT,
            membre_id BIGINT NOT NULL,
            periode TEXT NOT NULL,
            echeance TEXT NOT NULL,
            cotisation_due DOUBLE PRECISION DEFAULT 0,
            cotisation_payee DOUBLE PRECISION DEFAULT 0,
            solidarite_due DOUBLE PRECISION DEFAULT 0,
            solidarite_payee DOUBLE PRECISION DEFAULT 0,
            date_paiement TEXT,
            statut TEXT DEFAULT 'En attente',
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS emprunts(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT,
            membre_id BIGINT NOT NULL,
            montant DOUBLE PRECISION DEFAULT 0,
            taux DOUBLE PRECISION DEFAULT 0,
            interet DOUBLE PRECISION DEFAULT 0,
            total DOUBLE PRECISION DEFAULT 0,
            date_octroi TEXT,
            date_limite TEXT,
            statut TEXT DEFAULT 'En cours'
        );

        CREATE TABLE IF NOT EXISTS remboursements(
            id BIGSERIAL PRIMARY KEY,
            emprunt_id BIGINT NOT NULL,
            montant DOUBLE PRECISION DEFAULT 0,
            date TEXT
        );

        CREATE TABLE IF NOT EXISTS tours(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT,
            semaine INTEGER,
            date TEXT,
            membre_id BIGINT,
            montant DOUBLE PRECISION DEFAULT 0,
            statut TEXT DEFAULT 'Planifié'
        );

        CREATE TABLE IF NOT EXISTS fonds(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT,
            date TEXT,
            type TEXT,
            montant DOUBLE PRECISION DEFAULT 0,
            membre_id BIGINT,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS journal(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT,
            date TEXT,
            action TEXT,
            details TEXT
        );

        CREATE TABLE IF NOT EXISTS encaissements(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT NOT NULL,
            membre_id BIGINT NOT NULL,
            date TEXT NOT NULL,
            solidarite DOUBLE PRECISION DEFAULT 0,
            epargne DOUBLE PRECISION DEFAULT 0,
            amende DOUBLE PRECISION DEFAULT 0,
            observation TEXT
        );

        CREATE TABLE IF NOT EXISTS semaines_gestion(
            id BIGSERIAL PRIMARY KEY,
            tontine_id BIGINT NOT NULL,
            debut TEXT NOT NULL,
            fin TEXT NOT NULL,
            libelle TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT
        );
        """)

        # ---------------------------------------------------------
        # MIGRATION NON DESTRUCTIVE DES COLONNES
        # ---------------------------------------------------------
        migrations = {
            "admins": [
                ("role", "TEXT DEFAULT 'admin'"),
                ("tontine_id", "BIGINT"),
            ],
            "whitelist": [
                ("tontine_id", "BIGINT"),
                ("username", "TEXT"),
                ("salt", "TEXT"),
                ("hash", "TEXT"),
                ("nom_tontine", "TEXT"),
                ("infos_tontine", "TEXT"),
            ],
            "members": [
                ("tontine_id", "BIGINT"),
                ("code", "TEXT"),
                ("telephone", "TEXT"),
                ("inscription", "TEXT"),
                ("profil_id", "BIGINT"),
                ("cotisation", "DOUBLE PRECISION DEFAULT 0"),
                ("solidarite", "DOUBLE PRECISION DEFAULT 0"),
                ("periodicite", "TEXT DEFAULT 'Hebdomadaire'"),
                ("date_debut", "TEXT"),
                ("date_fin", "TEXT"),
                ("active", "INTEGER DEFAULT 1"),
                ("notes", "TEXT"),
            ],
            "paiements": [
                ("tontine_id", "BIGINT"),
                ("cotisation_due", "DOUBLE PRECISION DEFAULT 0"),
                ("cotisation_payee", "DOUBLE PRECISION DEFAULT 0"),
                ("solidarite_due", "DOUBLE PRECISION DEFAULT 0"),
                ("solidarite_payee", "DOUBLE PRECISION DEFAULT 0"),
                ("date_paiement", "TEXT"),
                ("statut", "TEXT DEFAULT 'En attente'"),
                ("notes", "TEXT"),
            ],
            "emprunts": [
                ("tontine_id", "BIGINT"),
                ("montant", "DOUBLE PRECISION DEFAULT 0"),
                ("taux", "DOUBLE PRECISION DEFAULT 0"),
                ("interet", "DOUBLE PRECISION DEFAULT 0"),
                ("total", "DOUBLE PRECISION DEFAULT 0"),
                ("date_octroi", "TEXT"),
                ("date_limite", "TEXT"),
                ("statut", "TEXT DEFAULT 'En cours'"),
            ],
            "tours": [
                ("tontine_id", "BIGINT"),
                ("semaine", "INTEGER"),
                ("date", "TEXT"),
                ("membre_id", "BIGINT"),
                ("montant", "DOUBLE PRECISION DEFAULT 0"),
                ("statut", "TEXT DEFAULT 'Planifié'"),
            ],
            "fonds": [
                ("tontine_id", "BIGINT"),
                ("date", "TEXT"),
                ("type", "TEXT"),
                ("montant", "DOUBLE PRECISION DEFAULT 0"),
                ("membre_id", "BIGINT"),
                ("description", "TEXT"),
            ],
            "journal": [
                ("tontine_id", "BIGINT"),
                ("date", "TEXT"),
                ("action", "TEXT"),
                ("details", "TEXT"),
            ],
        }

        for table, columns in migrations.items():
            for name, definition in columns:
                c.execute(f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{name}" {definition}')

        # Supprime d'éventuels doublons historiques avant de créer
        # l'index unique utilisé par ON CONFLICT.
        c.execute("""
            DELETE FROM paiements p
            USING paiements p2
            WHERE p.id > p2.id
              AND p.tontine_id IS NOT DISTINCT FROM p2.tontine_id
              AND p.membre_id = p2.membre_id
              AND p.periode = p2.periode
        """)

        # Index et contrainte nécessaire au ON CONFLICT des paiements.
        c.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_paiements_tontine_membre_periode
            ON paiements(tontine_id,membre_id,periode)
        """)
        for sql in [
            "CREATE INDEX IF NOT EXISTS idx_members_tontine ON members(tontine_id)",
            "CREATE INDEX IF NOT EXISTS idx_paiements_tontine ON paiements(tontine_id)",
            "CREATE INDEX IF NOT EXISTS idx_emprunts_tontine ON emprunts(tontine_id)",
            "CREATE INDEX IF NOT EXISTS idx_tours_tontine ON tours(tontine_id)",
            "CREATE INDEX IF NOT EXISTS idx_fonds_tontine ON fonds(tontine_id)",
            "CREATE INDEX IF NOT EXISTS idx_journal_tontine ON journal(tontine_id)",
            "CREATE INDEX IF NOT EXISTS idx_encaissements_tontine_date ON encaissements(tontine_id,date)",
            "CREATE INDEX IF NOT EXISTS idx_encaissements_membre ON encaissements(membre_id)",
            "CREATE INDEX IF NOT EXISTS idx_semaines_tontine ON semaines_gestion(tontine_id,active)",
        ]:
            c.execute(sql)

        c.execute("UPDATE admins SET role='admin' WHERE role IS NULL OR TRIM(role)=''")

        # ---------------------------------------------------------
        # ADMIN GENERAL PAR DEFAUT
        # ---------------------------------------------------------
        admin = c.execute("SELECT 1 FROM admins LIMIT 1").fetchone()
        if not admin:
            s, h = password_hash("admin123")
            c.execute(
                "INSERT INTO admins(username,salt,hash,role,tontine_id) VALUES(%s,%s,%s,%s,%s)",
                ("admin", s, h, "admin", None)
            )

        # ---------------------------------------------------------
        # PROFIL STANDARD
        # ---------------------------------------------------------
        profile = c.execute("SELECT 1 FROM whitelist LIMIT 1").fetchone()
        if not profile:
            c.execute(
                "INSERT INTO whitelist(code,label,description,active) VALUES(%s,%s,%s,%s)",
                ("STANDARD", "Membre standard", "Profil membre standard", 1)
            )

        # ---------------------------------------------------------
        # TONTINE PAR DEFAUT
        # ---------------------------------------------------------
        t = c.execute("SELECT id FROM tontines ORDER BY id LIMIT 1").fetchone()

        if t:
            default_tid = t["id"]
        else:
            debut = date.today()
            fin = debut + timedelta(days=364)
            row = c.execute(
                """
                INSERT INTO tontines(
                    code,nom,description,date_debut,date_fin,
                    active,verrouillee,created_at
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    "TONTINE-001",
                    "Tontine principale",
                    "Tontine principale créée automatiquement",
                    debut.isoformat(),
                    fin.isoformat(),
                    1,
                    0,
                    now()
                )
            ).fetchone()
            default_tid = row["id"]

        # ---------------------------------------------------------
        # MIGRATION DES ANCIENS MEMBRES
        # ---------------------------------------------------------
        members = c.execute("SELECT id,code FROM members ORDER BY id").fetchall()
        for m in members:
            if not m["code"] or not str(m["code"]).strip():
                c.execute(
                    "UPDATE members SET code=%s WHERE id=%s",
                    (f"MBR-{int(m['id']):05d}", m["id"])
                )

        c.execute(
            "UPDATE members SET tontine_id=%s WHERE tontine_id IS NULL",
            (default_tid,)
        )

        c.execute("UPDATE members SET cotisation=0 WHERE cotisation IS NULL")
        c.execute("UPDATE members SET solidarite=0 WHERE solidarite IS NULL")
        c.execute("UPDATE members SET active=1 WHERE active IS NULL")
        c.execute("""
            UPDATE members
            SET periodicite='Hebdomadaire'
            WHERE periodicite IS NULL OR TRIM(periodicite)=''
        """)

        c.execute("""
            UPDATE paiements p
            SET tontine_id=m.tontine_id
            FROM members m
            WHERE p.membre_id=m.id AND p.tontine_id IS NULL
        """)
        c.execute("""
            UPDATE emprunts e
            SET tontine_id=m.tontine_id
            FROM members m
            WHERE e.membre_id=m.id AND e.tontine_id IS NULL
        """)
        c.execute("""
            UPDATE tours t
            SET tontine_id=m.tontine_id
            FROM members m
            WHERE t.membre_id=m.id AND t.tontine_id IS NULL
        """)
        c.execute(
            "UPDATE fonds SET tontine_id=%s WHERE tontine_id IS NULL",
            (default_tid,)
        )
        c.execute(
            "UPDATE journal SET tontine_id=%s WHERE tontine_id IS NULL",
            (default_tid,)
        )

def audit(tid,action,details=""):
    with db() as c:c.execute("INSERT INTO journal(tontine_id,date,action,details) VALUES(?,?,?,?)",(tid,now(),action,details))
def tontines():
    with db() as c:
        rows = c.execute("SELECT * FROM tontines ORDER BY nom").fetchall()
    return [dict(r) for r in rows]
def T(tid):
    with db() as c:return dict(c.execute("SELECT * FROM tontines WHERE id=?",(tid,)).fetchone())
def sync_periods(tid):
    """
    Génère les échéances uniquement pour la tontine sélectionnée.
    Les montants sont copiés depuis la fiche du membre au moment
    de la création de la période, afin de préserver l'historique.
    """
    with db() as c:
        t = c.execute(
            "SELECT * FROM tontines WHERE id=?",
            (tid,)
        ).fetchone()

        if not t:
            return

        ms = c.execute(
            """
            SELECT *
            FROM members
            WHERE tontine_id=?
              AND active=1
            ORDER BY nom,prenom
            """,
            (tid,)
        ).fetchall()

        start = date.fromisoformat(t["date_debut"])
        end = date.fromisoformat(t["date_fin"])

        for m in ms:
            d = start

            if m["date_debut"]:
                try:
                    d = max(d, date.fromisoformat(m["date_debut"]))
                except (TypeError, ValueError):
                    pass

            last = end

            if m["date_fin"]:
                try:
                    last = min(last, date.fromisoformat(m["date_fin"]))
                except (TypeError, ValueError):
                    pass

            while d <= last:
                if m["periodicite"] == "Mensuelle":
                    periode = d.strftime("%Y-%m")
                    nxt = d + timedelta(days=32)
                    nxt = nxt.replace(day=1)
                else:
                    periode = d.strftime("%Y-W%W")
                    nxt = d + timedelta(days=7)

                c.execute(
                    """
                    INSERT INTO paiements(
                        tontine_id,
                        membre_id,
                        periode,
                        echeance,
                        cotisation_due,
                        cotisation_payee,
                        solidarite_due,
                        solidarite_payee,
                        statut
                    )
                    VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT (tontine_id,membre_id,periode) DO NOTHING
                    """,
                    (
                        tid,
                        m["id"],
                        periode,
                        d.isoformat(),
                        float(m["cotisation"] or 0),
                        0,
                        float(m["solidarite"] or 0),
                        0,
                        "En attente"
                    )
                )

                d = nxt

def refresh(tid):
    with db() as c:
        rows=c.execute("SELECT * FROM paiements WHERE tontine_id=?",(tid,)).fetchall()
        for r in rows:
            if r["cotisation_payee"]>=r["cotisation_due"] and r["solidarite_payee"]>=r["solidarite_due"]: s="Payé"
            elif date.today()>date.fromisoformat(r["echeance"]): s="En retard"
            elif r["cotisation_payee"] or r["solidarite_payee"]: s="Partiel"
            else:s="En attente"
            c.execute("UPDATE paiements SET statut=? WHERE id=?",(s,r["id"]))
        rows=c.execute("""SELECT e.id,e.total,COALESCE(SUM(r.montant),0) rem,e.date_limite
        FROM emprunts e LEFT JOIN remboursements r ON r.emprunt_id=e.id
        WHERE e.tontine_id=? GROUP BY e.id""",(tid,)).fetchall()
        for r in rows:
            s="Remboursé" if r["rem"]>=r["total"] else ("En retard" if date.today()>date.fromisoformat(r["date_limite"]) else "En cours")
            c.execute("UPDATE emprunts SET statut=? WHERE id=?",(s,r["id"]))
def finance(mid,tid):
    """Situation financière d'un membre basée sur les versements réels.

    Les cotisations ne sont plus considérées comme des échéances fixes.
    Les champs cd/cp et sd/sp sont conservés pour compatibilité avec
    les anciens écrans, mais les montants réellement versés proviennent
    de la table encaissements.
    """
    with db() as c:
        p=c.execute(
            """SELECT COALESCE(SUM(epargne),0) ep,
                      COALESCE(SUM(solidarite),0) sol,
                      COALESCE(SUM(amende),0) am
               FROM encaissements WHERE membre_id=? AND tontine_id=?""",
            (mid,tid)
        ).fetchone()
        es=c.execute(
            """SELECT e.*,COALESCE((SELECT SUM(montant) FROM remboursements WHERE emprunt_id=e.id),0) rem
               FROM emprunts e WHERE e.membre_id=? AND e.tontine_id=?""",
            (mid,tid)
        ).fetchall()
        tr=c.execute(
            "SELECT COALESCE(SUM(montant),0) x FROM tours WHERE membre_id=? AND tontine_id=? AND statut='Payé'",
            (mid,tid)
        ).fetchone()["x"]
    reste_em=sum(max(0,float(e["total"] or 0)-float(e["rem"] or 0)) for e in es)
    ep=float(p["ep"] or 0); sol=float(p["sol"] or 0)
    return {"cd":ep,"cp":ep,"sd":sol,"sp":sol,"rc":0,"rs":0,
            "em":sum(float(e["montant"] or 0) for e in es),
            "interets":sum(float(e["interet"] or 0) for e in es),
            "rem":sum(float(e["rem"] or 0) for e in es),
            "reste_em":reste_em,"tours":float(tr or 0),"amendes":float(p["am"] or 0)}

def blocked(mid,tid):
    f=finance(mid,tid);return f["reste_em"]>0

def docs_page(tid):
    st.title("📊 6 — Documents Excel / TXT")
    st.caption("Les documents sont exportés en Excel, CSV ou TXT. Aucun document n'est utilisé.")

    with db() as c:
        members = c.execute(
            "SELECT * FROM members WHERE tontine_id=? ORDER BY nom,prenom", (tid,)
        ).fetchall()
    if not members:
        st.info("Aucun membre.")
        return

    m = st.selectbox(
        "Membre",
        members,
        format_func=lambda x: f"{x['prenom']} {x['nom']} — {x['code']}"
    )
    df = read_df(
        """SELECT date, epargne AS Epargne, solidarite AS Solidarite,
                  amende AS Amende, observation AS Observation
           FROM encaissements
           WHERE tontine_id=? AND membre_id=?
           ORDER BY date DESC""",
        params=(tid, m["id"])
    )

    st.dataframe(df, use_container_width=True, hide_index=True)

    # Excel
    excel = BytesIO()
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Encaissements")
        pd.DataFrame([dict(m)]).to_excel(writer, index=False, sheet_name="Membre")
    st.download_button(
        "📥 Télécharger Excel",
        excel.getvalue(),
        f"{m['code']}_tontine.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    # CSV
    st.download_button(
        "📥 Télécharger CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        f"{m['code']}_encaissements.csv",
        "text/csv",
        use_container_width=True
    )

    # TXT
    txt = df.to_csv(index=False, sep="\t")
    st.download_button(
        "📥 Télécharger TXT",
        txt.encode("utf-8"),
        f"{m['code']}_encaissements.txt",
        "text/plain",
        use_container_width=True
    )

def reports_page(tid):
    st.title("📊 7 — Rapports")
    week = active_week(tid)
    default_start = date.fromisoformat(week["debut"]) if week else date.today()-timedelta(days=date.today().weekday())
    default_end = date.fromisoformat(week["fin"]) if week else default_start+timedelta(days=6)
    a,b = st.columns(2)
    debut = a.date_input("Début du rapport", default_start, key="report_debut")
    fin = b.date_input("Fin du rapport", default_end, key="report_fin")
    if debut > fin:
        st.error("La date de début doit être antérieure ou égale à la date de fin.")
        return

    with db() as c:
        df = read_df(
            """SELECT m.code AS Code, m.nom || ' ' || m.prenom AS Membre,
                      COALESCE(SUM(e.epargne),0) AS Epargne,
                      COALESCE(SUM(e.solidarite),0) AS Solidarite,
                      COALESCE(SUM(e.amende),0) AS Amende,
                      COALESCE(SUM(e.epargne+e.solidarite+e.amende),0) AS Total
               FROM members m LEFT JOIN encaissements e
                 ON e.membre_id=m.id AND e.tontine_id=? AND e.date::date BETWEEN date(?) AND date(?)
               WHERE m.tontine_id=? AND m.active=1
               GROUP BY m.id,m.code,m.nom,m.prenom ORDER BY m.nom,m.prenom""",
            params=(tid,debut.isoformat(),fin.isoformat(),tid)
        )
    for col in ["Epargne","Solidarite","Amende","Total"]:
        df[col] = df[col].apply(money)
    st.dataframe(df.rename(columns={"Epargne":"Épargne / cotisation","Solidarite":"Solidarité"}),use_container_width=True,hide_index=True)
    st.download_button("📥 Exporter CSV",df.to_csv(index=False).encode("utf-8-sig"),"rapport_tontine.csv","text/csv")

    # Excel
    export_df = df.copy()
    excel = BytesIO()
    with pd.ExcelWriter(excel, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Rapport")
    st.download_button(
        "📥 Télécharger le rapport Excel",
        excel.getvalue(),
        f"rapport_tontine_{debut.isoformat()}_{fin.isoformat()}.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

    st.download_button(
        "📥 Télécharger le rapport TXT",
        export_df.to_csv(index=False, sep="\t").encode("utf-8"),
        f"rapport_tontine_{debut.isoformat()}_{fin.isoformat()}.txt",
        "text/plain",
        use_container_width=True
    )


def guided_visits_page(tid):
    st.title("🧭 Visites guidées")
    st.info("Espace pratique du gérant : utilisez les boutons ci-dessous pour suivre le fonctionnement de la tontine sans accéder aux paramètres d'administration.")
    tabs = st.tabs(["👥 Membres", "💳 Cotisations", "💰 Emprunts", "🏦 Fonds", "📊 Documents", "📊 Rapports"])
    with tabs[0]:
        st.markdown("**Membres :** ajoutez les personnes et consultez leur tableau. Les montants indicatifs ne bloquent jamais les versements réels.")
    with tabs[1]:
        st.markdown("**Cotisations :** choisissez une personne et saisissez librement l'épargne, la solidarité et l'amende pour chaque date.")
    with tabs[2]:
        st.markdown("**Emprunts :** enregistrez la somme empruntée, l'échéance et chaque remboursement daté. Le reste est automatique.")
    with tabs[3]:
        st.markdown("**Fonds :** consultez les entrées et sorties de caisse de la tontine.")
    with tabs[4]:
        st.markdown("**Documents :** exportez les fiches individuelles en Excel, CSV ou TXT.")
    with tabs[5]:
        st.markdown("**Rapports :** consultez les synthèses et exportez le rapport en Excel ou TXT.")

def gerants_page():
    if not require_admin(): return
    st.title("👤 Gestion des gérants")
    st.info("Seul l'administrateur général peut créer, modifier ou affecter un gérant à une tontine.")
    ts=tontines()
    if not ts:
        st.warning("Créez d'abord une tontine.")
        return
    with st.form("create_manager"):
        a,b=st.columns(2)
        username=a.text_input("Identifiant du gérant *")
        password=b.text_input("Mot de passe *",type="password")
        t=st.selectbox("Tontine affectée",ts,format_func=lambda x:f"{x['nom']} — {x['code']}")
        if st.form_submit_button("➕ Créer le compte gérant",use_container_width=True):
            if not username.strip() or not password:
                st.error("Identifiant et mot de passe obligatoires.")
            else:
                salt,h=password_hash(password)
                try:
                    with db() as c:
                        c.execute("INSERT INTO admins(username,salt,hash,role,tontine_id) VALUES(?,?,?,?,?)",(username.strip(),salt,h,"gerant",t["id"]))
                    st.success(f"Compte gérant créé pour la tontine : {t['nom']}.")
                    st.rerun()
                except pgdb.IntegrityError:
                    st.error("Cet identifiant existe déjà.")
    with db() as c:
        df=read_df("""SELECT a.id,a.username,a.role,a.tontine_id,COALESCE(t.nom,'') AS tontine
                               FROM admins a LEFT JOIN tontines t ON t.id=a.tontine_id
                               WHERE a.role='gerant' ORDER BY a.username""")
    st.subheader("📋 Gérants existants")
    st.dataframe(df.rename(columns={"username":"Identifiant","tontine":"Tontine","role":"Rôle"})[["Identifiant","Tontine","Rôle"]],use_container_width=True,hide_index=True)

def params_page(tid):
    t=T(tid);st.title("⚙️ 8 — Paramètres de la tontine")
    with st.form("tp"):
        nom=st.text_input("Nom",t["nom"]);code=st.text_input("Code",t["code"]);desc=st.text_area("Description",t["description"] or "")
        a,b=st.columns(2);debut=a.date_input("Début",date.fromisoformat(t["date_debut"]));fin=b.date_input("Fin",date.fromisoformat(t["date_fin"]))
        lock=st.checkbox("🔒 Verrouiller la configuration",bool(t["verrouillee"]))
        if st.form_submit_button("💾 Enregistrer"):
            with db() as c:c.execute("UPDATE tontines SET nom=?,code=?,description=?,date_debut=?,date_fin=?,verrouillee=? WHERE id=?",(nom,code,desc,debut.isoformat(),fin.isoformat(),int(lock),tid))
            audit(tid,"Paramètres modifiés");st.rerun()
    st.info("Les cotisations ne sont pas fixes : le gestionnaire les saisit librement, personne par personne et à chaque date. Le montant habituel du membre est seulement indicatif.")

def whitelist_page():
    if not require_admin(): return
    st.title("🛡️ Liste blanche — accès par tontine")
    st.info("Créez ici les identifiants propres à chaque tontine. Ces comptes n'utilisent jamais les identifiants de l'administrateur général.")
    ts=tontines()
    if not ts:
        st.warning("Créez d'abord une tontine."); return
    ids=[int(t["id"]) for t in ts]
    labels={int(t["id"]):f'{t["nom"]} — {t["code"]}' for t in ts}
    with st.form("whitelist_access"):
        tid=st.selectbox("Tontine concernée",ids,format_func=lambda x:labels[int(x)])
        a,b=st.columns(2); username=a.text_input("Identifiant de connexion *"); password=b.text_input("Mot de passe *",type="password")
        label=st.text_input("Nom de l'accès / administrateur de tontine *")
        infos=st.text_area("Informations sur la tontine")
        active=st.checkbox("Accès actif",value=True)
        if st.form_submit_button("➕ Créer l'accès de la tontine",use_container_width=True):
            if not username.strip() or not password or not label.strip(): st.error("Identifiant, mot de passe et nom obligatoires.")
            else:
                salt,h=password_hash(password)
                try:
                    with db() as c:
                        exists=c.execute("SELECT id FROM whitelist WHERE username=?",(username.strip(),)).fetchone()
                        if exists: raise pgdb.IntegrityError
                        c.execute("INSERT INTO whitelist(code,label,description,active,tontine_id,username,salt,hash,nom_tontine,infos_tontine) VALUES(?,?,?,?,?,?,?,?,?,?)",(f'ACC-{username.strip().upper()}',label.strip(),infos,int(active),tid,username.strip(),salt,h,labels[tid],infos))
                    st.success("Accès de la tontine créé. La personne peut maintenant se connecter avec cet identifiant et ce mot de passe."); st.rerun()
                except pgdb.IntegrityError: st.error("Cet identifiant existe déjà.")
    with db() as c:
        df=read_df("SELECT w.id,w.username AS Identifiant,w.label AS Accès,w.nom_tontine AS Tontine,w.infos_tontine AS Informations,w.active AS Actif FROM whitelist w ORDER BY w.id DESC")
    if not df.empty:
        df["Actif"]=df["Actif"].map({1:"Oui",0:"Non"})
    st.subheader("📋 Accès créés")
    st.dataframe(df,use_container_width=True,hide_index=True)

def history_page(tid):
    st.title("📜 10 — Historique administrateur")
    with db() as c:df=read_df("SELECT date,action,details FROM journal WHERE tontine_id=? ORDER BY id DESC", params=(tid,))
    st.dataframe(df,use_container_width=True,hide_index=True)

def guide_page():
    st.title("❓ 11 — Guide d'utilisation")
    for h,p in [
        ("1. Définir une tontine","Seul l'administrateur/gestionnaire connecté crée et paramètre les tontines. Chaque tontine est indépendante."),
        ("2. Définir la semaine","Dans l'accueil, le gestionnaire choisit la date de début, la date de fin et le libellé de la semaine."),
        ("3. Suivre les membres","Le tableau de la semaine regroupe Nom, Prénom, Solidarité, Épargne, Amende et Observation."),
        ("4. Saisir les opérations","Chaque opération peut être enregistrée par date et par membre. Les totaux de la semaine sont calculés automatiquement."),
        ("5. Suivre la caisse","Le tableau quotidien calcule le solde cumulatif en tenant compte des encaissements, remboursements, emprunts et mouvements de fonds."),
        ("6. Gérer les emprunts","Pour chaque emprunt, l'application conserve la somme empruntée, le total à rendre, les remboursements datés, l'échéance et le reste à rendre."),
        ("7. Administration","La liste blanche, les profils, les paramètres, la définition des tontines et l'historique sont réservés à l'administrateur.")]:
        st.markdown(f"### {h}\n{p}")

def main():
    if not SUPABASE_DB_URL:
        st.error('Connexion Supabase non configurée.')
        st.code('SUPABASE_DB_URL = "postgresql://postgres:VOTRE_MOT_DE_PASSE@VOTRE_HOST:5432/postgres"')
        st.stop()
    init_db()
    if not st.session_state.get("auth"):
        login()
        return

    ts=tontines()
    if not ts:
        if is_admin():
            create_tontine()
        else:
            st.error("Aucune tontine n'est encore disponible. Contactez l'administrateur général.")
        return

    if not selector():
        return
    st.markdown("---")
    a,b=st.columns([1,5])
    if a.button("🚪 Déconnexion"):
        st.session_state.clear(); st.rerun()

    page=nav(); tid=st.session_state.tid
    if page=="🏠 Accueil":dashboard(tid)
    elif page=="⚙️ Administration":administration_page()
    elif page=="👥 Membres":members_page(tid)
    elif page=="💳 Cotisations":payments_page(tid)
    elif page=="💰 Emprunts":loans_page(tid)
    elif page=="🧭 Visites guidées":guided_visits_page(tid)
    elif page=="🎯 Tours":turns_page(tid)
    elif page=="🏦 Fonds":fund_page(tid)
    elif page=="📊 Documents Excel / TXT":docs_page(tid)
    elif page=="📊 Rapports":reports_page(tid)
    elif page=="❓ Guide":guide_page()

if __name__=="__main__":main()
