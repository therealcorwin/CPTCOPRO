## But rapide

Ce dépôt récupère les charges et les lots depuis un extranet via Playwright, parse le HTML, puis persiste les données dans SQLite. Ce fichier doit rester un guide court: utiliser le code source et reports/call_graph.md pour les détails.

## Points d'entrée et architecture

### Orchestration principale
- **Point d'entrée** : `src/cptcopro/main.py` — orchestre la récupération HTML, le parsing, la persistance SQLite, les backups pCloud et le lancement optionnel de Streamlit.
- **Flux principal** : validation `.env`, récupération HTML parallèle, parsing charges/lots, restauration pCloud si nécessaire, sauvegarde SQLite, mise à jour `suivi_alertes`, backup pCloud optionnel, puis lancement de Streamlit.

### Parsing HTML (Playwright) - Architecture à 3 modules
- **`src/cptcopro/Parsing/Commun.py`** : orchestration parallèle, authentification et logique commune de navigation.
- **`src/cptcopro/Parsing/Charge_Copro.py`** : navigation spécifique vers la page des charges.
- **`src/cptcopro/Parsing/Lots_Copro.py`** : navigation spécifique vers la page des lots.

### Traitement et parsing HTML (selectolax)
- **`src/cptcopro/Traitement/Charge_Copro.py`** : extraction de la date et du tableau des charges.
- **`src/cptcopro/Traitement/Lots_Copro.py`** : extraction et consolidation des propriétaires et lots.

### Persistance Base de Données
- **Package principal** : `src/cptcopro/Database/`
- Modules à connaître : `Creation_BDD.py`, `Charges_To_BDD.py`, `Coproprietaires_To_BDD.py`, `Alertes_Config.py`, `Backup_DB.py`, `Backup_DB_Pcloud.py`, `Relance_Config.py`, `Relance_Templates.py`.
- Tables clés : `charge`, `alertes_debit_eleve`, `coproprietaires`, `suivi_alertes`, `config_alerte`, `relance_config`, `relance_destinataire`, `relance_draft`, `relance_template`.

### Système d'alertes
- **Table `config_alerte`** : seuils configurables par type d'appartement.
- **Triggers dynamiques** : s'appuient sur `config_alerte` et `coproprietaires.type_apt`.
- **UI associée** : `src/cptcopro/Pages/Config_Alertes.py` permet de consulter et modifier les seuils.

### Relances email
- `Database/Relance_Config.py` gère la configuration, les destinataires, les échéances et les brouillons.
- `Database/Relance_Templates.py` gère les modèles statiques ou guidés par LLM.
- `utils/relance_mailer.py` génère les messages et les dépose en brouillon IMAP avec OAuth2 ou mot de passe.
- Pages associées : `Relance.py`, `Relance_Drafts.py`, `Relance_Config.py`, `Relance_Templates.py`, `Relance_Admin.py`.

### Utilitaires
- **`src/cptcopro/utils/paths.py`** : chemins portables et résolution du chemin de base.
- **`src/cptcopro/utils/env_loader.py`** : chargement des variables d'environnement.
- **`src/cptcopro/utils/browser_launcher.py`** : lancement navigateur avec fallback.
- **`src/cptcopro/utils/streamlit_launcher.py`** : lancement Streamlit en subprocess ou in-process.
- **Comportement des chemins** : en dev, les données persistantes vivent sous `src/cptcopro/` (`BDD/`, `logs/`, `Backup/`) ; en bundle PyInstaller, elles vivent à côté de l'exécutable.

### Interface utilisateur
- **`src/cptcopro/Affichage_Stream.py`** : navigation multi-pages Streamlit.
- Pages principales : Dashboard, Liste Charge, Liste Copro, Courbe Charge, Alerte, Stat Alerte, Statistiques Avancées, Config Alertes, Recherche Copro.

## Dépendances et environnement

- **Python requis** : `>=3.12,<3.14` (défini dans `pyproject.toml`)
- **Dépendances principales** : `loguru`, `selectolax`, `pandas`, `plotly`, `rich`, `python-dotenv`, `playwright`, `streamlit`, `streamlit-extras`
- **Variables d'environnement** (ou `.env`) requises au démarrage (voir `REQUIRED_STARTUP_ENV_VARS` dans `env_loader.py`) :
  - Core site copro : `login_site_copro`, `password_site_copro`, `url_site_copro`, `url_situation_copro`
  - pCloud : `pcloud_APP_KEY`, `pcloud_APP_SECRET`, `pcloud_location_id`, `pcloud_backup_folder`, `pcloud_backup_folder_id`, `pcloud_backup_file`
  - MariaDB : `MARIADB_HOST`, `MARIADB_PORT`, `MARIADB_USER`, `MARIADB_PASSWORD`, `MARIADB_DATABASE`
  - Optionnel Relances : `MISTRAL_API_KEY`, `RELANCE_MAILBOX_PASSWORD`, `MS_CLIENT_ID`
  - Toutes documentées dans `src/cptcopro/.env.example` (un test dédié vérifie que cette liste et le fichier restent synchronisés)

### Emplacement et chargement du `.env`

- **Exécution normale** : le démarrage valide et charge les variables depuis un `.env` à la racine du projet.
- **PyInstaller** : le `.env` est attendu à côté de l'exécutable.
- **`utils.env_loader` est le point d'entrée unique** pour charger/valider le `.env` (`utils.paths.init_env()` a été supprimé) ; la résolution du chemin (`paths.get_env_file_path()`) reste dans `paths.py` et est réutilisée par `env_loader`.
- **Chargement en cache** : le fichier `.env` n'est lu/parsé qu'une seule fois par processus (flag `_env_loaded` dans `env_loader.py`) ; chaque appelant continue de valider ses propres clés requises à chaque appel, sans relire le fichier.
- **Ordre d'import important dans `main.py`** : `validate_startup_env()` doit être appelé avant d'importer tout module applicatif (ex. `Backup_DB_Pcloud`) qui lit le `.env` au niveau module — sinon une erreur partielle (clés d'un seul sous-module) masquerait la liste complète des clés manquantes.

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
- **Connexions SQLite** : helpers dédiés dans `Database/`, avec fermeture explicite ou context manager selon le module

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `CPTCOPRO_DB_NAME` | Nom du fichier SQLite si `CPTCOPRO_DB_PATH` n'est pas défini | `coproprietaires.sqlite` |
| `CPTCOPRO_DB_PATH` | Chemin de la base de données | `src/cptcopro/BDD/coproprietaires.sqlite` |
| `CPTCOPRO_LOG_FILE` | Fichier de log | `logs/app.log` |

> Note : `CPTCOPRO_LOG_LEVEL` est documenté historiquement mais n'est pas utilisé par le code actuel.

## CLI

```powershell
python -m cptcopro.main [OPTIONS]

Options:
  --no-headless     Lance Playwright en mode visible (debug)
  --no-serve        Ne pas lancer Streamlit après le traitement
  --serve-port N    Port Streamlit (défaut: 8501)
  --serve-host HOST Host Streamlit (défaut: 127.0.0.1)
  --serve-python P  Interpréteur Python pour lancer Streamlit
  --streamlit-no-browser
  --streamlit-no-console
  --streamlit-use-cmd-start
  --streamlit-log-file FILE
  --show-console    Afficher les données dans la console (rich)
  --no-backup       Ne pas envoyer de backup sur pCloud après l'écriture
  --deco-pcloud     Se déconnecter de pCloud et supprimer le token local
```

## Limitations et comportements utiles

- Les erreurs de parsing remontent sous forme de codes `KO_*` centralisés dans `src/cptcopro/Parsing/constants.py`.
- Le détail du flux d'appel et des pages Streamlit est maintenu dans `reports/call_graph.md`.
- `tests/test_env_example_sync.py` échoue si une variable de `REQUIRED_STARTUP_ENV_VARS` n'est pas documentée dans `.env.example` ; `tests/test_env_loader.py::TestEnvLoadedOnlyOnce` verrouille le chargement unique du `.env`.

## Fichiers à consulter rapidement

| Fichier | Rôle |
|---------|------|
| `pyproject.toml` | Dépendances, version Python |
| `src/cptcopro/main.py` | Orchestration principale |
| `src/cptcopro/Parsing/Commun.py` | Authentification, parsing parallèle |
| `src/cptcopro/Traitement/Charge_Copro.py` | Parsing HTML des charges |
| `src/cptcopro/Traitement/Lots_Copro.py` | Parsing HTML des lots |
| `src/cptcopro/Database/__init__.py` | API publique du package Database |
| `src/cptcopro/utils/paths.py` | Résolution des chemins DB/logs/backup |
| `src/cptcopro/utils/env_loader.py` | Chargement/validation unique du `.env` |
| `src/cptcopro/Parsing/constants.py` | Codes d'erreur et timings Playwright |
| `reports/call_graph.md` | Graphe des appels de fonctions |

## graphify

For any question about this repo's architecture, structure, components, or how to add/modify/find
code, your first action should be `graphify query "<question>"` when `graphify-out/graph.json`
exists. Use `graphify path "<A>" "<B>"` for relationship questions and `graphify explain "<concept>"`
for focused-concept questions. These return a scoped subgraph, usually much smaller than the full
report or raw grep output.

Before every Graphify command, signal activity in PowerShell:

```powershell
New-Item -ItemType Directory -Force graphify-out | Out-Null
New-Item -ItemType File -Force graphify-out/.graphify-activity | Out-Null
```

Use `graphify update .` only after significant changes (5+ files, merge/pull), when the graph is
stale, or on explicit request. Warn before this potentially long operation. Do not run concurrent
updates; `graphify-out/` is generated local state and must remain ignored by Git.

Triggers: "how do I…", "where is…", "what does … do", "add/modify a <component>",
"explain the architecture", or anything that depends on how files or classes relate.

If `graphify-out/wiki/index.md` exists, use it for broad navigation. Read `graphify-out/GRAPH_REPORT.md`
only for broad architecture review or when query/path/explain do not surface enough context. Only read
source files when (a) modifying/debugging specific code, (b) the graph lacks the needed detail, or
(c) the graph is missing or stale.

Type `/graphify` in Copilot Chat to build or update the graph.
