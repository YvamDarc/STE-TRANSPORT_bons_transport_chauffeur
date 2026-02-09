import streamlit as st
import pandas as pd
import io
import os
from datetime import datetime
import uuid

import dropbox
from dropbox.files import WriteMode

# =========================================================
# STREAMLIT CONFIG (DOIT ÊTRE TOUT EN HAUT)
# =========================================================
st.set_page_config(page_title="Bon de transport", layout="centered")

# =========================================================
# CONFIG DROPBOX PATHS
# =========================================================
APP_ROOT = "/TRANSPORT_APP"  # Racine dans le dossier App Folder Dropbox
MASTER_PATH = f"{APP_ROOT}/00_MASTER"
SOCIETES_PATH = f"{APP_ROOT}/01_SOCIETES"

# =========================================================
# DROPBOX CLIENT (MODE SIMPLE: ACCESS TOKEN)
# =========================================================
@st.cache_resource
def get_dbx() -> dropbox.Dropbox:
    if "DROPBOX_ACCESS_TOKEN" not in st.secrets:
        st.error('Secret manquant : DROPBOX_ACCESS_TOKEN (Streamlit Cloud → Settings → Secrets)')
        st.stop()
    return dropbox.Dropbox(st.secrets["DROPBOX_ACCESS_TOKEN"])

dbx = get_dbx()

# Test connexion (affiche une erreur claire si KO)
try:
    acc = dbx.users_get_current_account()
    st.success(f"✅ Dropbox connecté : {acc.name.display_name}")
except Exception as e:
    st.error("❌ Connexion Dropbox impossible (token invalide ou révoqué).")
    st.exception(e)
    st.stop()

# =========================================================
# DROPBOX HELPERS
# =========================================================
def dbx_exists(path: str) -> bool:
    try:
        dbx.files_get_metadata(path)
        return True
    except Exception:
        return False

def dbx_mkdir(path: str):
    # best effort : ignore si existe
    try:
        dbx.files_create_folder_v2(path)
    except Exception:
        pass

def dbx_download_bytes(path: str) -> bytes:
    _md, res = dbx.files_download(path)
    return res.content

def dbx_upload_bytes(path: str, content: bytes, overwrite: bool = True):
    mode = WriteMode.overwrite if overwrite else WriteMode.add
    dbx.files_upload(content, path, mode=mode, mute=True)

def dbx_read_csv(path: str) -> pd.DataFrame:
    if not dbx_exists(path):
        return pd.DataFrame()
    data = dbx_download_bytes(path)
    return pd.read_csv(io.BytesIO(data), sep=";", dtype=str).fillna("")

def dbx_write_csv(path: str, df: pd.DataFrame):
    buf = io.StringIO()
    df.to_csv(buf, sep=";", index=False)
    dbx_upload_bytes(path, buf.getvalue().encode("utf-8"), overwrite=True)

def dbx_ensure_csv(path: str, header: str):
    """
    Crée le fichier CSV s'il n'existe pas + essaye de créer les dossiers parents.
    """
    if dbx_exists(path):
        return

    parent = os.path.dirname(path).replace("\\", "/")
    if parent and parent != "/":
        parts = parent.split("/")
        curr = ""
        for p in parts:
            if not p:
                continue
            curr += "/" + p
            dbx_mkdir(curr)

    dbx_upload_bytes(path, (header.strip() + "\n").encode("utf-8"), overwrite=True)

def only_active(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "actif" in df.columns:
        return df[df["actif"].astype(str).isin(["1", "true", "TRUE", "True", "OUI", "oui"])].copy()
    return df

def to_options(df: pd.DataFrame, id_col: str, label_col: str):
    if df.empty or id_col not in df.columns or label_col not in df.columns:
        return [], {}
    labels = [f"{row[label_col]} ({row[id_col]})" for _, row in df.iterrows()]
    mapping = {f"{row[label_col]} ({row[id_col]})": row[id_col] for _, row in df.iterrows()}
    return labels, mapping

def get_societe_from_url(allowed):
    qp = st.query_params
    soc = (qp.get("societe", "") or "").strip()
    return soc if soc in allowed else ""

# =========================================================
# SOCIÉTÉS (via fichier master)
# =========================================================
societes_file = f"{MASTER_PATH}/02_PARAMETRES_APP/societes.csv"
societes = dbx_read_csv(societes_file)

allowed_societes = []
if not societes.empty and "societe_code" in societes.columns:
    allowed_societes = societes["societe_code"].tolist()

societe = get_societe_from_url(allowed_societes)
if not societe:
    st.error("Lien invalide : ajoute ?societe=TPRD (ex: https://tonapp.streamlit.app/?societe=TPRD)")
    st.stop()

st.title(f"🚚 Bon de transport — {societe}")
st.caption("Société verrouillée via le lien du chauffeur.")

# =========================================================
# PATHS SOCIÉTÉ
# =========================================================
REF_PATH = f"{SOCIETES_PATH}/{societe}/01_REFERENTIELS"
DATA_PATH = f"{SOCIETES_PATH}/{societe}/02_OPERATIONNEL"
JUSTIF_PATH = f"{SOCIETES_PATH}/{societe}/03_JUSTIFICATIFS"

BT_FILE = f"{DATA_PATH}/bons_transport.csv"

CHAUFFEURS_FILE = f"{REF_PATH}/chauffeurs.csv"
VEHICULES_FILE = f"{REF_PATH}/vehicules.csv"
CLIENTS_FILE = f"{REF_PATH}/clients.csv"
ARTICLES_FILE = f"{REF_PATH}/articles.csv"

# Crée bons_transport si absent
dbx_ensure_csv(
    BT_FILE,
    "bt_id;date;chauffeur_id;vehicule_id;client_id;article_id;depart;arrivee;zone;quantite;duree;options;commentaire;statut;justificatifs_path"
)

# =========================================================
# RÉFÉRENTIELS (Dropbox)
# =========================================================
chauffeurs = only_active(dbx_read_csv(CHAUFFEURS_FILE))
vehicules = only_active(dbx_read_csv(VEHICULES_FILE))
clients = only_active(dbx_read_csv(CLIENTS_FILE))
articles = only_active(dbx_read_csv(ARTICLES_FILE))

chauffeur_labels, chauffeur_map = to_options(chauffeurs, "chauffeur_id", "chauffeur_nom")
vehicule_labels, vehicule_map = to_options(vehicules, "vehicule_id", "immatriculation")
client_labels, client_map = to_options(clients, "client_id", "client_nom")
article_labels, article_map = to_options(articles, "article_id", "libelle")

# =========================================================
# FORMULAIRE
# =========================================================
with st.form("bon_transport"):
    st.subheader("📌 Identification")
    date_transport = st.date_input("Date du transport", value=datetime.today())

    if chauffeur_labels:
        chauffeur_label = st.selectbox("Chauffeur", chauffeur_labels)
        chauffeur_id = chauffeur_map[chauffeur_label]
    else:
        st.warning("Référentiel chauffeurs vide : remplir chauffeurs.csv sur Dropbox.")
        chauffeur_id = st.text_input("Chauffeur (id)")

    if vehicule_labels:
        vehicule_label = st.selectbox("Véhicule", vehicule_labels)
        vehicule_id = vehicule_map[vehicule_label]
    else:
        st.warning("Référentiel véhicules vide : remplir vehicules.csv sur Dropbox.")
        vehicule_id = st.text_input("Véhicule (id)")

    if client_labels:
        client_label = st.selectbox("Client", client_labels)
        client_id = client_map[client_label]
    else:
        st.warning("Référentiel clients vide : créer/remplir clients.csv sur Dropbox.")
        client_id = st.text_input("Client (id)")

    st.subheader("🧾 Prestation (par code article)")
    st.caption("Sélection d’un code article = saisie standardisée.")
    if article_labels:
        article_label = st.selectbox("Code article / Libellé", article_labels)
        article_id = article_map[article_label]
    else:
        st.warning("Référentiel articles vide : remplir articles.csv sur Dropbox.")
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
    fichiers = st.file_uploader(
        "Photos / BL / POD",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True
    )

    submit = st.form_submit_button("✅ Enregistrer le bon")

# =========================================================
# ENREGISTREMENT (Dropbox)
# =========================================================
if submit:
    bt_id = f"BT{datetime.now().strftime('%Y')}-{uuid.uuid4().hex[:6].upper()}"

    year = datetime.now().strftime("%Y")
    month = datetime.now().strftime("%m")
    bt_justif_path = f"{JUSTIF_PATH}/{year}/{month}/{bt_id}"

    # Crée le dossier justificatifs
    dbx_mkdir(bt_justif_path)

    # Upload justificatifs
    for f in fichiers or []:
        dest = f"{bt_justif_path}/{f.name}"
        dbx_upload_bytes(dest, f.getvalue(), overwrite=True)

    # Append au CSV
    df = dbx_read_csv(BT_FILE)

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
        "justificatifs_path": bt_justif_path,
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    dbx_write_csv(BT_FILE, df)

    st.success(f"✅ Bon {bt_id} enregistré sur Dropbox")
    st.info(f"📁 Justificatifs : {bt_justif_path}")
    st.caption(f"📄 CSV : {BT_FILE}")
