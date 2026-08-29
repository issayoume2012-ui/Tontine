import streamlit as st
import bcrypt
import io
import pandas as pd
from datetime import date, datetime
from supabase import create_client, Client
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen致します import canvas # Note: correction of potential typo in some envs, using standard reportlab imports below

# ==========================================
# CONFIGURATION DE LA PAGE STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Gestion de Tontine Pro - Supabase API",
    page_icon="🏦",
    layout="wide"
)

# ==========================================
# CONNEXION SUPABASE CLIENT OFFICIEL
# ==========================================
SUPABASE_URL = "https://db.rrpmbnxmmsoryzyadhaj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey... (Utilisez votre clé anon/service_role de Supabase)" # Ou insérez votre clé anon publique complète directement

@st.cache_resource
def init_supabase() -> Client:
    # Remplacer par votre URL et votre clé publique Supabase (Anon Key)
    url = "https://db.rrpmbnxmmsoryzyadhaj.supabase.co"
    # Attention: Mettez ici votre clé anon ou service_role Supabase (fournie dans votre dashboard Supabase -> Project Settings -> API)
    key = st.secrets["supabase"]["key"] if "supabase" in st.secrets else "VOTRE_SUPABASE_ANON_KEY"
    return create_client(url, key)

# Initialisation simplifiée via l'URL directe et la clé publique Supabase
# Si vous n'utilisez pas st.secrets, remplacez la clé ci-dessous par votre clé anon Supabase réelle
@st.cache_resource
def get_supabase_client() -> Client:
    url = "https://db.rrpmbnxmmsoryzyadhaj.supabase.co"
    # Insérez votre clé publique Supabase (clé anon) ci-dessous si vous ne l'avez pas dans st.secrets
    key = "VOTRE_SUPABASE_ANON_KEY_ICI" 
    return create_client(url, key)

# ==========================================
# FONCTIONS UTILITAIRES & SÉCURITÉ
# ==========================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def log_action(user_id, user_role, tontine_id, action_type, table_name, record_id=None):
    try:
        client = get_supabase_client()
        client.table("audit_logs").insert({
            "user_id": str(user_id) if user_id else None,
            "user_role": user_role,
            "tontine_id": str(tontine_id) if tontine_id else None,
            "action_type": action_type,
            "table_name": table_name,
            "record_id": str(record_id) if record_id else None
        }).execute()
    except Exception as e:
        print(f"Erreur log : {e}")

# ==========================================
# MODULE D'AUTHENTIFICATION
# ==========================================
def render_auth():
    st.subheader("🔐 Connexion à l'application Tontine")
    client = get_supabase_client()
    
    # Vérifier s'il existe des utilisateurs, sinon créer un admin par défaut
    try:
        res = client.table("users").select("id", count="exact").execute()
        if not res.data:
            default_pwd = hash_password("Admin123*")
            client.table("users").insert({
                "email": "admin@tontine.com",
                "password_hash": default_pwd,
                "full_name": "Administrateur Général",
                "role": "admin_general",
                "is_active": True
            }).execute()
    except Exception as e:
        st.warning("Assurez-vous que les tables sont créées dans Supabase (voir l'éditeur SQL Supabase). Erreur: " + str(e))

    with st.form("login_form"):
        email = st.text_input("Adresse Email")
        password = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Se connecter")
        
        if submit:
            if not email or not password:
                st.warning("Veuillez remplir tous les champs.")
                return
            
            try:
                response = client.table("users").select("*").eq("email", email).execute()
                users = response.data
                
                if not users:
                    st.error("Utilisateur introuvable.")
                    return
                
                user = users[0]
                if not user.get("is_active", True):
                    st.error("Ce compte est désactivé.")
                    return
                    
                if verify_password(password, user["password_hash"]):
                    st.session_state["user"] = user
                    st.session_state["role"] = user["role"]
                    st.session_state["tontine_id"] = user.get("tontine_id")
                    log_action(user["id"], user["role"], user.get("tontine_id"), "CONNEXION", "users", user["id"])
                    st.success("Connexion réussie !")
                    st.rerun()
                else:
                    st.error("Mot de passe incorrect.")
            except Exception as e:
                st.error(f"Erreur de connexion : {e}")

# ==========================================
# MODULE ADMINISTRATION GÉNÉRALE
# ==========================================
def render_admin_module():
    st.title("⚙️ Administration Générale")
    tab1, tab2, tab3, tab4 = st.tabs(["Gérants", "Tontines", "Liste Blanche", "Journal d'Audit"])
    client = get_supabase_client()
    
    with tab1:
        st.subheader("Création et Gestion des Gérants")
        tontines_res = client.table("tontines").select("*").execute().data
        tontine_map = {t["name"]: t["id"] for t in tontines_res} if tontines_res else {}
        
        with st.form("create_mgr"):
            name = st.text_input("Nom complet")
            email = st.text_input("Email")
            pwd = st.text_input("Mot de passe temporaire", type="password")
            t_name = st.selectbox("Tontine assignée", options=list(tontine_map.keys()) if tontine_map else [])
            sub = st.form_submit_button("Créer le gérant")
            if sub and t_name:
                try:
                    hashed = hash_password(pwd)
                    t_id = tontine_map[t_name]
                    client.table("users").insert({
                        "email": email,
                        "password_hash": hashed,
                        "full_name": name,
                        "role": "gerant",
                        "tontine_id": t_id,
                        "is_active": True
                    }).execute()
                    st.success("Gérant créé avec succès !")
                except Exception as e:
                    st.error(f"Erreur : {e}")
        
        st.divider()
        managers_res = client.table("users").select("id, full_name, email, is_active, tontine_id").eq("role", "gerant").execute().data
        if managers_res:
            for m in managers_res:
                col1, col2 = st.columns([4, 1])
                col1.write(f"**{m['full_name']}** ({m['email']}) - Actif : {m['is_active']}")
                if col2.button("Activer/Désactiver", key=f"mgr_toggle_{m['id']}"):
                    client.table("users").update({"is_active": not m['is_active']}).eq("id", m['id']).execute()
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
                    client.table("tontines").insert({
                        "code": code,
                        "name": tname,
                        "description": desc,
                        "start_date": str(start),
                        "end_date": str(end),
                        "is_active": True,
                        "is_locked": False
                    }).execute()
                    st.success("Tontine créée avec succès !")
                except Exception as e:
                    st.error(f"Erreur : {e}")

        st.divider()
        tontines_list = client.table("tontines").select("*").execute().data
        if tontines_list:
            for t in tontines_list:
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{t['name']}** (Code: {t['code']}) | Active: {t['is_active']} | Verrouillée: {t['is_locked']}")
                if c2.button("Verrouiller/Déverrouiller", key=f"lock_{t['id']}"):
                    client.table("tontines").update({"is_locked": not t['is_locked']}).eq("id", t['id']).execute()
                    st.rerun()
                if c3.button("Activer/Désactiver", key=f"act_{t['id']}"):
                    client.table("tontines").update({"is_active": not t['is_active']}).eq("id", t['id']).execute()
                    st.rerun()

    with tab3:
        st.subheader("Liste Blanche (Whitelist)")
        with st.form("whitelist"):
            w_email = st.text_input("Email autorisé")
            w_role = st.selectbox("Rôle", ["admin_general", "gerant"])
            sub_w = st.form_submit_button("Ajouter")
            if sub_w:
                try:
                    client.table("whitelist").insert({"email": w_email, "role": w_role}).execute()
                    st.success("Ajouté à la whitelist.")
                except Exception as e:
                    st.error(f"Erreur : {e}")

    with tab4:
        st.subheader("Journal d'Audit & Historique")
        logs = client.table("audit_logs").select("*").order("action_timestamp", desc=True).limit(50).execute().data
        if logs:
            st.dataframe(pd.DataFrame(logs))
        else:
            st.info("Aucun historique disponible.")

# ==========================================
# MODULE MEMBRES
# ==========================================
def render_members_module(tontine_id):
    st.subheader("👥 Gestion des Membres")
    client = get_supabase_client()
    
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
                client.table("members").insert({
                    "tontine_id": tontine_id,
                    "member_code": code,
                    "first_name": fn,
                    "last_name": ln,
                    "phone": phone,
                    "periodicity": period,
                    "indicative_contribution": contrib,
                    "indicative_solidarity": solidarity,
                    "observations": obs,
                    "is_active": True
                }).execute()
                st.success("Membre enregistré avec succès !")
                log_action(st.session_state["user"]["id"], st.session_state["role"], tontine_id, "AJOUT_MEMBRE", "members")
            except Exception as e:
                st.error(f"Erreur : {e}")
                
    st.divider()
    members = client.table("members").select("*").eq("tontine_id", tontine_id).execute().data
    if members:
        st.dataframe(pd.DataFrame(members))
    else:
        st.info("Aucun membre enregistré pour cette tontine.")

# ==========================================
# MODULE COTISATIONS
# ==========================================
def render_cotisations_module(tontine_id):
    st.subheader("💰 Enregistrement des Cotisations")
    client = get_supabase_client()
    
    members = client.table("members").select("id, member_code, first_name, last_name").eq("tontine_id", tontine_id).eq("is_active", True).execute().data
    if not members:
        st.warning("Aucun membre actif disponible.")
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
                client.table("contributions").insert({
                    "tontine_id": tontine_id,
                    "member_id": m_id,
                    "savings_amount": savings,
                    "solidarity_amount": solidarity,
                    "fine_amount": fine,
                    "observation": obs,
                    "recorded_by": st.session_state["user"]["id"]
                }).execute()
                st.success("Cotisation enregistrée avec succès !")
                log_action(st.session_state["user"]["id"], st.session_state["role"], tontine_id, "COTISATION", "contributions")
            except Exception as e:
                st.error(f"Erreur : {e}")

# ==========================================
# MODULE EMPRUNTS & REMBOURSEMENTS
# ==========================================
def render_emprunts_module(tontine_id):
    st.subheader("📊 Gestion des Emprunts & Remboursements")
    client = get_supabase_client()
    
    members = client.table("members").select("id, member_code, first_name, last_name").eq("tontine_id", tontine_id).eq("is_active", True).execute().data
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
                client.table("loans").insert({
                    "tontine_id": tontine_id,
                    "member_id": m_id,
                    "borrowed_amount": amount,
                    "interest_rate": rate,
                    "calculated_interest": interest,
                    "total_to_repay": total,
                    "remaining_amount": total,
                    "due_date": str(due_date),
                    "status": "en_cours",
                    "recorded_by": st.session_state["user"]["id"]
                }).execute()
                
                client.table("funds").insert({
                    "tontine_id": tontine_id,
                    "movement_type": "sortie",
                    "amount": amount,
                    "description": f"Octroi d'emprunt au membre {selected_m}",
                    "recorded_by": st.session_state["user"]["id"]
                }).execute()
                
                st.success("Emprunt accordé et fonds mis à jour avec succès !")
                log_action(st.session_state["user"]["id"], st.session_state["role"], tontine_id, "OCTROI_EMPRUNT", "loans")
            except Exception as e:
                st.error(f"Erreur lors de la transaction : {e}")

# ==========================================
# MODULE FONDS & TRÉSORERIE
# ==========================================
def render_fonds_module(tontine_id):
    st.subheader("💼 Gestion de la Trésorerie & Fonds")
    client = get_supabase_client()
    
    with st.form("fund_form"):
        m_type = st.selectbox("Type de mouvement", ["apport", "sortie", "aide", "interet", "autre"])
        amount = st.number_input("Montant", min_value=0.0, step=500.0)
        desc = st.text_area("Description")
        sub = st.form_submit_button("Enregistrer le mouvement")
        if sub:
            try:
                client.table("funds").insert({
                    "tontine_id": tontine_id,
                    "movement_type": m_type,
                    "amount": amount,
                    "description": desc,
                    "recorded_by": st.session_state["user"]["id"]
                }).execute()
                st.success("Mouvement de fonds enregistré.")
            except Exception as e:
                st.error(f"Erreur : {e}")
                
    st.divider()
    funds = client.table("funds").select("*").eq("tontine_id", tontine_id).order("created_at", desc=True).execute().data
    if funds:
        st.dataframe(pd.DataFrame(funds))

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
    client = get_supabase_client()
    
    members = client.table("members").select("id, member_code, first_name, last_name").eq("tontine_id", tontine_id).execute().data
    m_map = {f"{m['member_code']} - {m['first_name']} {m['last_name']}": m['id'] for m in members} if members else {}
    
    if m_map:
        sel_m = st.selectbox("Choisir un membre", options=list(m_map.keys()))
        if st.button("Générer le relevé PDF"):
            m_id = m_map[sel_m]
            m_info = client.table("members").select("*").eq("id", m_id).single().execute().data
            contribs = client.table("contributions").select("*").eq("member_id", m_id).execute().data
            
            pdf_bytes = generate_pdf_statement(m_info, contribs)
            st.download_button(
                label="Télécharger le PDF",
                data=pdf_bytes,
                file_name=f"fiche_{m_info['member_code']}.pdf",
                mime="application/pdf"
            )
    else:
        st.info("Aucun membre disponible.")

# ==========================================
# INTERFACE PRINCIPALE & ROUTAGE
# ==========================================
def main():
    if "user" not in st.session_state:
        render_auth()
        return
        
    user = st.session_state["user"]
    role = st.session_state["role"]
    client = get_supabase_client()
    
    st.sidebar.title(f"Bienvenue, {user['full_name']}")
    st.sidebar.text(f"Rôle : {role.upper()}")
    
    if role == "admin_general":
        tontines_res = client.table("tontines").select("*").execute().data
        t_map = {t["name"]: t["id"] for t in tontines_res} if tontines_res else {}
        if t_map:
            sel_t = st.sidebar.selectbox("Tontine active", options=list(t_map.keys()))
            current_tontine_id = t_map[sel_t]
        else:
            current_tontine_id = None
    else:
        current_tontine_id = user.get("tontine_id")
        if current_tontine_id:
            res_t = client.table("tontines").select("name").eq("id", current_tontine_id).single().execute().data
            st.sidebar.text(f"Tontine : {res_t['name'] if res_t else 'Inconnue'}")

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
            m_count = len(client.table("members").select("id", count="exact").eq("tontine_id", current_tontine_id).execute().data)
            l_count = len(client.table("loans").select("id", count="exact").eq("tontine_id", current_tontine_id).eq("status", "en_cours").execute().data)
            
            col1, col2 = st.columns(2)
            col1.metric("Membres enregistrés", m_count)
            col2.metric("Emprunts en cours", l_count)
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
