"""Page de configuration des seuils d'alerte par type d'appartement.

Cette page permet de visualiser et modifier les seuils d'alerte configurés
pour chaque type d'appartement (2p, 3p, 4p, 5p).

Les alertes sont déclenchées lorsque le débit d'un copropriétaire dépasse
le seuil configuré pour son type d'appartement.
"""
import sqlite3
import pandas as pd
import streamlit as st
from pathlib import Path

# Import du module de chemins portables
try:
    from cptcopro.utils.paths import get_db_path
    from cptcopro.Database import (
        get_config_alertes,
        update_config_alerte,
        DEFAULT_ALERT_THRESHOLDS,
        DEFAULT_THRESHOLD_FALLBACK,
    )
    DB_PATH = get_db_path()
except ImportError:
    # Fallback pour le mode développement
    DB_PATH = Path(__file__).parent.parent / "BDD" / "test.sqlite"
    # Valeurs par défaut si import échoue
    DEFAULT_ALERT_THRESHOLDS = {
        "2p": {"charge_moyenne": 1500.0, "taux": 1.33, "threshold": 2000.0},
        "3p": {"charge_moyenne": 1800.0, "taux": 1.33, "threshold": 2400.0},
        "4p": {"charge_moyenne": 2100.0, "taux": 1.33, "threshold": 2800.0},
        "5p": {"charge_moyenne": 2400.0, "taux": 1.33, "threshold": 3200.0},
    }
    DEFAULT_THRESHOLD_FALLBACK = 2000.0
    
    def get_config_alertes(db_path):
        """Fallback pour récupérer la config."""
        conn = sqlite3.connect(str(db_path))
        try:
            df = pd.read_sql_query("SELECT * FROM config_alerte ORDER BY type_apt", conn)
            return df.to_dict('records')
        except Exception:
            return []
        finally:
            conn.close()
    
    def update_config_alerte(db_path, type_apt, charge_moyenne=None, taux=None, threshold=None):
        """Fallback pour mettre à jour la config."""
        try:
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            cur.execute(
                """UPDATE config_alerte 
                   SET charge_moyenne = COALESCE(?, charge_moyenne),
                       taux = COALESCE(?, taux),
                       threshold = COALESCE(?, threshold),
                       last_update = CURRENT_DATE
                   WHERE type_apt = ?""",
                (charge_moyenne, taux, threshold, type_apt.lower())
            )
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            st.exception(Exception())
            return False
        finally:
            conn.close()


def load_config() -> pd.DataFrame:
    """Charge la configuration des alertes depuis la base de données."""
    try:
        config = get_config_alertes(str(DB_PATH))
        if config:
            df = pd.DataFrame(config)
            # Renommer les colonnes pour l'affichage
            df = df.rename(columns={
                'type_apt': 'Type Apt',
                'charge_moyenne': 'Charge Moyenne (€)',
                'taux': 'Taux',
                'threshold': 'Seuil Alerte (€)',
                'last_update': 'Dernière MAJ'
            })
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erreur lors du chargement de la configuration : {e}")
        return pd.DataFrame()


def save_config(type_apt: str, charge_moyenne: float, taux: float, threshold: float) -> bool:
    """Sauvegarde la configuration pour un type d'appartement."""
    try:
        return update_config_alerte(
            str(DB_PATH),
            type_apt,
            charge_moyenne=charge_moyenne,
            taux=taux,
            threshold=threshold
        )
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")
        return False


# Configuration de la page
st.set_page_config(page_title="Configuration Alertes", layout="wide")
st.title("⚙️ Configuration des Seuils d'Alerte")

st.markdown("""
Cette page permet de configurer les seuils d'alerte par type d'appartement.
Une alerte est déclenchée lorsque le débit d'un copropriétaire dépasse le seuil
configuré pour son type d'appartement.

**Formule du seuil** : `Seuil = Charge Moyenne × Taux`
""")

# Charger la configuration actuelle
config_df = load_config()

if config_df.empty:
    st.warning("⚠️ Aucune configuration trouvée. Veuillez d'abord initialiser la base de données.")
else:
    # Afficher la configuration actuelle
    st.subheader("📊 Configuration Actuelle")
    
    # Filtrer pour n'afficher que les types d'appartement (pas 'default')
    display_df = config_df[config_df['Type Apt'] != 'default'].copy()
    default_row = config_df[config_df['Type Apt'] == 'default']
    
    # Afficher le tableau
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Type Apt": st.column_config.TextColumn("Type", width="small"),
            "Charge Moyenne (€)": st.column_config.NumberColumn(
                "Charge Moyenne (€)",
                format="%.2f €",
                width="medium"
            ),
            "Taux": st.column_config.NumberColumn(
                "Taux",
                format="%.2f",
                width="small"
            ),
            "Seuil Alerte (€)": st.column_config.NumberColumn(
                "Seuil Alerte (€)",
                format="%.2f €",
                width="medium"
            ),
            "Dernière MAJ": st.column_config.DateColumn(
                "Dernière MAJ",
                width="medium"
            ),
        }
    )
    
    # Afficher le seuil par défaut
    if not default_row.empty:
        st.info(f"🔄 **Seuil par défaut** (pour types non configurés) : **{default_row['Seuil Alerte (€)'].values[0]:.2f} €**")

    st.divider()
    
    # Formulaire de modification
    st.subheader("✏️ Modifier un Seuil")
    
    # Sélection du type à modifier
    types_disponibles = display_df['Type Apt'].tolist()
    if 'default' not in types_disponibles:
        types_disponibles.append('default')
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        type_selectionne = st.selectbox(
            "Type d'appartement",
            options=types_disponibles,
            format_func=lambda x: f"{x.upper()}" if x != 'default' else "Par défaut"
        )
    
    # Récupérer les valeurs actuelles pour le type sélectionné
    if type_selectionne == 'default':
        current_row = default_row
    else:
        current_row = display_df[display_df['Type Apt'] == type_selectionne]
    
    if not current_row.empty:
        current_charge = float(current_row['Charge Moyenne (€)'].values[0])
        current_taux = float(current_row['Taux'].values[0])
        current_threshold = float(current_row['Seuil Alerte (€)'].values[0])
    else:
        # Valeurs par défaut
        current_charge = DEFAULT_THRESHOLD_FALLBACK
        current_taux = 1.33
        current_threshold = DEFAULT_THRESHOLD_FALLBACK
    
    with col2:
        st.markdown(f"**Valeurs actuelles pour {type_selectionne.upper()}** : "
                   f"Charge moyenne = {current_charge:.2f} €, "
                   f"Taux = {current_taux:.2f}, "
                   f"Seuil = {current_threshold:.2f} €")
    
    # Formulaire de saisie
    with st.form("form_modifier_seuil"):
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            new_charge = st.number_input(
                "Charge Moyenne (€)",
                min_value=0.0,
                max_value=10000.0,
                value=current_charge,
                step=50.0,
                help="Charge moyenne observée pour ce type d'appartement"
            )
        
        with col_b:
            new_taux = st.number_input(
                "Taux multiplicateur",
                min_value=1.0,
                max_value=3.0,
                value=current_taux,
                step=0.05,
                help="Coefficient multiplicateur (ex: 1.33 = 33% au-dessus de la moyenne)"
            )
        
        with col_c:
            # Calculer automatiquement le seuil
            calculated_threshold = new_charge * new_taux
            new_threshold = st.number_input(
                "Seuil d'Alerte (€)",
                min_value=0.0,
                max_value=20000.0,
                value=calculated_threshold,
                step=50.0,
                help="Seuil au-delà duquel une alerte est déclenchée"
            )
        
        # Aperçu du calcul
        st.markdown(f"📐 **Calcul automatique** : {new_charge:.2f} € × {new_taux:.2f} = **{calculated_threshold:.2f} €**")
        
        submitted = st.form_submit_button("💾 Enregistrer les modifications", type="primary")
        
        if submitted:
            success = save_config(type_selectionne, new_charge, new_taux, new_threshold)
            if success:
                st.success(f"✅ Configuration pour '{type_selectionne.upper()}' mise à jour avec succès!")
                st.rerun()
            else:
                st.error("❌ Erreur lors de la sauvegarde. Vérifiez les logs.")

    st.divider()
    
    # Section d'aide
    with st.expander("ℹ️ Aide sur la configuration des alertes"):
        st.markdown("""
        ### Comment fonctionnent les alertes ?
        
        1. **Charge Moyenne** : C'est la charge typique observée pour un type d'appartement.
           Plus l'appartement est grand, plus la charge est élevée.
        
        2. **Taux** : C'est le coefficient multiplicateur qui détermine à partir de 
           quel pourcentage au-dessus de la moyenne une alerte doit être déclenchée.
           - Taux 1.33 = alerte si débit > 133% de la charge moyenne
           - Taux 1.50 = alerte si débit > 150% de la charge moyenne
        
        3. **Seuil** : C'est le montant en euros à partir duquel une alerte est créée.
           Il est calculé automatiquement : `Seuil = Charge Moyenne × Taux`
        
        ### Types d'appartement
        
        | Type | Description |
        |------|-------------|
        | 2P | 2 pièces (T2) |
        | 3P | 3 pièces (T3) |
        | 4P | 4 pièces (T4) |
        | 5P | 5 pièces et plus (T5+) |
        | Default | Seuil utilisé si le type n'est pas renseigné |
        
        ### Recommandations
        
        - Ajustez les seuils en fonction de l'historique des charges de votre copropriété
        - Un taux de 1.33 (33% au-dessus de la moyenne) est un bon point de départ
        - Surveillez les alertes pendant quelques mois et ajustez si nécessaire
        """)
