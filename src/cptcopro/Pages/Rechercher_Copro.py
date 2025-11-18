import streamlit as st
import sqlite3
import pandas as pd
from loguru import logger
from pathlib import Path
import plotly.express as px
from typing import List

DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"

@st.cache_data
def load_all_charges_data(db_path: Path) -> pd.DataFrame:
    """Charge toutes les données de charges depuis la vue vw_charge_coproprietaires."""
    sql = "SELECT nom_proprietaire, code_proprietaire, num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires"
    expected_cols = ["proprietaire", "code", "num_apt", "type_apt", "debit", "credit", "date"]
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql_query(sql, conn)
    except sqlite3.Error as e:
        logger.error("Erreur SQLite lors de la lecture des charges: {}", e)
        # Afficher l'erreur dans Streamlit (fonction décorée par @st.cache_data,
        # donc exécutée dans le contexte Streamlit). Ne pas capturer cette
        # erreur localement : laisser l'appel échouer visible pour l'utilisateur.
        st.error(f"Impossible de lire les données de la base: {e}")
        return pd.DataFrame(columns=expected_cols)
    except Exception as e:  # generic fallback
        logger.error("Erreur inattendue lors de la lecture des charges: {}", e)
        st.error(f"Erreur inattendue lors de la lecture des données: {e}")
        return pd.DataFrame(columns=expected_cols)

    # Renommer pour la cohérence avec le reste du code
    df = df.rename(columns={"nom_proprietaire": "proprietaire", "code_proprietaire": "code"})
    # Convertir la date une seule fois
    # Conserver les valeurs originales pour journalisation des valeurs invalides
    orig_dates = df["date"].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    # Comptabiliser les dates invalides (coercées en NaT) et journaliser
    invalid_mask = df["date"].isna()
    n_invalid = int(invalid_mask.sum())
    if n_invalid > 0:
        sample_invalid = orig_dates[invalid_mask].head(3).tolist()
        logger.warning(
            "load_all_charges_data: {} ligne(s) avec 'date' invalide seront supprimées; exemples: {}",
            n_invalid,
            sample_invalid,
        )

    return df.dropna(subset=["date"])


st.set_page_config(page_title="Recherche Info Copropriétaires", layout="wide")
st.title("Recherche Info Copropriétaires")

st.divider()
charges_df = load_all_charges_data(DB_PATH)
proprietaires_df = charges_df[["proprietaire", "code"]].drop_duplicates().reset_index(drop=True)

st.subheader("Recherche informations sur les copropriétaires")
proprietaire_input = st.text_input("Entrez le nom du copropriétaire à rechercher :").strip()

proprietaires_selection: List[str] = []
if proprietaire_input:
    # Filtrer la liste de noms de copropriétaires
    options = [p for p in proprietaires_df["proprietaire"].values if proprietaire_input.lower() in p.lower()]

    if options:
        st.markdown(f"### Résultats pour '{proprietaire_input}':")
        # Afficher les informations uniques pour les propriétaires trouvés
        info_df = charges_df[charges_df["proprietaire"].isin(options)]
        info_df = info_df[["proprietaire", "code", "num_apt", "type_apt"]].drop_duplicates().reset_index(drop=True)
        st.dataframe(info_df)

        # Permettre de sélectionner un ou plusieurs propriétaires parmi les résultats
        # Par défaut rien n'est sélectionné pour éviter de surcharger le graphique
        # Fournir une case à cocher pour "Sélectionner tout" si l'utilisateur
        # souhaite volontairement tout tracer.
        select_all_key = f"select_all_{proprietaire_input}"
        multiselect_key = f"multiselect_{proprietaire_input}"
        if len(options) > 1:
            if len(options) > 20:
                st.info(
                    f"Plus de 20 copropriétaires trouvés ({len(options)}). Par défaut rien n'est sélectionné; "
                    "cochez la case 'Sélectionner tout' pour tout tracer, ou affinez votre recherche pour réduire les résultats."
                )
            # Par défaut rien n'est sélectionné pour éviter de surcharger le graphique.
            # L'utilisateur peut cocher "Sélectionner tout" pour remplir le multiselect.

            # Initialiser la clé de session pour la checkbox et pour le multiselect si nécessaire.
            if select_all_key not in st.session_state:
                st.session_state[select_all_key] = False
            if multiselect_key not in st.session_state:
                st.session_state[multiselect_key] = options if st.session_state[select_all_key] else []

            # Définir un callback qui sera appelé uniquement quand l'utilisateur
            # change explicitement la case "Sélectionner tout". Ainsi on ne
            # modifie le multiselect que sur action explicite et on préserve les
            # sélections manuelles lors des reruns.
            def _on_select_all_change(multi_key: str, opts: list, sel_key: str):
                # lire l'état actuel de la checkbox et appliquer la synchronisation
                if st.session_state.get(sel_key):
                    st.session_state[multi_key] = opts
                else:
                    st.session_state[multi_key] = []

            # Créer la checkbox UNE seule fois avec on_change pour déclencher le callback.
            select_all = st.checkbox(
                f"Sélectionner tout ({len(options)})",
                value=st.session_state[select_all_key],
                key=select_all_key,
                on_change=_on_select_all_change,
                args=(multiselect_key, options, select_all_key),
            )

            proprietaires_selection = st.multiselect(
                "Sélectionnez un ou plusieurs copropriétaires à tracer",
                options=options,
                key=multiselect_key,
            )

            # Si la case "Sélectionner tout" est cochée mais que l'utilisateur
            # modifie manuellement la sélection du multiselect (par ex. désélection
            # d'éléments), alors décocher automatiquement la case au lieu de forcer
            # la sélection complète. Cela permet aux utilisateurs de désélectionner
            # des éléments sans que la case les réactive.
            try:
                current_sel = st.session_state.get(multiselect_key, [])
                if st.session_state.get(select_all_key, False) and set(current_sel) != set(options):
                    st.session_state[select_all_key] = False
            except Exception:
                # Ne pas faire échouer l'UI si session_state change unexpectedly
                pass
        else:
            proprietaires_selection = options
    else:
        st.warning(f"Aucun copropriétaire trouvé avec le nom '{proprietaire_input}'.")
else:
    st.info("Veuillez entrer un nom de copropriétaire pour rechercher.")

st.divider()
st.subheader("Suivi des charges pour le(s) copropriétaire(s) sélectionné(s)")
if proprietaires_selection:
    # Filtrer le DataFrame principal au lieu de faire un appel BDD
    filtered_charges_df = charges_df[charges_df["proprietaire"].isin(proprietaires_selection)]

    if filtered_charges_df.empty:
        st.warning("Aucune charge trouvée pour le(s) copropriétaire(s) sélectionné(s).")
    else:
        # Agréger par date et par propriétaire (somme des debits)
        # Trier par propriétaire puis date ASC pour que les séries temporelles
        # progressent de gauche (ancienne) vers droite (récentes)
        charges_df_sorted = filtered_charges_df.sort_values(["proprietaire", "date"], ascending=[True, True])
        agg = charges_df_sorted.groupby([charges_df_sorted["date"].dt.date, "proprietaire"]).agg({"debit": "sum"}).reset_index()

        # Tracer l'évolution du débit par date (une courbe par propriétaire)
        fig = px.line(agg, x="date", y="debit", color="proprietaire", markers=True)
        fig.update_layout(title="Évolution du débit par date", xaxis_title="Date", yaxis_title="Débit")
        st.plotly_chart(fig, use_container_width=True)

        # Afficher le tableau agrégé
        with st.expander("Tableau agrégé par date et propriétaire", expanded=False):
            st.dataframe(agg.sort_values(by=["date", "proprietaire"], ascending=[True, False]))

else:
    st.info("Aucun propriétaire sélectionné pour le tracé.")
