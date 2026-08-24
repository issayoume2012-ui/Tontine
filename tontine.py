# ============================================================
# DEPENDANCES : uniquement celles de requirements.txt
# ============================================================
import psycopg2
from psycopg2.extras import RealDictCursor
from supabase import create_client, Client
from fpdf import FPDF

# Compatibilité PDF avec FPDF à la place de ReportLab.
# Les fonctions existantes de l'application utilisent une petite API
# de type SimpleDocTemplate/Paragraph/Table ; ces classes l'implémentent
# avec FPDF afin de ne nécessiter aucune autre dépendance.
class _PDFStyle:
    def __init__(self, name):
        self.name = name

class _PDFStyles:
    def __getitem__(self, name):
        return _PDFStyle(name)

class Paragraph:
    def __init__(self, text, style=None):
        self.text = str(text)
        self.style = getattr(style, "name", "Normal") if style else "Normal"

class Spacer:
    def __init__(self, w=1, h=8):
        self.h = float(h)

class TableStyle:
    def __init__(self, commands=None):
        self.commands = commands or []

class Table:
    def __init__(self, data, repeatRows=0, style=None):
        self.data = data or []
        self.repeatRows = repeatRows
        self.style = style

class _PDFDocument:
    def __init__(self, buffer, pagesize=None, rightMargin=28, leftMargin=28,
                 topMargin=30, bottomMargin=30):
        self.buffer = buffer
        self.margins = (leftMargin, rightMargin, topMargin, bottomMargin)

    @staticmethod
    def _clean(value):
        if value is None:
            return ""
        text = str(value)
        # fpdf 1.x utilise latin-1. Les caractères non représentables
        # sont remplacés plutôt que de faire planter la génération.
        return text.encode("latin-1", "replace").decode("latin-1")

    def _table(self, pdf, table):
        data = [[self._clean(c) for c in row] for row in table.data]
        if not data:
            return
        ncols = max(len(r) for r in data)
        widths = [0] * ncols
        for row in data:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], pdf.get_string_width(cell) + 5)
        available = pdf.w - pdf.l_margin - pdf.r_margin
        total = sum(widths) or available
        widths = [available * w / total for w in widths]

        row_h = 6
        for ridx, row in enumerate(data):
            if pdf.get_y() + row_h > pdf.h - pdf.b_margin:
                pdf.add_page()
            is_header = ridx < table.repeatRows
            x0 = pdf.get_x()
            y0 = pdf.get_y()
            for i in range(ncols):
                cell = row[i] if i < len(row) else ""
                w = widths[i]
                pdf.set_fill_color(23, 54, 93) if is_header else pdf.set_fill_color(255,255,255)
                pdf.set_text_color(255,255,255) if is_header else pdf.set_text_color(0,0,0)
                pdf.rect(x0, y0, w, row_h, style="FD")
                pdf.set_xy(x0 + 1, y0 + 1)
                pdf.cell(w - 2, row_h - 2, cell[:80], border=0, align="L")
                x0 += w
            pdf.set_xy(pdf.l_margin, y0 + row_h)
        pdf.set_text_color(0,0,0)

    def build(self, story):
        pdf = FPDF("P", "mm", "A4")
        left, right, top, bottom = self.margins
        pdf.set_margins(left, top, right)
        pdf.set_auto_page_break(True, margin=bottom)
        pdf.add_page()
        for item in story:
            if isinstance(item, Spacer):
                pdf.ln(max(1, item.h / 2))
            elif isinstance(item, Paragraph):
                if item.style == "Title":
                    pdf.set_font("Arial", "B", 18)
                    pdf.ln(2)
                elif item.style == "Heading2":
                    pdf.set_font("Arial", "B", 13)
                    pdf.ln(2)
                else:
                    pdf.set_font("Arial", "", 9)
                text = self._clean(item.text)
                pdf.multi_cell(0, 6, text)
            elif isinstance(item, Table):
                pdf.set_font("Arial", "", 7)
                self._table(pdf, item)
                pdf.ln(2)
        output = pdf.output(dest="S")
        if isinstance(output, str):
            output = output.encode("latin-1", "replace")
        self.buffer.write(output)

SimpleDocTemplate = _PDFDocument

def getSampleStyleSheet():
    return _PDFStyles()

class _Colors:
    grey = (128,128,128)
    white = (255,255,255)
    @staticmethod
    def HexColor(value):
        value = value.lstrip("#")
        return tuple(int(value[i:i+2], 16) for i in (0,2,4))
colors = _Colors()
A4 = "A4"

# ============================================================
# BASE DE DONNEES DISTANTE SUPABASE / POSTGRESQL
# ============================================================
try:
    _secret_password = st.secrets["SUPABASE_DB_PASSWORD"]
except Exception:
    _secret_password = None

SUPABASE_DB_PASSWORD = (
    _secret_password
    or os.getenv("SUPABASE_DB_PASSWORD")
    or "EoalvKG2mAx1AbC6"
)

SUPABASE_HOST = os.getenv(
    "SUPABASE_DB_HOST",
    "db.rrpmbnxmmsoryzyadhaj.supabase.co"
)
SUPABASE_PORT = int(os.getenv("SUPABASE_DB_PORT", "5432"))
SUPABASE_DATABASE = os.getenv("SUPABASE_DB_NAME", "postgres")
SUPABASE_USER = os.getenv("SUPABASE_DB_USER", "postgres")

DB_URL = os.getenv(
    "SUPABASE_DB_URL",
    f"postgresql://{SUPABASE_USER}:{SUPABASE_DB_PASSWORD}"
    f"@{SUPABASE_HOST}:{SUPABASE_PORT}/{SUPABASE_DATABASE}"
)

st.set_page_config(page_title="Tontine Manager",page_icon="💰",layout="wide")

# ============================================================
# SDK SUPABASE (optionnel pour les fonctions API)
# ============================================================
SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://rrpmbnxmmsoryzyadhaj.supabase.co"
)
try:
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY", ""))
except Exception:
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

_supabase_client = None

def get_supabase_client():
    global _supabase_client
    if _supabase_client is None and SUPABASE_KEY:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

def supabase_configured():
    return bool(SUPABASE_URL and SUPABASE_KEY)

class PGDictCursor:
    """Curseur compatible avec les accès row['colonne'] de l'application."""
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
    """Adaptateur PostgreSQL conservant c.execute()/fetchone()/fetchall()."""
    def __init__(self, connection):
        self.connection = connection
    def execute(self, sql, params=None):
        sql = sql.replace("?", "%s")
        cur = self.connection.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params or ())
        return cur
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
    conn = None
    try:
        conn = psycopg2.connect(
            host=SUPABASE_HOST,
            port=SUPABASE_PORT,
            dbname=SUPABASE_DATABASE,
            user=SUPABASE_USER,
            password=SUPABASE_DB_PASSWORD,
            sslmode="require",
            connect_timeout=15,
            application_name="Tontine Manager"
        )
        conn.autocommit = False
        c = PGConnection(conn)
        yield c
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()

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

def pdf_member(mid,tid,year=None,month=None):
    if not _require_reportlab():
        return None
    with db() as c:
        m=c.execute(
            """SELECT m.*,w.label profil FROM members m LEFT JOIN whitelist w ON w.id=m.profil_id
               WHERE m.id=? AND m.tontine_id=?""",(mid,tid)
        ).fetchone()
        f=finance(mid,tid)
        args=[tid,mid]
        date_filter=""
        if year:
            date_filter += " AND EXTRACT(YEAR FROM e.date::date)=%s"; args.append(str(year))
        if month:
            date_filter += " AND LPAD(EXTRACT(MONTH FROM e.date::date)::text,2,'0')=%s"; args.append(f"{month:02d}")
        enc=c.execute(
            f"""SELECT * FROM encaissements e WHERE e.tontine_id=? AND e.membre_id=?{date_filter} ORDER BY e.date::date""",
            args
        ).fetchall()
        loans=c.execute(
            """SELECT e.*,COALESCE((SELECT SUM(montant) FROM remboursements WHERE emprunt_id=e.id),0) rem
               FROM emprunts e WHERE membre_id=? AND tontine_id=? ORDER BY date_octroi""",(mid,tid)
        ).fetchall()
        tours=c.execute("SELECT * FROM tours WHERE membre_id=? AND tontine_id=? ORDER BY semaine",(mid,tid)).fetchall()
    b=BytesIO();doc=SimpleDocTemplate(b,pagesize=A4);s=getSampleStyleSheet()
    story=[Paragraph("TONTINE MANAGER",s["Title"]),Paragraph("FICHE INDIVIDUELLE",s["Heading2"]),
           Paragraph(f"{m['prenom']} {m['nom']} — {m['code']}",s["Normal"]),
           Paragraph(f"Téléphone : {m['telephone'] or '-'} | Profil : {m['profil'] or '-'}",s["Normal"]),Spacer(1,12)]
    story.append(Table([["Indicateur","Montant"],["Épargne / cotisations versées",money(f["cp"])],
                        ["Solidarité versée",money(f["sp"])],["Amendes versées",money(f["amendes"])],
                        ["Remboursements d'emprunts",money(f["rem"])],["Reste emprunts",money(f["reste_em"]) ]],
                       style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white)])))
    story += [Spacer(1,14),Paragraph("Historique des versements",s["Heading2"])]
    rows=[["Date","Épargne","Solidarité","Amende","Observation"]]+[[x["date"],money(x["epargne"]),money(x["solidarite"]),money(x["amende"]),x["observation"] or "-"] for x in enc]
    if len(rows)==1: rows.append(["-","-","-","-","Aucun versement"])
    story.append(Table(rows,repeatRows=1,style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey)])))
    story += [Spacer(1,12),Paragraph("Emprunts",s["Heading2"])]
    rows=[["Octroi","Capital","Intérêt","Remboursé","Reste","Statut"]]+[[e["date_octroi"],money(e["montant"]),money(e["interet"]),money(e["rem"]),money(float(e["total"] or 0)-float(e["rem"] or 0)),e["statut"]] for e in loans]
    if len(rows)==1: rows.append(["-","-","-","-","-","Aucun emprunt"])
    story.append(Table(rows,repeatRows=1,style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey)])))
    story += [Spacer(1,12),Paragraph("Tours",s["Heading2"])]
    rows=[["Semaine","Date","Montant","Statut"]]+[[x["semaine"],x["date"],money(x["montant"]),x["statut"]] for x in tours]
    if len(rows)==1: rows.append(["-","-","-","Aucun tour"])
    story.append(Table(rows,repeatRows=1,style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey)])))
    doc.build(story);return b.getvalue()

st.markdown("""<style>
#MainMenu,footer{visibility:hidden}.block-container{padding:1rem 2rem 3rem}
.top{background:linear-gradient(90deg,#102a43,#176b87,#0b8f70);color:white;padding:17px 22px;border-radius:18px;margin-bottom:12px}
.brand{font-size:28px;font-weight:800}.muted{opacity:.85}
.card{border:1px solid #dfe8ee;border-radius:16px;padding:16px;background:#fff}
.hero-img img{border-radius:22px;box-shadow:0 8px 28px rgba(0,0,0,.12)}
div[data-testid="stMetric"]{border:1px solid #dfe8ee;padding:12px;border-radius:14px}
</style>""",unsafe_allow_html=True)

def is_admin():
    return st.session_state.get("role") == "admin"

def is_manager():
    return st.session_state.get("role") == "gerant"

def require_admin():
    if not is_admin():
        st.error("🔒 Accès réservé à l'administrateur général.")
        return False
    return True

def login():
    st.markdown('<div class="top"><div class="brand">💰 Tontine Manager</div><div class="muted">Gestion multi-tontines</div></div>',unsafe_allow_html=True)
    with st.form("login"):
        u=st.text_input("Identifiant")
        p=st.text_input("Mot de passe",type="password")
        if st.form_submit_button("🔐 Se connecter",use_container_width=True):
            with db() as c:
                a=c.execute("SELECT * FROM admins WHERE username=?",(u.strip(),)).fetchone()
                w=c.execute("SELECT * FROM whitelist WHERE username=? AND active=1",(u.strip(),)).fetchone()
            if a and valid_password(p,a["salt"],a["hash"]):
                st.session_state.auth=True; st.session_state.role=a["role"] or "admin"
                st.session_state.user_id=a["id"]; st.session_state.username=a["username"]
                st.session_state.manager_tontine_id=a["tontine_id"]
                st.rerun()
            elif w and w["salt"] and w["hash"] and valid_password(p,w["salt"],w["hash"]):
                if not w["tontine_id"]:
                    st.error("Cet accès n'est associé à aucune tontine.")
                else:
                    st.session_state.auth=True; st.session_state.role="tontine_admin"
                    st.session_state.user_id=w["id"]; st.session_state.username=w["username"]
                    st.session_state.manager_tontine_id=w["tontine_id"]
                    st.rerun()
            else:
                st.error("Identifiants incorrects.")

def is_tontine_admin():
    return st.session_state.get("role") == "tontine_admin"

def require_tontine_access():
    if not (is_admin() or is_manager() or is_tontine_admin()):
        st.error("🔒 Accès réservé aux utilisateurs autorisés.")
        return False
    return True

def tontines_page():
    if not require_admin(): return
    st.title("🏢 Gestion des tontines")
    st.info("🔐 Cette rubrique est réservée à l'administrateur/gestionnaire connecté. Vous seul pouvez créer, définir et modifier les tontines.")
    st.subheader("➕ Définir une nouvelle tontine")
    create_tontine()

    ts = tontines()
    if ts:
        rows = [{"ID":t["id"],"Code":t["code"],"Nom":t["nom"],"Début":t["date_debut"],"Fin":t["date_fin"],"Active": "Oui" if t["active"] else "Non"} for t in ts]
        st.subheader("📋 Tontines disponibles")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def selector():
    ts=tontines()
    if is_manager() or is_tontine_admin():
        tid=st.session_state.get("manager_tontine_id")
        ts=[t for t in ts if t["id"]==tid]
        if not ts:
            st.error("Aucune tontine n'est affectée à ce compte gérant.")
            return False
        st.session_state.tid=ts[0]["id"]
        st.info(f"👤 Gérant connecté : {st.session_state.get('username','')} — Tontine : **{ts[0]['nom']}**")
        return True
    if not ts:
        st.title("🏢 Créer votre première tontine")
        st.info("Seul l’administrateur général peut définir la première tontine.")
        create_tontine()
        return False
    labels={f"{x['nom']} — {x['code']}":x["id"] for x in ts}
    cur=st.session_state.get("tid"); keys=list(labels); idx=next((i for i,k in enumerate(keys) if labels[k]==cur),0)
    pick=st.selectbox("🏢 Tontine active",keys,index=idx,label_visibility="collapsed")
    st.session_state.tid=labels[pick]
    return True

def create_tontine():
    with st.form("newt"):
        a,b=st.columns(2);nom=a.text_input("Nom *");code=b.text_input("Code unique *");desc=st.text_area("Description")
        a,b=st.columns(2);debut=a.date_input("Date de début",date.today());fin=b.date_input("Date de fin",date.today()+timedelta(days=364))
        if st.form_submit_button("🚀 Définir et créer la tontine"):
            if not nom or not code:st.error("Nom et code obligatoires.")
            else:
                try:
                    with db() as c:
                        tid = c.execute(
                            "INSERT INTO tontines(code,nom,description,date_debut,date_fin,created_at) VALUES(?,?,?,?,?,?) RETURNING id",
                            (code.upper(),nom,desc,debut.isoformat(),fin.isoformat(),now())
                        ).fetchone()["id"]
                    st.session_state.tid=tid
                    audit(tid,"Création tontine",nom)
                    st.rerun()
                except pgdb.IntegrityError:st.error("Code déjà existant.")

def nav():
    t=T(st.session_state.tid)
    role_label={"admin":"Administrateur général","tontine_admin":"Administrateur de tontine","gerant":"Gérant"}.get(st.session_state.get("role"),"Utilisateur")
    st.markdown(f'<div class="top"><div class="brand">💰 Tontine Manager</div><div class="muted">Tontine active : <b>{t["nom"]}</b> — {t["code"]} &nbsp; | &nbsp; {role_label}</div></div>',unsafe_allow_html=True)
    if is_admin():
        pages=["🏠 Accueil","⚙️ Administration","👥 Membres","💳 Cotisations","💰 Emprunts","🧭 Visites guidées","🎯 Tours","🏦 Fonds","📄 Documents & PDF","📊 Rapports","❓ Guide"]
    else:
        pages=["🏠 Accueil","👥 Membres","💳 Cotisations","💰 Emprunts","🧭 Visites guidées","🏦 Fonds","📄 Documents & PDF","📊 Rapports","❓ Guide"]
    return st.radio("Menu",pages,horizontal=True,label_visibility="collapsed")

def administration_page():
    if not is_admin():
        st.error("🔒 Administration réservée à l'administrateur général.")
        return
    st.title("⚙️ Administration")
    tabs=st.tabs(["🏢 Tontines","🛡️ Listes blanches","👤 Gérants"])
    with tabs[0]: tontines_page()
    with tabs[1]: whitelist_page()
    with tabs[2]: gerants_page()

def image_accueil():
    """Affiche l'image d'accueil TT.jpg si elle est présente à côté du script."""
    image_path = Path(__file__).with_name("TT.jpg")
    if image_path.exists():
        st.markdown('<div class="hero-img">', unsafe_allow_html=True)
        st.image(str(image_path), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)


def active_week(tid):
    with db() as c:
        r = c.execute(
            "SELECT * FROM semaines_gestion WHERE tontine_id=? AND active=1 ORDER BY id DESC LIMIT 1",
            (tid,)
        ).fetchone()
    return r


def set_active_week(tid, debut, fin, libelle=""):
    if debut > fin:
        raise ValueError("La date de début doit être antérieure ou égale à la date de fin.")
    with db() as c:
        c.execute("UPDATE semaines_gestion SET active=0 WHERE tontine_id=?", (tid,))
        c.execute(
            "INSERT INTO semaines_gestion(tontine_id,debut,fin,libelle,active,created_at) VALUES(?,?,?,?,1,?)",
            (tid, debut.isoformat(), fin.isoformat(), libelle.strip() or f"Semaine du {debut.strftime('%d/%m/%Y')} au {fin.strftime('%d/%m/%Y')}", now())
        )


def weekly_member_table(tid, debut, fin):
    with db() as c:
        df = read_df(
            """
            SELECT m.id, m.nom, m.prenom,
                   COALESCE(SUM(e.solidarite),0) AS solidarite,
                   COALESCE(SUM(e.epargne),0) AS epargne,
                   COALESCE(SUM(e.amende),0) AS amende,
                   COALESCE(MAX(e.observation),'') AS observation
            FROM members m
            LEFT JOIN encaissements e
              ON e.membre_id=m.id AND e.tontine_id=?
             AND e.date::date BETWEEN date(?) AND date(?)
            WHERE m.tontine_id=? AND m.active=1
            GROUP BY m.id,m.nom,m.prenom
            ORDER BY m.nom,m.prenom
            """,
            params=(tid, debut.isoformat(), fin.isoformat(), tid)
        )
    if not df.empty:
        df["solidarite"] = df["solidarite"].astype(float)
        df["epargne"] = df["epargne"].astype(float)
        df["amende"] = df["amende"].astype(float)
    return df


def weekly_daily_summary(tid, debut, fin):
    days = []
    current = debut
    while current <= fin:
        days.append(current)
        current += timedelta(days=1)

    rows = []
    with db() as c:
        # Base de caisse avant le début de la période :
        # entrées = solidarité + épargne + amendes + remboursements
        # sorties = décaissements d'emprunts + sorties/aides des fonds.
        before = c.execute(
            """
            SELECT
              COALESCE((SELECT SUM(solidarite) FROM encaissements WHERE tontine_id=? AND date < ?),0) +
              COALESCE((SELECT SUM(epargne) FROM encaissements WHERE tontine_id=? AND date < ?),0) +
              COALESCE((SELECT SUM(amende) FROM encaissements WHERE tontine_id=? AND date < ?),0) +
              COALESCE((SELECT SUM(r.montant) FROM remboursements r JOIN emprunts e ON e.id=r.emprunt_id
                        WHERE e.tontine_id=? AND r.date < ?),0) -
              COALESCE((SELECT SUM(e.montant) FROM emprunts e WHERE e.tontine_id=? AND e.date_octroi < ?),0) -
              COALESCE((SELECT SUM(f.montant) FROM fonds f WHERE f.tontine_id=? AND f.date < ?
                        AND f.type IN ('Sortie','Aide')),0) +
              COALESCE((SELECT SUM(f.montant) FROM fonds f WHERE f.tontine_id=? AND f.date < ?
                        AND f.type IN ('Apport','Intérêt')),0) AS solde
            """,
            (tid,debut.isoformat(),tid,debut.isoformat(),tid,debut.isoformat(),tid,debut.isoformat(),
             tid,debut.isoformat(),tid,debut.isoformat(),tid,debut.isoformat())
        ).fetchone()["solde"] or 0
        solde = float(before)

        for d in days:
            ds = d.isoformat()
            e = c.execute(
                "SELECT COALESCE(SUM(solidarite),0) s, COALESCE(SUM(epargne),0) ep, COALESCE(SUM(amende),0) a FROM encaissements WHERE tontine_id=? AND date=?",
                (tid, ds)
            ).fetchone()
            rem = c.execute(
                "SELECT COALESCE(SUM(r.montant),0) x FROM remboursements r JOIN emprunts e ON e.id=r.emprunt_id WHERE e.tontine_id=? AND r.date=?",
                (tid, ds)
            ).fetchone()["x"] or 0
            loans = c.execute(
                "SELECT COALESCE(SUM(montant),0) x FROM emprunts WHERE tontine_id=? AND date_octroi=?",
                (tid, ds)
            ).fetchone()["x"] or 0
            fund_in = c.execute(
                "SELECT COALESCE(SUM(montant),0) x FROM fonds WHERE tontine_id=? AND date=? AND type IN ('Apport','Intérêt')",
                (tid, ds)
            ).fetchone()["x"] or 0
            fund_out = c.execute(
                "SELECT COALESCE(SUM(montant),0) x FROM fonds WHERE tontine_id=? AND date=? AND type IN ('Sortie','Aide')",
                (tid, ds)
            ).fetchone()["x"] or 0
            s = float(e["s"] or 0)
            ep = float(e["ep"] or 0)
            a = float(e["a"] or 0)
            solde += s + ep + a + float(rem) + float(fund_in) - float(loans) - float(fund_out)
            rows.append({
                "Date": d.strftime("%d/%m/%Y"),
                "Solidarité du jour": s,
                "Épargne du jour": ep,
                "Amende": a,
                "Solde de caisse": solde
            })
    return pd.DataFrame(rows)


def register_daily_entry(tid):
    with db() as c:
        ms = dict_rows(c.execute("SELECT * FROM members WHERE tontine_id=? AND active=1 ORDER BY nom,prenom", (tid,)).fetchall())
    if not ms:
        st.info("Ajoutez d'abord des membres à cette tontine.")
        return
    week = active_week(tid)
    if not week:
        st.warning("Définissez d'abord une semaine de gestion dans l'accueil.")
        return
    debut = date.fromisoformat(week["debut"]); fin = date.fromisoformat(week["fin"])
    with st.expander("➕ Enregistrer une opération du jour", expanded=False):
        with st.form("daily_entry"):
            member = st.selectbox("Membre", ms, format_func=lambda x: f"{x['nom']} {x['prenom']} — {x['code']}")
            d = st.date_input("Date", min_value=debut, max_value=fin, value=min(max(date.today(), debut), fin))
            a,b,c = st.columns(3)
            sol = a.number_input("Solidarité", min_value=0.0, step=100.0)
            ep = b.number_input("Épargne", min_value=0.0, step=500.0)
            am = c.number_input("Amende", min_value=0.0, step=100.0)
            obs = st.text_input("Observation")
            if st.form_submit_button("💾 Enregistrer l'opération", use_container_width=True):
                if sol == 0 and ep == 0 and am == 0 and not obs.strip():
                    st.warning("Saisissez au moins un montant ou une observation.")
                else:
                    with db() as c:
                        c.execute(
                            "INSERT INTO encaissements(tontine_id,membre_id,date,solidarite,epargne,amende,observation) VALUES(?,?,?,?,?,?,?)",
                            (tid, member["id"], d.isoformat(), sol, ep, am, obs.strip())
                        )
                    audit(tid, "Opération journalière", f"{member['code']} — {d.isoformat()}")
                    st.success("Opération enregistrée.")
                    st.rerun()


def home_week_section(tid):
    st.subheader("📅 Semaine de gestion définie par le gestionnaire")
    current = active_week(tid)
    default_start = date.fromisoformat(current["debut"]) if current else date.today() - timedelta(days=date.today().weekday())
    default_end = date.fromisoformat(current["fin"]) if current else default_start + timedelta(days=6)
    with st.form("week_definition"):
        a,b,c = st.columns([1,1,1.5])
        debut = a.date_input("Début de la semaine", default_start)
        fin = b.date_input("Fin de la semaine", default_end)
        libelle = c.text_input("Libellé", current["libelle"] if current else "Semaine de gestion")
        if st.form_submit_button("📌 Définir cette semaine", use_container_width=True):
            if debut > fin:
                st.error("La date de début doit être antérieure ou égale à la date de fin.")
            else:
                set_active_week(tid, debut, fin, libelle)
                audit(tid, "Semaine de gestion définie", f"{debut.isoformat()} → {fin.isoformat()}")
                st.success("Semaine de gestion enregistrée.")
                st.rerun()

    week = active_week(tid)
    if not week:
        return
    debut = date.fromisoformat(week["debut"]); fin = date.fromisoformat(week["fin"])
    st.caption(f"Période active : **{debut.strftime('%d/%m/%Y')} → {fin.strftime('%d/%m/%Y')}** — {week['libelle'] or ''}")

    st.subheader("👥 Situation des membres de la tontine")
    register_daily_entry(tid)
    df = weekly_member_table(tid, debut, fin)
    if df.empty:
        st.info("Aucun membre dans cette tontine.")
    else:
        display = df.rename(columns={
            "nom":"Nom", "prenom":"Prénom", "solidarite":"Solidarité",
            "epargne":"Épargner", "amende":"Amende", "observation":"Observation"
        })[["Nom","Prénom","Solidarité","Épargner","Amende","Observation"]].copy()
        for col in ["Solidarité","Épargner","Amende"]:
            display[col] = display[col].apply(money)
        st.dataframe(display, use_container_width=True, hide_index=True)

        totals = df[["solidarite","epargne","amende"]].sum()
        a,b,c = st.columns(3)
        a.metric("Solidarité de la période", money(totals["solidarite"]))
        b.metric("Épargne de la période", money(totals["epargne"]))
        c.metric("Amendes de la période", money(totals["amende"]))

    st.subheader("📊 Synthèse de la semaine")
    summary = weekly_daily_summary(tid, debut, fin)
    if summary.empty:
        st.info("Aucune journée dans la période sélectionnée.")
    else:
        for col in ["Solidarité du jour","Épargne du jour","Amende","Solde de caisse"]:
            summary[col] = summary[col].apply(money)
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.caption("Le solde de caisse est cumulatif : solidarité + épargne + amendes + remboursements + apports/intérêts, moins les emprunts accordés et les sorties/aides.")

def dashboard(tid):
    refresh(tid)
    t = T(tid)
    image_accueil()
    st.title(f"🏠 Accueil — {t['nom']}")
    st.markdown(
        "**Bienvenue dans la gestion de votre tontine.** Cette page est le point de départ : "
        "le gestionnaire définit la tontine, choisit la semaine de gestion et suit immédiatement "
        "la solidarité, l'épargne, les amendes et la caisse."
    )

    with db() as c:
        n = c.execute("SELECT COUNT(*) n FROM members WHERE tontine_id=? AND active=1", (tid,)).fetchone()["n"]
        sol = c.execute("SELECT COALESCE(SUM(solidarite),0) x FROM encaissements WHERE tontine_id=?", (tid,)).fetchone()["x"]
        ep = c.execute("SELECT COALESCE(SUM(epargne),0) x FROM encaissements WHERE tontine_id=?", (tid,)).fetchone()["x"]
        am = c.execute("SELECT COALESCE(SUM(amende),0) x FROM encaissements WHERE tontine_id=?", (tid,)).fetchone()["x"]
        rem = c.execute("SELECT COALESCE(SUM(r.montant),0) x FROM remboursements r JOIN emprunts e ON e.id=r.emprunt_id WHERE e.tontine_id=?", (tid,)).fetchone()["x"]
        loans = c.execute("SELECT COALESCE(SUM(montant),0) x FROM emprunts WHERE tontine_id=?", (tid,)).fetchone()["x"]

    a,b,c,d,e = st.columns(5)
    a.metric("👥 Membres", n)
    b.metric("🤝 Solidarité", money(sol))
    c.metric("💰 Épargne", money(ep))
    d.metric("⚠️ Amendes", money(am))
    e.metric("💳 Remboursements", money(rem))

    st.info("🔐 La création et la définition des tontines sont réservées à l'administrateur/gestionnaire connecté. Chaque tontine possède ses propres membres, opérations, emprunts et caisse.")
    home_week_section(tid)

def members_page(tid):
    st.title("👥 Membres de la tontine")
    with db() as c:
        profiles = dict_rows(c.execute("SELECT * FROM whitelist WHERE active=1 ORDER BY label").fetchall())
    with st.form("member"):
        a,b = st.columns(2)
        prenom = a.text_input("Prénom *")
        nom = b.text_input("Nom *")
        a,b = st.columns(2)
        code = a.text_input("Code membre", f"MBR-{secrets.token_hex(3).upper()}")
        tel = b.text_input("Téléphone")
        a,b = st.columns(2)
        cot = a.number_input("💵 Épargne/cotisation habituelle (facultatif)", 0.0, step=500.0)
        sol = b.number_input("🤝 Solidarité habituelle (facultatif)", 0.0, step=100.0)
        a,b = st.columns(2)
        freq = a.selectbox("Fréquence", ["Hebdomadaire", "Mensuelle"])
        ins = b.date_input("Début", date.today())
        prof = st.selectbox("Profil", profiles, format_func=lambda x: f"{x['label']} — {x['code']}") if profiles else None
        notes = st.text_area("Observation générale")
        if st.form_submit_button("➕ Ajouter le membre", use_container_width=True):
            if not prenom or not nom:
                st.error("Prénom et nom obligatoires.")
            else:
                try:
                    with db() as c:
                        c.execute(
                            """INSERT INTO members(tontine_id,code,prenom,nom,telephone,inscription,profil_id,cotisation,solidarite,periodicite,date_debut,notes)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (tid,code,prenom,nom,tel,ins.isoformat(),prof["id"] if prof else None,cot,sol,freq,ins.isoformat(),notes)
                        )
                    audit(tid, "Création membre", code)
                    st.rerun()
                except pgdb.IntegrityError:
                    st.error("Ce code existe déjà.")

    with db() as c:
        df = read_df(
            """SELECT id,code,nom,prenom,telephone,cotisation,solidarite,notes,active
               FROM members WHERE tontine_id=? ORDER BY nom,prenom""",
            params=(tid,)
        )
    if not df.empty:
        st.subheader("📋 Tableau de définition des membres")
        st.caption("Les colonnes Épargne/cotisation et Solidarité sont seulement indicatives. Les versements réels restent libres, personne par personne, dans l'onglet Cotisations.")
        edit_df = df[["id","code","nom","prenom","telephone","cotisation","solidarite","notes","active"]].copy()
        edit_df = edit_df.rename(columns={"id":"ID","code":"Code","nom":"Nom","prenom":"Prénom","telephone":"Téléphone",
                                          "cotisation":"Épargne/cotisation indicative","solidarite":"Solidarité indicative",
                                          "notes":"Observation","active":"Actif"})
        with st.form("members_table_form"):
            edited = st.data_editor(
                edit_df,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                column_config={"ID":None},
                disabled=["ID","Code"],
                key=f"members_editor_{tid}"
            )
            if st.form_submit_button("💾 Enregistrer les modifications du tableau", use_container_width=True):
                with db() as c:
                    for _, row in edited.iterrows():
                        c.execute(
                            "UPDATE members SET prenom=?,nom=?,telephone=?,cotisation=?,solidarite=?,notes=?,active=? WHERE id=? AND tontine_id=?",
                            (str(row["Prénom"]),str(row["Nom"]),str(row["Téléphone"] or ""),
                             float(row["Épargne/cotisation indicative"] or 0),float(row["Solidarité indicative"] or 0),
                             str(row["Observation"] or ""),int(bool(row["Actif"])),int(row["ID"]),tid)
                        )
                audit(tid,"Modification tableau membres","Membres et montants indicatifs")
                st.success("Tableau des membres enregistré.")
                st.rerun()

        mid = st.selectbox(
            "🪪 Ouvrir la fiche d'un membre",
            df.id.tolist(),
            format_func=lambda x: f"{df.loc[df.id==x,'nom'].iloc[0]} {df.loc[df.id==x,'prenom'].iloc[0]} — {df.loc[df.id==x,'code'].iloc[0]}"
        )
        member_card(mid, tid)
    else:
        st.info("Aucun membre enregistré dans cette tontine.")

def member_card(mid,tid):
    with db() as c:m=c.execute("SELECT * FROM members WHERE id=?",(mid,)).fetchone()
    f=finance(mid,tid)
    st.markdown("---");st.subheader(f"🪪 Carte : {m['prenom']} {m['nom']}")
    a,b,c,d,e=st.columns(5)
    for z,l,v in zip([a,b,c,d,e],["Montant habituel","Épargne versée","Solidarité versée","Reste emprunt","Tours reçus"],[money(m["cotisation"]),money(f["cp"]),money(f["sp"]),money(f["reste_em"]),money(f["tours"])]):z.metric(l,v)
    if blocked(mid,tid):st.error("🔴 Membre bloqué : impayé ou emprunt non soldé.")
    else:st.success("🟢 Membre à jour.")
    st.caption(f"Solidarité personnelle : {money(m['solidarite'])} • Fréquence : {m['periodicite']}")
    with st.expander("✏️ Modifier les montants individuels"):
        with st.form("editmember"):
            a,b=st.columns(2);cot=a.number_input("Nouvelle cotisation personnelle",0.,value=float(m["cotisation"]),step=500);sol=b.number_input("Nouvelle solidarité",0.,value=float(m["solidarite"]),step=100)
            if st.form_submit_button("Enregistrer pour les prochaines périodes"):
                with db() as c:c.execute("UPDATE members SET cotisation=?,solidarite=? WHERE id=?",(cot,sol,mid))
                audit(tid,"Modification montants indicatifs membre",m["code"]);st.success("Les montants indicatifs du membre ont été enregistrés. Les versements restent libres à chaque date.")

def payments_page(tid):
    """Saisie des cotisations/épargnes librement, personne par personne.

    Aucun montant global ou montant obligatoire n'est imposé par la tontine.
    Le gestionnaire choisit le membre et saisit le montant réellement versé
    pour chaque opération.
    """
    st.title("💳 2 — Cotisations / Épargne par personne")
    st.info("Chaque personne peut verser un montant différent à chaque date. Aucun montant fixe n'est imposé.")

    with db() as c:
        ms = dict_rows(c.execute(
            "SELECT * FROM members WHERE tontine_id=? AND active=1 ORDER BY nom,prenom",
            (tid,)
        ).fetchall())

    if not ms:
        st.info("Ajoutez d'abord des membres à cette tontine.")
        return

    with st.form("payment_personne", clear_on_submit=True):
        member = st.selectbox(
            "👤 Personne", ms,
            format_func=lambda x: f"{x['nom']} {x['prenom']} — {x['code']}"
        )
        d = st.date_input("📅 Date du versement", date.today())
        a,b,c = st.columns(3)
        ep = a.number_input("💰 Épargne / cotisation", min_value=0.0, step=500.0)
        sol = b.number_input("🤝 Solidarité", min_value=0.0, step=100.0)
        am = c.number_input("⚠️ Amende", min_value=0.0, step=100.0)
        obs = st.text_input("Observation")
        if st.form_submit_button("💾 Enregistrer pour cette personne", use_container_width=True):
            if ep == 0 and sol == 0 and am == 0 and not obs.strip():
                st.warning("Saisissez au moins un montant ou une observation.")
            else:
                with db() as c:
                    c.execute(
                        "INSERT INTO encaissements(tontine_id,membre_id,date,solidarite,epargne,amende,observation) VALUES(?,?,?,?,?,?,?)",
                        (tid, member["id"], d.isoformat(), sol, ep, am, obs.strip())
                    )
                audit(tid, "Cotisation par personne", f"{member['code']} — {d.isoformat()}")
                st.success(f"Versement enregistré pour {member['prenom']} {member['nom']}.")
                st.rerun()

    st.subheader("📋 Historique des cotisations par personne")
    with db() as c:
        df = read_df(
            """SELECT e.id, e.date AS Date, m.code AS Code, m.nom || ' ' || m.prenom AS Membre,
                      e.epargne AS Epargne, e.solidarite AS Solidarite, e.amende AS Amende, e.observation AS Observation
               FROM encaissements e JOIN members m ON m.id=e.membre_id
               WHERE e.tontine_id=? ORDER BY e.date::date DESC, e.id DESC""",
            params=(tid,)
        )
    if df.empty:
        st.info("Aucune cotisation enregistrée.")
        return
    for col in ["Epargne","Solidarite","Amende"]:
        df[col] = df[col].apply(money)
    st.dataframe(
        df.rename(columns={"Epargne":"Épargne / cotisation", "Solidarite":"Solidarité"}),
        use_container_width=True, hide_index=True
    )

    st.subheader("🔎 Total par personne")
    with db() as c:
        total = read_df(
            """SELECT m.code AS Code, m.nom || ' ' || m.prenom AS Membre,
                      COALESCE(SUM(e.epargne),0) AS Epargne,
                      COALESCE(SUM(e.solidarite),0) AS Solidarite,
                      COALESCE(SUM(e.amende),0) AS Amende,
                      COALESCE(SUM(e.epargne+e.solidarite+e.amende),0) AS Total
               FROM members m LEFT JOIN encaissements e
                 ON e.membre_id=m.id AND e.tontine_id=?
               WHERE m.tontine_id=? AND m.active=1
               GROUP BY m.id,m.code,m.nom,m.prenom ORDER BY m.nom,m.prenom""",
            params=(tid,tid)
        )
    for col in ["Epargne","Solidarite","Amende","Total"]:
        total[col] = total[col].apply(money)
    st.dataframe(total.rename(columns={"Epargne":"Épargne / cotisation","Solidarite":"Solidarité"}),
                 use_container_width=True, hide_index=True)


def loans_page(tid):
    st.title("💰 Emprunts — suivi par tontine")
    st.caption("Chaque emprunt est rattaché à la tontine active. Les remboursements sont enregistrés avec leur date et le reste est calculé automatiquement.")

    with db() as c:
        ms = dict_rows(c.execute("SELECT * FROM members WHERE tontine_id=? AND active=1 ORDER BY nom,prenom", (tid,)).fetchall())

    if not ms:
        st.info("Ajoutez d'abord un membre à cette tontine.")
        return

    with st.form("loan"):
        m = st.selectbox("Membre", ms, format_func=lambda x: f"{x['nom']} {x['prenom']} — {x['code']}")
        a,b,c = st.columns(3)
        amt = a.number_input("Somme empruntée", min_value=0.0, step=1000.0)
        rate = b.number_input("Taux d'intérêt %", min_value=0.0, step=0.5)
        lim = c.date_input("Échéance", date.today()+timedelta(days=60))
        octroi = st.date_input("Date de l'emprunt", date.today())
        if st.form_submit_button("➕ Enregistrer l'emprunt", use_container_width=True):
            if blocked(m["id"], tid):
                st.error("Ce membre est bloqué jusqu'à régularisation.")
            elif amt <= 0:
                st.error("La somme empruntée doit être supérieure à 0.")
            elif lim < octroi:
                st.error("L'échéance ne peut pas être antérieure à la date de l'emprunt.")
            else:
                inte = amt * rate / 100
                with db() as c:
                    c.execute(
                        """INSERT INTO emprunts(tontine_id,membre_id,montant,taux,interet,total,date_octroi,date_limite)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (tid,m["id"],amt,rate,inte,amt+inte,octroi.isoformat(),lim.isoformat())
                    )
                    c.execute(
                        "INSERT INTO fonds(tontine_id,date,type,montant,membre_id,description) VALUES(?,?,?,?,?,?)",
                        (tid,octroi.isoformat(),"Intérêt",inte,m["id"],"Intérêt généré par emprunt")
                    )
                audit(tid, "Emprunt accordé", m["code"])
                st.rerun()

    st.subheader("📋 Tableau des emprunts")
    f1,f2 = st.columns(2)
    d1 = f1.date_input("Remboursements à partir du", date.today()-timedelta(days=30), key="loan_from")
    d2 = f2.date_input("Remboursements jusqu'au", date.today(), key="loan_to")
    if d1 > d2:
        st.error("La première date doit être antérieure ou égale à la deuxième.")
        return

    refresh(tid)
    with db() as c:
        df = read_df(
            """
            SELECT e.id, m.code, m.nom || ' ' || m.prenom AS membre,
                   e.date_octroi AS date_emprunt, e.montant AS somme_empruntee,
                   e.interet, e.total AS somme_a_rendre,
                   COALESCE((SELECT SUM(r.montant) FROM remboursements r WHERE r.emprunt_id=e.id),0) AS somme_rendue,
                   COALESCE((SELECT SUM(r.montant) FROM remboursements r WHERE r.emprunt_id=e.id AND r.date::date BETWEEN date(?) AND date(?)),0) AS paiement_periode,
                   COALESCE((SELECT MAX(r.date) FROM remboursements r WHERE r.emprunt_id=e.id), '') AS dernier_paiement,
                   e.date_limite AS echeance, e.statut
            FROM emprunts e JOIN members m ON m.id=e.membre_id
            WHERE e.tontine_id=?
            ORDER BY e.id DESC
            """,
            params=(d1.isoformat(), d2.isoformat(), tid)
        )

    if df.empty:
        st.info("Aucun emprunt pour cette tontine.")
    else:
        df["reste"] = (df["somme_a_rendre"] - df["somme_rendue"]).clip(lower=0)
        display = df.rename(columns={
            "code":"Code", "membre":"Membre", "date_emprunt":"Date emprunt",
            "somme_empruntee":"Somme empruntée", "interet":"Intérêt",
            "somme_a_rendre":"Total à rendre", "somme_rendue":"Somme rendue",
            "paiement_periode":"Paiement période", "dernier_paiement":"Dernier paiement",
            "echeance":"Échéance", "reste":"Reste à rendre", "statut":"Statut"
        })[["Code","Membre","Date emprunt","Somme empruntée","Intérêt","Total à rendre",
           "Somme rendue","Paiement période","Dernier paiement","Échéance","Reste à rendre","Statut"]].copy()
        for col in ["Somme empruntée","Intérêt","Total à rendre","Somme rendue","Paiement période","Reste à rendre"]:
            display[col] = display[col].apply(money)
        st.dataframe(display, use_container_width=True, hide_index=True)

    ids = df[df["somme_a_rendre"] > df["somme_rendue"]]["id"].tolist() if not df.empty else []
    if ids:
        st.subheader("💵 Enregistrer un remboursement")
        eid = st.selectbox("Emprunt concerné", ids, format_func=lambda x: next(
            f"{df.loc[df.id==x,'membre'].iloc[0]} — reste {money(max(0,df.loc[df.id==x,'somme_a_rendre'].iloc[0]-df.loc[df.id==x,'somme_rendue'].iloc[0]))}"
            for _ in [0]
        ))
        with st.form("rep"):
            a,b = st.columns(2)
            max_reste = float(max(0, df.loc[df.id==eid,"somme_a_rendre"].iloc[0] - df.loc[df.id==eid,"somme_rendue"].iloc[0]))
            x = a.number_input("Somme rendue", min_value=0.0, max_value=max_reste if max_reste > 0 else 0.0, step=1000.0)
            d = b.date_input("Date du remboursement", date.today())
            if st.form_submit_button("💾 Enregistrer le remboursement", use_container_width=True) and x > 0:
                with db() as c:
                    c.execute("INSERT INTO remboursements(emprunt_id,montant,date) VALUES(?,?,?)", (eid,x,d.isoformat()))
                audit(tid, "Remboursement", f"Emprunt {eid} — {x} FCFA")
                refresh(tid)
                st.rerun()

    st.subheader("🧾 Détail des remboursements par date")
    with db() as c:
        repayments = read_df(
            """
            SELECT r.date AS Date, m.nom || ' ' || m.prenom AS Membre,
                   e.id AS Emprunt, r.montant AS "Somme rendue"
            FROM remboursements r
            JOIN emprunts e ON e.id=r.emprunt_id
            JOIN members m ON m.id=e.membre_id
            WHERE e.tontine_id=? AND r.date::date BETWEEN date(?) AND date(?)
            ORDER BY r.date::date DESC, r.id DESC
            """,
            params=(tid,d1.isoformat(),d2.isoformat())
        )
    if not repayments.empty:
        repayments["Somme rendue"] = repayments["Somme rendue"].apply(money)
    st.dataframe(repayments, use_container_width=True, hide_index=True)

def turns_page(tid):
    st.title("🎯 4 — Tours de tontine")
    with db() as c:ms=dict_rows(c.execute("SELECT * FROM members WHERE tontine_id=? AND active=1 ORDER BY nom",(tid,)).fetchall())
    with st.form("tour"):
        a,b=st.columns(2);w=a.number_input("Semaine",1,999,1);d=b.date_input("Date",date.today())
        m=st.selectbox("Bénéficiaire",ms,format_func=lambda x:f"{x['prenom']} {x['nom']} — {x['code']}")
        amt=st.number_input("Cagnotte",0.,step=1000.);status=st.selectbox("Statut",["Planifié","Payé","Annulé"])
        if st.form_submit_button("📌 Fixer le tour"):
            with db() as c:
                old=c.execute("SELECT id FROM tours WHERE tontine_id=? AND semaine=?",(tid,w)).fetchone()
                if old:c.execute("UPDATE tours SET date=?,membre_id=?,montant=?,statut=? WHERE id=?",(d.isoformat(),m["id"],amt,status,old["id"]))
                else:c.execute("INSERT INTO tours(tontine_id,semaine,date,membre_id,montant,statut) VALUES(?,?,?,?,?,?)",(tid,w,d.isoformat(),m["id"],amt,status))
            audit(tid,"Tour fixé",str(w));st.rerun()
    with db() as c:df=read_df("""SELECT t.semaine,t.date,m.code,m.prenom||' '||m.nom membre,t.montant,t.statut
    FROM tours t JOIN members m ON m.id=t.membre_id WHERE t.tontine_id=? ORDER BY t.semaine""", params=(tid,))
    st.dataframe(df,use_container_width=True,hide_index=True)

def fund_page(tid):
    st.title("🏦 5 — Fonds de solidarité")
    with db() as c:
        sol=c.execute("SELECT COALESCE(SUM(solidarite),0) x FROM encaissements WHERE tontine_id=?",(tid,)).fetchone()["x"]
        plus=c.execute("SELECT COALESCE(SUM(montant),0) x FROM fonds WHERE tontine_id=? AND type IN ('Apport','Intérêt')",(tid,)).fetchone()["x"]
        moins=c.execute("SELECT COALESCE(SUM(montant),0) x FROM fonds WHERE tontine_id=? AND type IN ('Sortie','Aide')",(tid,)).fetchone()["x"]
        df=read_df("SELECT date,type,montant,description FROM fonds WHERE tontine_id=? ORDER BY id DESC", params=(tid,))
    st.metric("Fonds estimé disponible",money(sol+plus-moins));st.dataframe(df,use_container_width=True,hide_index=True)
    with st.form("fund"):
        a,b=st.columns(2);typ=a.selectbox("Type",["Apport","Sortie","Aide","Autre"]);amt=b.number_input("Montant",0.,step=1000.);desc=st.text_input("Description")
        if st.form_submit_button("Enregistrer mouvement") and amt>0:
            with db() as c:c.execute("INSERT INTO fonds(tontine_id,date,type,montant,description) VALUES(?,?,?,?,?)",(tid,date.today().isoformat(),typ,amt,desc))
            audit(tid,"Mouvement fonds",typ);st.rerun()

def docs_page(tid):
    st.title("📄 6 — Documents & PDF")
    with db() as c:ms=dict_rows(c.execute("SELECT * FROM members WHERE tontine_id=? ORDER BY nom,prenom",(tid,)).fetchall())
    if not ms:return st.info("Aucun membre.")
    m=st.selectbox("Membre",ms,format_func=lambda x:f"{x['prenom']} {x['nom']} — {x['code']}")
    mode=st.radio("Période",["Complet","Année","Mois"],horizontal=True)
    year=st.number_input("Année",2000,2100,date.today().year) if mode!="Complet" else None
    month=st.selectbox("Mois",range(1,13)) if mode=="Mois" else None
    data=pdf_member(m["id"],tid,year,month)
    if data is None:
        return
    st.download_button("📥 Générer le PDF",data,f"{m['code']}_{year or 'complet'}{('_'+str(month)) if month else ''}.pdf","application/pdf",use_container_width=True)

def pdf_tontine_report(tid, debut=None, fin=None):
    if not _require_reportlab():
        return None
    """Génère un rapport PDF global de la tontine active."""
    t = T(tid)
    week = active_week(tid)
    if debut is None:
        debut = date.fromisoformat(week["debut"]) if week else date.today() - timedelta(days=date.today().weekday())
    if fin is None:
        fin = date.fromisoformat(week["fin"]) if week else debut + timedelta(days=6)

    with db() as c:
        members = c.execute(
            "SELECT id,code,nom,prenom FROM members WHERE tontine_id=? AND active=1 ORDER BY nom,prenom",
            (tid,)
        ).fetchall()
        enc = c.execute(
            """SELECT m.nom,m.prenom,m.code,e.date,e.epargne,e.solidarite,e.amende,e.observation
               FROM encaissements e JOIN members m ON m.id=e.membre_id
               WHERE e.tontine_id=? AND e.date::date BETWEEN date(?) AND date(?)
               ORDER BY e.date::date,m.nom,m.prenom""",
            (tid,debut.isoformat(),fin.isoformat())
        ).fetchall()
        loans = c.execute(
            """SELECT e.id,m.nom,m.prenom,e.date_octroi,e.montant,e.interet,e.total,e.date_limite,e.statut,
                      COALESCE((SELECT SUM(r.montant) FROM remboursements r WHERE r.emprunt_id=e.id),0) AS rendu
               FROM emprunts e JOIN members m ON m.id=e.membre_id
               WHERE e.tontine_id=? ORDER BY e.date_octroi DESC""",
            (tid,)
        ).fetchall()
        rems = c.execute(
            """SELECT r.date,m.nom,m.prenom,r.montant,e.id AS emprunt
               FROM remboursements r JOIN emprunts e ON e.id=r.emprunt_id
               JOIN members m ON m.id=e.membre_id
               WHERE e.tontine_id=? AND r.date::date BETWEEN date(?) AND date(?)
               ORDER BY r.date::date""",
            (tid,debut.isoformat(),fin.isoformat())
        ).fetchall()

    total_ep = sum(float(x["epargne"] or 0) for x in enc)
    total_sol = sum(float(x["solidarite"] or 0) for x in enc)
    total_am = sum(float(x["amende"] or 0) for x in enc)
    total_rem = sum(float(x["montant"] or 0) for x in rems)
    total_loans = sum(float(x["montant"] or 0) for x in loans)
    total_rendu = sum(float(x["rendu"] or 0) for x in loans)
    caisse = total_ep + total_sol + total_am + total_rem - total_loans

    b = BytesIO()
    doc = SimpleDocTemplate(b, pagesize=A4, rightMargin=28, leftMargin=28, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("TONTINE MANAGER", styles["Title"]),
        Paragraph(f"RAPPORT GLOBAL — {t['nom']} ({t['code']})", styles["Heading2"]),
        Paragraph(f"Période : {debut.strftime('%d/%m/%Y')} → {fin.strftime('%d/%m/%Y')}", styles["Normal"]),
        Spacer(1, 12),
    ]
    story.append(Table([
        ["Indicateur","Montant"],
        ["Nombre de membres", str(len(members))],
        ["Épargne / cotisations", money(total_ep)],
        ["Solidarité", money(total_sol)],
        ["Amendes", money(total_am)],
        ["Remboursements reçus", money(total_rem)],
        ["Emprunts accordés", money(total_loans)],
        ["Solde calculé de caisse", money(caisse)],
    ], style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white)])))

    story += [Spacer(1,14), Paragraph("Cotisations / opérations par personne", styles["Heading2"])]
    rows = [["Date","Membre","Épargne","Solidarité","Amende","Observation"]]
    for x in enc:
        rows.append([x["date"],f"{x['nom']} {x['prenom']}",money(x["epargne"]),money(x["solidarite"]),money(x["amende"]),x["observation"] or "-"])
    if len(rows)==1:
        rows.append(["-","Aucune opération","-","-","-","-"])
    story.append(Table(rows,repeatRows=1,style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white)])))

    story += [Spacer(1,14), Paragraph("Emprunts et reste à rendre", styles["Heading2"])]
    rows = [["Membre","Date","Emprunt","Total à rendre","Rendu","Reste","Échéance","Statut"]]
    for x in loans:
        reste=max(0,float(x["total"] or 0)-float(x["rendu"] or 0))
        rows.append([f"{x['nom']} {x['prenom']}",x["date_octroi"],money(x["montant"]),money(x["total"]),money(x["rendu"]),money(reste),x["date_limite"],x["statut"]])
    if len(rows)==1:
        rows.append(["Aucun","-","-","-","-","-","-","-"])
    story.append(Table(rows,repeatRows=1,style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white)])))

    story += [Spacer(1,14), Paragraph("Remboursements enregistrés sur la période", styles["Heading2"])]
    rows = [["Date","Membre","Emprunt","Somme rendue"]]
    for x in rems:
        rows.append([x["date"],f"{x['nom']} {x['prenom']}",str(x["emprunt"]),money(x["montant"])])
    if len(rows)==1:
        rows.append(["-","Aucun remboursement","-","-"])
    story.append(Table(rows,repeatRows=1,style=TableStyle([("GRID",(0,0),(-1,-1),.3,colors.grey),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white)])))

    story += [Spacer(1,12), Paragraph("Document généré automatiquement par Tontine Manager.", styles["Normal"])]
    doc.build(story)
    return b.getvalue()

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

    pdf = pdf_tontine_report(tid, debut, fin)
    st.download_button(
        "📄 Générer le rapport PDF complet", pdf,
        f"rapport_tontine_{debut.isoformat()}_{fin.isoformat()}.pdf",
        "application/pdf", use_container_width=True
    )


def guided_visits_page(tid):
    st.title("🧭 Visites guidées")
    st.info("Espace pratique du gérant : utilisez les boutons ci-dessous pour suivre le fonctionnement de la tontine sans accéder aux paramètres d'administration.")
    tabs = st.tabs(["👥 Membres", "💳 Cotisations", "💰 Emprunts", "🏦 Fonds", "📄 Documents", "📊 Rapports"])
    with tabs[0]:
        st.markdown("**Membres :** ajoutez les personnes et consultez leur tableau. Les montants indicatifs ne bloquent jamais les versements réels.")
    with tabs[1]:
        st.markdown("**Cotisations :** choisissez une personne et saisissez librement l'épargne, la solidarité et l'amende pour chaque date.")
    with tabs[2]:
        st.markdown("**Emprunts :** enregistrez la somme empruntée, l'échéance et chaque remboursement daté. Le reste est automatique.")
    with tabs[3]:
        st.markdown("**Fonds :** consultez les entrées et sorties de caisse de la tontine.")
    with tabs[4]:
        st.markdown("**Documents :** générez les fiches individuelles et les PDF disponibles.")
    with tabs[5]:
        st.markdown("**Rapports :** consultez les synthèses et générez le rapport PDF de la tontine.")

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
    elif page=="📄 Documents & PDF":docs_page(tid)
    elif page=="📊 Rapports":reports_page(tid)
    elif page=="❓ Guide":guide_page()

if __name__=="__main__":main()
