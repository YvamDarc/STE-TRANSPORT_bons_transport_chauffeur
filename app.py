import streamlit as st
import pandas as pd
import os
from datetime import datetime
import uuid

# =============================
# PARAMÈTRES
# =============================
BASE_PATH = r"C:\Users\mdavy\OneDrive - CAPEOS Solutions\Documents\dropbox\TRANSPORT_APP"

# =============================
# HELPERS
# =============================
def load_csv(path):
    if os.path.exists(path):
        df = pd.read_csv(path, sep=";", dtype=str).fillna("")
        return df
    return pd.DataFrame()

def ensure_file(path: str, header: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(header.strip() + "\n")

def get_societe_from_url(allowed):
    # Streamlit 1.30+ : st.query_params
    qp = st.query_params
    soc = (qp.get("societe", "") or "").strip()
    if soc in allowed:
        return soc
    return ""

# =============================
# UI CONFIG
# =============================
st.set_page_config(page_title="Bon de transport", layout="centered")

# =============================
# CHARGEMENT SOCIÉTÉS
# =============================
societes_file = os.path.join(BASE_PATH, "00_MASTER", "02_PARAMETRES_APP", "societes.csv")
societes = load_csv(societes_file)

allowed_societes = societes["societe_code"].tolist() if not societes.empty else []
societe = get_societe_from_url(allowed_societes)

if not societe:
    st.error("Lien invalide : la société n’est pas définie. Exemple : ?societe=TPRD")
    st.stop()

st.title(f"🚚 Bon de transport — {societe}")
st.caption("La société est verrouillée via le lien du chauffeur.")

# =============================
# PATHS SOCIÉTÉ
# =============================
REF_PATH = os.path.join(BASE_PATH, "01_SOCIETES", societe, "01_REFERENTIELS")
DATA_PATH = os.path.join(BASE_PATH, "01_SOCIETES", societe, "02_OPERATIONNEL")
JUSTIF_PATH = os.path.join(BASE_PATH, "01_SOCIETES", societe, "03_JUSTIFICATIFS")

BT_FILE = os.path.join(DATA_PATH, "bons_transport.csv")

CHAUFFEURS_FILE = os.path.join(REF_PATH, "chauffeurs.csv")
VEHICULES_FILE = os.path.join(REF_PATH, "vehicules.csv")
CLIENTS_FILE = os.path.join(REF_PATH, "clients.csv")         # À CRÉER
ARTICLES_FILE = os.path.join(REF_PATH, "articles.csv")

# S'assurer que bons_transport existe (évite crash)
ensure_file(
    BT_FILE,
    "bt_id;date;chauffeur_id;vehicule_id;client_id;article_id;depart;arrivee;zone;quantite;duree;options;commentaire;statut;justificatifs_path"
)

# =============================
# RÉFÉRENTIELS
# =============================
chauffeurs = load_csv(CHAUFFEURS_FILE)
vehicules = load_csv(VEHICULES_FILE)
clients = load_csv(CLIENTS_FILE)
articles = load_csv(ARTICLES_FILE)

# Filtre actifs si colonnes présentes
def only_active(df):
    if df.empty:
        return df
    if "actif" in df.columns:
        return df[df["actif"].astype(str).isin(["1", "true", "TRUE", "True", "OUI", "oui"])].copy()
    return df

chauffeurs = only_active(chauffeurs)
vehicules = only_active(vehicules)
clients = only_active(clients)
articles = only_active(articles)

# Menus déroulants "label -> id"
def to_options(df, id_col, label_col):
    if df.empty or id_col not in df.columns or label_col not in df.columns:
        return [], {}
    labels = [f"{row[label_col]} ({row[id_col]})" for _, row in df.iterrows()]
    map_label_to_id = {f"{row[label_col]} ({row[id_col]})": row[id_col] for _, row in df.iterrows()}
    return labels, map_label_to_id

chauffeur_labels, chauffeur_map = to_options(chauffeurs, "chauffeur_id", "chauffeur_nom")
vehicule_labels, vehicule_map = to_options(vehicules, "vehicule_id", "immatriculation")
client_labels, client_map = to_options(clients, "client_id", "client_nom")
article_labels, article_map = to_options(articles, "article_id", "libelle")

# =============================
# FORMULAIRE
# =============================
with st.form("bon_transport"):

    st.subheader("📌 Identification")
    date_transport = st.date_input("Date du transport", value=datetime.today())

    if chauffeur_labels:
        chauffeur_label = st.selectbox("Chauffeur", chauffeur_labels)
        chauffeur_id = chauffeur_map[chauffeur_label]
    else:
        st.warning("Référentiel chauffeurs vide : remplir chauffeurs.csv")
        chauffeur_id = st.text_input("Chauffeur (id)")

    if vehicule_labels:
        vehicule_label = st.selectbox("Véhicule", vehicule_labels)
        vehicule_id = vehicule_map[vehicule_label]
    else:
        st.warning("Référentiel véhicules vide : remplir vehicules.csv")
        vehicule_id = st.text_input("Véhicule (id)")

    if client_labels:
        client_label = st.selectbox("Client", client_labels)
        client_id = client_map[client_label]
    else:
        st.warning("Référentiel clients vide : créer clients.csv")
        client_id = st.text_input("Client (id)")

    st.subheader("🧾 Prestation (par code article)")
    st.caption("Sélectionne un code article : ça standardise et évite les erreurs.")

    if article_labels:
        article_label = st.selectbox("Code article / Libellé", article_labels)
        article_id = article_map[article_label]
    else:
        st.warning("Référentiel articles vide : remplir articles.csv")
        article_id = st.text_input("Article (id)")

    st.subheader("🏗️ Détails transport")
    depart = st.text_input("Ville de départ")
    arrivee = st.text_input("Ville d’arrivée")
    zone = st.selectbox("Zone", ["", "Z1","Z2","Z3","Z4","Z5","Z6","Z7","Z8","Z9","Z10"])

    quantite = st.number_input("Quantité (ex : m³ / nb)", min_value=0.0, step=0.1)
    duree = st.number_input("Durée sur site (heures)", min_value=0.0, step=0.25)

    st.subheader("➕ Options")
    barbotine = st.checkbox("Barbotine")
    tuyaux = st.checkbox("Tuyaux > 20 ml")
    attente = st.number_input("Attente (minutes)", min_value=0, step=5)
    heures_sup = st.number_input("Heures supplémentaires", min_value=0.0, step=0.25)

    commentaire = st.text_area("Commentaire")

    st.subheader("📷 Justificatifs")
    fichiers = st.file_uploader("Photos / BL / POD", type=["jpg", "jpeg", "png", "pdf"], accept_multiple_files=True)

    submit = st.form_submit_button("✅ Enregistrer le bon")

# =============================
# ENREGISTREMENT
# =============================
if submit:
    bt_id = f"BT{datetime.now().strftime('%Y')}-{uuid.uuid4().hex[:6].upper()}"

    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")

    bt_justif_path = os.path.join(JUSTIF_PATH, year, month, bt_id)
    os.makedirs(bt_justif_path, exist_ok=True)

    # Sauvegarde justificatifs
    for f in fichiers or []:
        with open(os.path.join(bt_justif_path, f.name), "wb") as out:
            out.write(f.read())

    # Lecture existant + append (robuste)
    df = load_csv(BT_FILE)

    new_row = {
        "bt_id": bt_id,
        "date": date_transport.strftime("%Y-%m-%d"),
        "chauffeur_id": chauffeur_id,
        "vehicule_id": vehicule_id,
        "client_id": client_id,
        "article_id": article_id,
        "depart": depart,
        "arrivee": arrivee,
        "zone": zone,
        "quantite": str(quantite),
        "duree": str(duree),
        "options": f"barbotine={barbotine}|tuyaux={tuyaux}|attente={attente}|heures_sup={heures_sup}",
        "commentaire": commentaire,
        "statut": "SAISI",
        "justificatifs_path": bt_justif_path
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(BT_FILE, sep=";", index=False)

    st.success(f"✅ Bon {bt_id} enregistré")
    st.info(f"📁 Justificatifs : {bt_justif_path}")
