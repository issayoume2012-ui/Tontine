import streamlit as st
import psycopg2
import psycopg2.extras
import bcrypt
import io
import pandas as pd
from datetime import date, datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# ==========================================
# CONFIGURATION DE LA PAGE STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Gestion de Tontine Pro - PostgreSQL/Supabase",
    page_icon="🏦",
    layout="wide"
)

# ==========================================
# PARAMÈTRES DE CONNEXION POSTGRESQL / SUPABASE
# ==========================================
DB_CONFIG = {
    "host": "db.rrpmbnxmmsoryzyadhaj.supabase.co",
    "port": 5432,
    "database": "postgres",
    "user": "postgres",
    "password": "EoalvKG2mAx1AbC6"
}

def get_db_connection():
    """Établit et retourne une connexion à PostgreSQL / Supabase."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        st.error(f"Erreur de connexion à la base de données PostgreSQL : {e}")
        return None

# ==========================================
# INITIALISATION AUTOMATIQUE DES TABLES
# ==========================================
def init_database():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        
        # Extension UUID si nécessaire
        cur.execute('create extension if not exists "uuid-ossp";')

        # 1. Table Tontines
        cur.execute("""
        create table if not exists tontines (
            id uuid default uuid_generate_v4() primary key,
            code text unique not null,
            name text not null,
            description text,
            start_date date not null,
            end_date date not null,
            is_active boolean default true,
            is_locked boolean default false,
            created_at timestamp with time zone default timezone('utc'::text, now()) not null,
            updated_at timestamp with time zone default timezone('utc'::text, now()) not null
        );
        """)

        # 2. Table Utilisateurs
        cur.execute("""
        create table if not exists users (
            id uuid default uuid_generate_v4() primary key,
            email text unique not null,
            password_hash text not null,
            full_name text not null,
            role text not null check (role in ('admin_general', 'gerant')),
            tontine_id uuid references tontines(id) on delete set null,
            is_active boolean default true,
            created_at timestamp with time zone default timezone('utc'::text, now()) not null,
            updated_at timestamp with time zone default timezone('utc'::text, now()) not null
        );
        """)

        # 3. Table Whitelist
        cur.execute("""
        create table if not exists whitelist (
            id uuid default uuid_generate_v4() primary key,
            email text unique not null,
            role text not null check (role in ('admin_general', 'gerant')),
            tontine_id uuid,
            created_at timestamp with time zone default timezone('utc'::text, now()) not null
        );
        """)

        # 4. Table Membres
        cur.execute("""
        create table if not exists members (
            id uuid default uuid_generate_v4() primary key,
            tontine_id uuid not null references tontines(id) on delete cascade,
            member_code text not null,
            first_name text not null,
            last_name text not null,
            phone text not null,
            registration_date date not null default current_date,
            profile text default 'standard',
            indicative_contribution numeric(12,2) default 0.00 check (indicative_contribution >= 0),
            indicative_solidarity numeric(12,2) default 0.00 check (indicative_solidarity >= 0),
            periodicity text default 'mensuel' check (periodicity in ('journalier', 'hebdomadaire', 'mensuel')),
            start_date date,
            end_date date,
            is_active boolean default true,
            observations text,
            created_at timestamp with time zone default timezone('utc'::text, now()) not null,
            updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
            constraint unique_member_code_per_tontine unique (tontine_id, member_code)
        );
        """)

        # 5. Table Cotisations
        cur.execute("""
        create table if not exists contributions (
            id uuid default uuid_generate_v4() primary key,
            tontine_id uuid not null references tontines(id) on delete cascade,
            member_id uuid not null references members(id) on delete cascade,
            date timestamp with time zone default timezone('utc'::text, now()) not null,
            savings_amount numeric(12,2) default 0.00 check (savings_amount >= 0),
            solidarity_amount numeric(12,2) default 0.00 check (solidarity_amount >= 0),
            fine_amount numeric(12,2) default 0.00 check (fine_amount >= 0),
            observation text,
            recorded_by uuid references users(id),
            created_at timestamp with time zone default timezone('utc'::text, now()) not null
        );
        """)

        # 6. Table Emprunts
        cur.execute("""
        create table if not exists loans (
            id uuid default uuid_generate_v4() primary key,
            tontine_id uuid not null references tontines(id) on delete cascade,
            member_id uuid not null references members(id) on delete cascade,
            borrowed_amount numeric(12,2) not null check (borrowed_amount > 0),
            interest_rate numeric(5,2) not null check (interest_rate >= 0),
            calculated_interest numeric(12,2) not null check (calculated_interest >= 0),
            total_to_repay numeric(12,2) not null check (total_to_repay >= 0),
            grant_date date not null default current_date,
            due_date date not null,
            remaining_amount numeric(12,2) not null check (remaining_amount >= 0),
            status text default 'en_cours' check (status in ('en_cours', 'solde', 'en_retard')),
            recorded_by uuid references users(id),
            created_at timestamp with time zone default timezone('utc'::text, now()) not null
        );
        """)

        # 7. Table Remboursements
        cur.execute("""
        create table if not exists repayments (
            id uuid default uuid_generate_v4() primary key,
            tontine_id uuid not null references tontines(id) on delete cascade,
            loan_id uuid not null references loans(id) on delete cascade,
            date timestamp with time zone default timezone('utc'::text, now()) not null,
            amount_paid numeric(12,2) not null check (amount_paid > 0),
            observation text,
            recorded_by uuid references users(id),
            created_at timestamp with time zone default timezone('utc'::text, now()) not null
        );
        """)

        # 8. Table Fonds
        cur.execute("""
        create table if not exists funds (
            id uuid default uuid_generate_v4() primary key,
            tontine_id uuid not null references tontines(id) on delete cascade,
            date timestamp with time zone default timezone('utc'::text, now()) not null,
            movement_type text not null check (movement_type in ('apport', 'sortie', 'aide', 'interet', 'autre')),
            amount numeric(12,2) not null,
            description text,
            recorded_by uuid references users(id),
            created_at timestamp with time zone default timezone('utc'::text, now()) not null
        );
        """)

        # 9. Table Historique (Audit Logs)
        cur.execute("""
        create table if not exists audit_logs (
            id uuid default uuid_generate_v4() primary key,
            user_id uuid references users(id),
            user_role text,
            tontine_id uuid references tontines(id),
            action_timestamp timestamp with time zone default timezone('utc'::text, now()) not null,
            action_type text not null,
            table_name text not null,
            record_id uuid,
            old_values text,
            new_values text
        );
        """)

        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Erreur lors de l'initialisation des tables : {e}")

# Lancer l'initialisation de la base de données au démarrage
init_database()

# ==========================================
# FONCTIONS UTILITAIRES & SÉCURITÉ
# ==========================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def log_action(user_id, user_role, tontine_id, action_type, table_name, record_id=None):
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute(
            """
            insert into audit_logs (user_id, user_role, tontine_id, action_type, table_name, record_id)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, user_role, tontine_id, action_type, table_name, record_id)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Erreur log : {e}")

# ==========================================
# MODULE D'AUTHENTIFICATION
# ==========================================
def render_auth():
    st.subheader("🔐 Connexion à l'application Tontine")
    
    # Création d'un compte admin par défaut si aucun utilisateur n'existe
    conn = get_db_connection()
    if conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("select count(*) as count from users;")
        res = cur.fetchone()
        if res["count"] == 0:
            default_pwd = hash_password("Admin123*")
            cur.execute(
                "insert into users (email, password_hash, full_name, role, is_active) values (%s, %s, %s, %s, %s)",
                ("admin@tontine.com", default_pwd, "Administrateur Général", "admin_general", True)
            )
            conn.commit()
        cur.close()
        conn.close()

    with st.form("login_form"):
        email = st.text_input("Adresse Email")
        password = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Se connecter")
        
        if submit:
            if not email or not password:
                st.warning("Veuillez remplir tous les champs.")
                return
            
            conn = get_db_connection()
            if not conn:
                return
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("select * from users where email = %s", (email,))
            user = cur.fetchone()
            cur.close()
            conn.close()
            
            if not user:
                st.error("Utilisateur introuvable.")
                return
            
            if not user["is_active"]:
                st.error("Ce compte est désactivé.")
                return
                
            if verify_password(password, user["password_hash"]):
                st.session_state["user"] = dict(user)
                st.session_state["role"] = user["role"]
                st.session_state["tontine_id"] = user["tontine_id"]
                log_action(user["id"], user["role"], user["tontine_id"], "CONNEXION", "users", user["id"])
                st.success("Connexion réussie !")
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")

# ==========================================
# MODULE ADMINISTRATION GÉNÉRALE
# ==========================================
def render_admin_module():
    st.title("⚙️ Administration Générale")
    tab1, tab2, tab3, tab4 = st.tabs(["Gérants", "Tontines", "Liste Blanche", "Journal d'Audit"])
    
    conn = get_db_connection()
    if not conn:
        return
        
    with tab1:
        st.subheader("Création et Gestion des Gérants")
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("select * from tontines")
        tontines = cur.fetchall()
        tontine_map = {t["name"]: t["id"] for t in tontines}
        
        with st.form("create_mgr"):
            name = st.text_input("Nom complet")
            email = st.text_input("Email")
            pwd = st.text_input("Mot de passe temporaire", type="password")
            t_name = st.selectbox("Tontine assignée", options=list(tontine_map.keys()) if tontine_map else [])
            sub = st.form_submit_button("Créer le gérant")
            if sub:
                if email and pwd and t_name:
                    try:
                        hashed = hash_password(pwd)
                        t_id = tontine_map[t_name]
                        cur.execute(
                            "insert into users (email, password_hash, full_name, role, tontine_id, is_active) values (%s, %s, %s, 'gerant', %s, true)",
                            (email, hashed, name, t_id)
                        )
                        conn.commit()
                        st.success("Gérant créé avec succès !")
                    except Exception as e:
                        st.error(f"Erreur : {e}")
        
        st.divider()
        st.subheader("Liste des Gérants")
        cur.execute("select u.id, u.full_name, u.email, u.is_active, t.name as tontine_name from users u left join tontines t on u.tontine_id = t.id where u.role = 'gerant'")
        managers = cur.fetchall()
        for m in managers:
            col1, col2 = st.columns([4, 1])
            col1.write(f"**{m['full_name']}** ({m['email']}) - Tontine : {m['tontine_name']} - Actif : {m['is_active']}")
            if col2.button("Activer/Désactiver", key=f"mgr_toggle_{m['id']}"):
                cur.execute("update users set is_active = not is_active where id = %s", (m['id'],))
                conn.commit()
                st.rerun()

    with tab2:
        st.subheader("Gestion des Tontines")
        with st.form("create_tontine"):
            code = st.text_input("Code unique")
            tname = st.text_input("Nom de la tontine")
            desc = st.text_area("Description")
            start = st.date_input("Date de début", value=date.today())
            end = st.date_input("Date de fin", value=date.today())
            sub_t = st.form_submit_button("Créer la tontine")
            if sub_t:
                try:
                    cur.execute(
                        "insert into tontines (code, name, description, start_date, end_date) values (%s, %s, %s, %s, %s)",
                        (code, tname, desc, start, end)
                    )
                    conn.commit()
                    st.success("Tontine créée avec succès !")
                except Exception as e:
                    st.error(f"Erreur : {e}")

        st.divider()
        cur.execute("select * from tontines")
        all_tontines = cur.fetchall()
        for t in all_tontines:
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"**{t['name']}** (Code: {t['code']}) | Active: {t['is_active']} | Verrouillée: {t['is_locked']}")
            if c2.button("Verrouiller/Déverrouiller", key=f"lock_{t['id']}"):
                cur.execute("update tontines set is_locked = not is_locked where id = %s", (t['id'],))
                conn.commit()
                st.rerun()
            if c3.button("Activer/Désactiver", key=f"act_{t['id']}"):
                cur.execute("update tontines set is_active = not is_active where id = %s", (t['id'],))
                conn.commit()
                st.rerun()

    with tab3:
        st.subheader("Liste Blanche (Whitelist)")
        with st.form("whitelist"):
            w_email = st.text_input("Email autorisé")
            w_role = st.selectbox("Rôle", ["admin_general", "gerant"])
            sub_w = st.form_submit_button("Ajouter")
            if sub_w:
                try:
                    cur.execute("insert into whitelist (email, role) values (%s, %s)", (w_email, w_role))
                    conn.commit()
                    st.success("Ajouté à la whitelist.")
                except Exception as e:
                    st.error(f"Erreur : {e}")

    with tab4:
        st.subheader("Journal d'Audit & Historique")
        cur.execute("select * from audit_logs order by action_timestamp desc limit 50")
        logs = cur.fetchall()
        if logs:
            df_logs = pd.DataFrame(logs)
            st.dataframe(df_logs)
        else:
            st.info("Aucun historique disponible.")
            
    cur.close()
    conn.close()

# ==========================================
# MODULE MEMBRES
# ==========================================
def render_members_module(tontine_id):
    st.subheader("👥 Gestion des Membres")
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    with st.form("add_member"):
        col1, col2 = st.columns(2)
        with col1:
            code = st.text_input("Code Membre")
            fn = st.text_input("Prénom")
            ln = st.text_input("Nom")
            phone = st.text_input("Téléphone")
        with col2:
            period = st.selectbox("Périodicité", ["mensuel", "hebdomadaire", "journalier"])
            contrib = st.number_input("Cotisation personnalisée", min_value=0.0, step=500.0)
            solidarity = st.number_input("Solidarité personnalisée", min_value=0.0, step=100.0)
            obs = st.text_area("Observations")
            
        sub = st.form_submit_button("Enregistrer le membre")
        if sub:
            try:
                cur.execute(
                    """
                    insert into members (tontine_id, member_code, first_name, last_name, phone, periodicity, indicative_contribution, indicative_solidarity, observations)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tontine_id, code, fn, ln, phone, period, contrib, solidarity, obs)
                )
                conn.commit()
                st.success("Membre enregistré avec succès !")
                log_action(st.session_state["user"]["id"], st.session_state["role"], tontine_id, "AJOUT_MEMBRE", "members")
            except Exception as e:
                st.error(f"Erreur : {e}")
                
    st.divider()
    cur.execute("select * from members where tontine_id = %s", (tontine_id,))
    members = cur.fetchall()
    if members:
        st.dataframe(pd.DataFrame(members))
    else:
        st.info("Aucun membre enregistré pour cette tontine.")
    cur.close()
    conn.close()

# ==========================================
# MODULE COTISATIONS
# ==========================================
def render_cotisations_module(tontine_id):
    st.subheader("💰 Enregistrement des Cotisations")
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cur.execute("select id, member_code, first_name, last_name from members where tontine_id = %s and is_active = true", (tontine_id,))
    members = cur.fetchall()
    if not members:
        st.warning("Aucun membre actif disponible.")
        cur.close()
        conn.close()
        return
        
    m_map = {f"{m['member_code']} - {m['first_name']} {m['last_name']}": m['id'] for m in members}
    
    with st.form("cotisation_form"):
        selected_m = st.selectbox("Sélectionner le membre", options=list(m_map.keys()))
        savings = st.number_input("Montant Épargne / Cotisation", min_value=0.0, step=500.0)
        solidarity = st.number_input("Solidarité", min_value=0.0, step=100.0)
        fine = st.number_input("Amende", min_value=0.0, step=100.0)
        obs = st.text_area("Observation")
        
        sub = st.form_submit_button("Enregistrer la cotisation")
        if sub:
            m_id = m_map[selected_m]
            try:
                cur.execute(
                    """
                    insert into contributions (tontine_id, member_id, savings_amount, solidarity_amount, fine_amount, observation, recorded_by)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tontine_id, m_id, savings, solidarity, fine, obs, st.session_state["user"]["id"])
                )
                conn.commit()
                st.success("Cotisation enregistrée avec succès !")
                log_action(st.session_state["user"]["id"], st.session_state["role"], tontine_id, "COTISATION", "contributions")
            except Exception as e:
                st.error(f"Erreur : {e}")
                
    cur.close()
    conn.close()

# ==========================================
# MODULE EMPRUNTS & REMBOURSEMENTS
# ==========================================
def render_emprunts_module(tontine_id):
    st.subheader("📊 Gestion des Emprunts & Remboursements")
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cur.execute("select id, member_code, first_name, last_name from members where tontine_id = %s and is_active = true", (tontine_id,))
    members = cur.fetchall()
    m_map = {f"{m['member_code']} - {m['first_name']} {m['last_name']}": m['id'] for m in members} if members else {}
    
    with st.form("loan_form"):
        selected_m = st.selectbox("Membre Emprunteur", options=list(m_map.keys())) if m_map else st.selectbox("Membre Emprunteur", options=[])
        amount = st.number_input("Montant emprunté", min_value=1000.0, step=1000.0)
        rate = st.number_input("Taux d'intérêt (%)", min_value=0.0, value=5.0, step=0.5)
        due_date = st.date_input("Date d'échéance", value=date.today())
        
        sub = st.form_submit_button("Octroyer l'emprunt")
        if sub and m_map:
            m_id = m_map[selected_m]
            interest = amount * (rate / 100.0)
            total = amount + interest
            try:
                # Transaction sécurisée : Emprunt + Sortie de fonds conjointe
                cur.execute(
                    """
                    insert into loans (tontine_id, member_id, borrowed_amount, interest_rate, calculated_interest, total_to_repay, due_date, remaining_amount, recorded_by)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tontine_id, m_id, amount, rate, interest, total, due_date, total, st.session_state["user"]["id"])
                )
                cur.execute(
                    """
                    insert into funds (tontine_id, movement_type, amount, description, recorded_by)
                    values (%s, 'sortie', %s, %s, %s)
                    """,
                    (tontine_id, amount, f"Octroi d'emprunt au membre {selected_m}", st.session_state["user"]["id"])
                )
                conn.commit()
                st.success("Emprunt accordé et fonds mis à jour avec succès !")
                log_action(st.session_state["user"]["id"], st.session_state["role"], tontine_id, "OCTROI_EMPRUNT", "loans")
            except Exception as e:
                conn.rollback()
                st.error(f"Erreur lors de la transaction : {e}")

    st.divider()
    st.subheader("Remboursement d'Emprunt")
    cur.execute("select id, borrowed_amount, remaining_amount from loans where tontine_id = %s and status = 'en_cours'", (tontine_id,))
    loans = cur.fetchall()
    loan_map = {f"Emprunt ID: {l['id']} - Restant: {l['remaining_amount']} FCFA": l['id'] for l in loans} if loans else {}
    
    with st.form("repayment_form"):
        sel_loan = st.selectbox("Sélectionner l'emprunt", options=list(loan_map.keys())) if loan_map else st.selectbox("Sélectionner l'emprunt", options=[])
        pay_amount = st.number_input("Montant remboursé", min_value=100.0, step=500.0)
        obs_rep = st.text_area("Observation")
        sub_rep = st.form_submit_button("Enregistrer le remboursement")
        if sub_rep and loan_map:
            l_id = loan_map[sel_loan]
            try:
                cur.execute("select remaining_amount from loans where id = %s", (l_id,))
                current_rem = float(cur.fetchone()["remaining_amount"])
                new_rem = max(0.0, current_rem - pay_amount)
                new_status = "solde" if new_rem == 0 else "en_cours"
                
                cur.execute(
                    """
                    insert into repayments (tontine_id, loan_id, amount_paid, observation, recorded_by)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (tontine_id, l_id, pay_amount, obs_rep, st.session_state["user"]["id"])
                )
                cur.execute(
                    "update loans set remaining_amount = %s, status = %s where id = %s",
                    (new_rem, new_status, l_id)
                )
                cur.execute(
                    """
                    insert into funds (tontine_id, movement_type, amount, description, recorded_by)
                    values (%s, 'apport', %s, %s, %s)
                    """,
                    (tontine_id, pay_amount, f"Remboursement d'emprunt", st.session_state["user"]["id"])
                )
                conn.commit()
                st.success("Remboursement enregistré avec succès !")
            except Exception as e:
                conn.rollback()
                st.error(f"Erreur : {e}")

    cur.close()
    conn.close()

# ==========================================
# MODULE FONDS & TRÉSORERIE
# ==========================================
def render_fonds_module(tontine_id):
    st.subheader("💼 Gestion de la Trésorerie & Fonds")
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    with st.form("fund_form"):
        m_type = st.selectbox("Type de mouvement", ["apport", "sortie", "aide", "interet", "autre"])
        amount = st.number_input("Montant", min_value=0.0, step=500.0)
        desc = st.text_area("Description")
        sub = st.form_submit_button("Enregistrer le mouvement")
        if sub:
            try:
                cur.execute(
                    """
                    insert into funds (tontine_id, movement_type, amount, description, recorded_by)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (tontine_id, m_type, amount, desc, st.session_state["user"]["id"])
                )
                conn.commit()
                st.success("Mouvement de fonds enregistré.")
            except Exception as e:
                st.error(f"Erreur : {e}")
                
    st.divider()
    cur.execute("select * from funds where tontine_id = %s order by date desc", (tontine_id,))
    funds = cur.fetchall()
    if funds:
        st.dataframe(pd.DataFrame(funds))
    cur.close()
    conn.close()

# ==========================================
# MODULE DOCUMENTS & PDF
# ==========================================
def generate_pdf_statement(member_info, contributions):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.drawString(100, 750, f"Fiche Individuelle - {member_info['first_name']} {member_info['last_name']}")
    p.drawString(100, 730, f"Code Membre : {member_info['member_code']}")
    y = 690
    p.drawString(100, y, "Date | Épargne | Solidarité | Amende")
    y -= 20
    for c in contributions:
        line = f"{str(c['date'])[:10]} | {c['savings_amount']} | {c['solidarity_amount']} | {c['fine_amount']}"
        p.drawString(100, y, line)
        y -= 20
        if y < 50:
            p.showPage()
            y = 750
    p.save()
    buffer.seek(0)
    return buffer.getvalue()

def render_documents_module(tontine_id):
    st.subheader("📄 Documents & PDF")
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cur.execute("select id, member_code, first_name, last_name from members where tontine_id = %s", (tontine_id,))
    members = cur.fetchall()
    m_map = {f"{m['member_code']} - {m['first_name']} {m['last_name']}": m['id'] for m in members} if members else {}
    
    if m_map:
        sel_m = st.selectbox("Choisir un membre", options=list(m_map.keys()))
        if st.button("Générer le relevé PDF"):
            m_id = m_map[sel_m]
            cur.execute("select * from members where id = %s", (m_id,))
            m_info = cur.fetchone()
            cur.execute("select * from contributions where member_id = %s", (m_id,))
            contribs = cur.fetchall()
            
            pdf_bytes = generate_pdf_statement(m_info, contribs)
            st.download_button(
                label="Télécharger le PDF",
                data=pdf_bytes,
                file_name=f"fiche_{m_info['member_code']}.pdf",
                mime="application/pdf"
            )
    else:
        st.info("Aucun membre disponible pour générer de documents.")
    cur.close()
    conn.close()

# ==========================================
# INTERFACE PRINCIPALE & ROUTAGE
# ==========================================
def main():
    if "user" not in st.session_state:
        render_auth()
        return
        
    user = st.session_state["user"]
    role = st.session_state["role"]
    
    st.sidebar.title(f"Bienvenue, {user['full_name']}")
    st.sidebar.text(f"Rôle : {role.upper()}")
    
    conn = get_db_connection()
    if not conn:
        return
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    if role == "admin_general":
        cur.execute("select * from tontines")
        tontines = cur.fetchall()
        t_map = {t["name"]: t["id"] for t in tontines} if tontines else {}
        if t_map:
            sel_t = st.sidebar.selectbox("Tontine active", options=list(t_map.keys()))
            current_tontine_id = t_map[sel_t]
        else:
            current_tontine_id = None
    else:
        current_tontine_id = user["tontine_id"]
        if current_tontine_id:
            cur.execute("select name from tontines where id = %s", (current_tontine_id,))
            res_t = cur.fetchone()
            st.sidebar.text(f"Tontine : {res_t['name'] if res_t else 'Inconnue'}")

    cur.close()
    conn.close()

    # Navigation menu
    if role == "admin_general":
        menu = st.sidebar.radio("Navigation", [
            "Tableau de bord", "Administration Générale", "Membres", 
            "Cotisations", "Emprunts & Remboursements", "Fonds & Trésorerie", "Documents & PDF"
        ])
    else:
        menu = st.sidebar.radio("Navigation", [
            "Tableau de bord", "Membres", "Cotisations", 
            "Emprunts & Remboursements", "Fonds & Trésorerie", "Documents & PDF"
        ])
        
    if st.sidebar.button("Se déconnecter"):
        del st.session_state["user"]
        del st.session_state["role"]
        st.rerun()

    # Routage des écrans
    if menu == "Tableau de bord":
        st.title("📊 Tableau de Bord & Indicateurs")
        if current_tontine_id:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("select count(*) as count from members where tontine_id = %s", (current_tontine_id,))
                m_count = cur.fetchone()["count"]
                cur.execute("select count(*) as count from loans where tontine_id = %s and status = 'en_cours'", (current_tontine_id,))
                l_count = cur.fetchone()["count"]
                
                col1, col2 = st.columns(2)
                col1.metric("Membres enregistrés", m_count)
                col2.metric("Emprunts en cours", l_count)
                cur.close()
                conn.close()
        else:
            st.info("Veuillez sélectionner ou créer une tontine active.")
            
    elif menu == "Administration Générale" and role == "admin_general":
        render_admin_module()
    elif menu == "Membres" and current_tontine_id:
        render_members_module(current_tontine_id)
    elif menu == "Cotisations" and current_tontine_id:
        render_cotisations_module(current_tontine_id)
    elif menu == "Emprunts & Remboursements" and current_tontine_id:
        render_emprunts_module(current_tontine_id)
    elif menu == "Fonds & Trésorerie" and current_tontine_id:
        render_fonds_module(current_tontine_id)
    elif menu == "Documents & PDF" and current_tontine_id:
        render_documents_module(current_tontine_id)
    else:
        st.warning("Veuillez configurer une tontine valide.")

if __name__ == "__main__":
    main()
