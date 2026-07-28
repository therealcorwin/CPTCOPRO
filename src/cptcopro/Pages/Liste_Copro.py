import streamlit as st
import sqlite3
import loguru
from pathlib import Path
import pandas as pd

# Import du module de chemins portables
try:
    from cptcopro.utils.paths import get_db_path
    from cptcopro.utils.privacy import appliquer_confidentialite, is_privacy_enabled

    DB_PATH = get_db_path()
except ImportError:
    # Fallback pour le mode développement
    DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"
    from cptcopro.utils.privacy import appliquer_confidentialite, is_privacy_enabled

CONSOLE_OUTPUT = False
if CONSOLE_OUTPUT:
    pd.set_option("display.max_rows", None)


def _get_db_cache_key(db_path: Path) -> int:
    try:
        return db_path.stat().st_mtime_ns
    except OSError:
        return 0


@st.cache_data(ttl=300)  # Cache expires after 5 minutes
def affiche_copro(db_path: Path, db_cache_key: int) -> pd.DataFrame:
    del db_cache_key
    try:
        with sqlite3.connect(db_path) as conn:
            requete = "SELECT nom_proprietaire AS Proprietaire, code_proprietaire AS Code, type_apt AS Type, num_apt AS Numero,last_check AS Date FROM coproprietaires"
            liste_coproprietaires = pd.read_sql_query(requete, conn)
        return liste_coproprietaires
    except sqlite3.Error as e:
        loguru.logger.error(f"Database error: {e}")
        raise
    except Exception as e:
        loguru.logger.error(f"Unexpected error loading data: {e}")
        raise


loguru.logger.info("Starting Streamlit app for coproprietaires display")
db_cache_key = _get_db_cache_key(DB_PATH)
df = affiche_copro(DB_PATH, db_cache_key)
st.title("Liste des copropriétaires")

# Indicateur de statut de confidentialité
if is_privacy_enabled():
    st.info("🔒 Mode confidentiel actif")

gauche, centre, droite, droite2 = st.columns(4, gap=24)

with gauche:
    proprietaires = st.multiselect(
        "Filtrer par copropriétaire",
        options=df["Proprietaire"].unique(),
        default=df["Proprietaire"].unique(),
        key="liste_copro_proprietaires",
    )
with centre:
    code = st.multiselect(
        "Filtrer par code",
        options=df["Code"].unique(),
        default=df["Code"].unique(),
        key="liste_copro_codes",
    )
with droite:
    type_apt = st.multiselect(
        "Filtrer par type d'appartement",
        options=df["Type"].unique(),
        default=df["Type"].unique(),
        key="liste_copro_types",
    )
with droite2:
    numero_apt = st.multiselect(
        "Filtrer par numéro d'appartement",
        options=df["Numero"].unique(),
        default=df["Numero"].unique(),
        key="liste_copro_numeros",
    )

# Pour afficher le dataframe complet dans Streamlit avec une hauteur dynamique,
# On calcule le nombre de lignes du dataframe (+ 1 pour l'en-tête) * nbre pixels en hauteurs par ligne.
# height = (len(df) + 1) * 35
# st.dataframe(df, height=height, use_container_width=True)
df_filtre = df.query(
    "Proprietaire == @proprietaires & Code == @code & Type == @type_apt & Numero == @numero_apt"
)
st.dataframe(appliquer_confidentialite(df_filtre), width="stretch", hide_index=True)
