## But rapide

Ce dépôt extrait et stocke le "solde des copropriétaires" et la liste des lots depuis un extranet (Playwright), parse le HTML (selectolax) et écrit dans une base SQLite locale. Ce fichier donne aux agents IA l'essentiel pour être productifs rapidement.

## Points d'entrée et architecture

### Orchestration principale
- **Point d'entrée** : `src/cptcopro/main.py` — orchestre la récupération HTML parallèle, le parsing, l'affichage et la sauvegarde en base.

### Parsing HTML (Playwright) - Architecture à 3 modules
- **`src/cptcopro/Parsing_Commun.py`** : Orchestration parallèle et authentification
  - `recup_all_html_parallel()` : Lance 2 navigateurs en parallèle (charges + lots)
  - `_recup_html_generic()` : Fonction générique pour browser/login/navigation
  - `login_and_open_menu()` : Connexion et ouverture du menu
  - Délai de 800ms entre les connexions pour éviter les conflits serveur
- **`src/cptcopro/Parsing_Charge_Copro.py`** : Navigation spécifique pour les charges
  - `recup_charges_coproprietaires(page)` : Clique sur le lien solde et récupère le HTML
- **`src/cptcopro/Parsing_Lots_Copro.py`** : Navigation spécifique pour les lots
  - `recup_lots_coproprietaires(page)` : Clique sur le lien liste et récupère le HTML

### Traitement et parsing HTML (selectolax)
- **`src/cptcopro/Traitement_Charge_Copro.py`** : Parsing des charges
  - `recuperer_date_situation_copro()` : Extrait la date depuis `td#lzA1`
  - `recuperer_situation_copro()` : Extrait le tableau depuis `table#ctzA1`
  - `afficher_etat_coproprietaire()` : Affichage rich dans la console
- **`src/cptcopro/Traitement_Lots_Copro.py`** : Parsing des lots
  - `extraire_lignes_brutes()` : Extrait les lignes du HTML
  - `consolider_proprietaires_lots()` : Associe propriétaires et lots (vérifie 64 copropriétaires)
  - `afficher_avec_rich()` : Affichage rich dans la console

### Persistance SQLite
- **`src/cptcopro/Data_To_BDD.py`** : Opérations base de données
  - Tables : `charge`, `alertes_debit_eleve`, `coproprietaires`, `suivi_alertes`, `config_alerte`
  - `integrite_db()` : Création/vérification des tables et triggers
  - `enregistrer_donnees_sqlite()` : INSERT des charges
  - `enregistrer_coproprietaires()` : INSERT des copropriétaires
  - `sauvegarder_nombre_alertes()` : Mise à jour de la table suivi_alertes
  - `get_config_alertes()` / `update_config_alerte()` : Gestion des seuils d'alerte par type d'appartement
- **`src/cptcopro/Dedoublonnage.py`** : Nettoyage des doublons
  - `analyse_doublons()` : Détecte les doublons par (nom_proprietaire, date)
  - `suppression_doublons()` : Supprime les doublons détectés
  - `rapport_doublon()` : Génère des rapports CSV dans `Rapports/`

### Système d'alertes
- **Table `config_alerte`** : Seuils configurables par type d'appartement (2p, 3p, 4p, 5p)
  - `type_apt` : Type d'appartement (clé primaire)
  - `charge_moyenne` : Charge moyenne pour ce type
  - `taux` : Coefficient multiplicateur (ex: 1.33 = 33% au-dessus de la moyenne)
  - `threshold` : Seuil d'alerte calculé (charge_moyenne × taux)
- **Triggers dynamiques** : Les triggers consultent `config_alerte` via jointure avec `coproprietaires.type_apt`
- **Page Streamlit** : `Pages/Config_Alertes.py` permet de visualiser/modifier les seuils

### Utilitaires
- **`src/cptcopro/utils/paths.py`** : Gestion des chemins portables (dev/PyInstaller)
- **`src/cptcopro/utils/env_loader.py`** : Chargement du fichier `.env`
- **`src/cptcopro/utils/browser_launcher.py`** : Lancement navigateur avec fallback (Edge→Chrome→Firefox)
- **`src/cptcopro/utils/streamlit_launcher.py`** : Lancement de l'interface Streamlit
- **`src/cptcopro/Backup_DB.py`** : Sauvegarde de la base dans `BACKUP/`

### Interface utilisateur
- **`src/cptcopro/Affichage_Stream.py`** : Application Streamlit pour visualiser les données

## Dépendances et environnement

- **Python requis** : `>=3.12,<3.14` (défini dans `pyproject.toml`)
- **Dépendances principales** : `loguru`, `selectolax`, `pandas`, `plotly`, `rich`, `dotenv`, `playwright`, `streamlit`
- **Variables d'environnement** (ou `.env`) nécessaires :
  - `login_site_copro` : Identifiant de connexion
  - `password_site_copro` : Mot de passe
  - `url_site_copro` : URL du site du syndic

### Exécution locale

```powershell
# Avec Poetry (recommandé)
poetry install
poetry run playwright install
poetry run python -m cptcopro.main

# Ou avec venv
$env:PYTHONPATH = 'src'
python -m cptcopro.main
```

## Patterns et conventions

- **Sélecteurs CSS** : date → `td#lzA1` ; tableau charges → `table#ctzA1`
- **Codes d'erreur** : Les fonctions de parsing retournent des codes `KO_*` en cas d'échec
- **Logging** : Chaque module utilise `logger.bind(type_log="NOM_MODULE")` pour classifier les logs
- **Connexions SQLite** : Pattern `try/finally` simple, chaque fonction gère sa propre connexion

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `CPTCOPRO_DB_PATH` | Chemin de la base de données | `src/cptcopro/coproprietaires.sqlite` |
| `CPTCOPRO_LOG_LEVEL` | Niveau de log | `INFO` |
| `CPTCOPRO_LOG_FILE` | Fichier de log | `logs/app.log` |

> Note : Les anciennes variables `CTPCOPRO_*` (avec faute de frappe) restent supportées pour compatibilité.

## CLI

```powershell
python -m cptcopro.main [OPTIONS]

Options:
  --no-headless     Lance Playwright en mode visible (debug)
  --db-path PATH    Surcharge le chemin de la base de données
  --no-serve        Ne pas lancer Streamlit après le traitement
  --show-console    Afficher les données dans la console (rich)
```

## Fichiers à consulter rapidement

| Fichier | Rôle |
|---------|------|
| `pyproject.toml` | Dépendances, version Python |
| `src/cptcopro/main.py` | Orchestration principale |
| `src/cptcopro/Parsing_Commun.py` | Authentification, parsing parallèle |
| `src/cptcopro/Traitement_Charge_Copro.py` | Parsing HTML des charges |
| `src/cptcopro/Traitement_Lots_Copro.py` | Parsing HTML des lots |
| `src/cptcopro/Data_To_BDD.py` | Opérations SQLite |
| `reports/call_graph.md` | Graphe des appels de fonctions |
