## But rapide

Ce dépôt récupère les charges et les lots depuis un extranet via Playwright, parse le HTML, puis persiste les données dans SQLite. Ce fichier doit rester un guide court: utiliser le code source et reports/call_graph.md pour les détails.

## Points d'entrée et architecture

### Orchestration principale
- **Point d'entrée** : `src/cptcopro/main.py` — orchestre la récupération HTML, le parsing, la persistance SQLite et le lancement optionnel de Streamlit.
- **Flux principal** : récupération HTML parallèle, parsing charges/lots, sauvegarde SQLite, mise à jour `suivi_alertes`, puis lancement optionnel de Streamlit.

### Parsing HTML (Playwright) - Architecture à 3 modules
- **`src/cptcopro/Parsing/Commun.py`** : orchestration parallèle, authentification et logique commune de navigation.
- **`src/cptcopro/Parsing/Charge_Copro.py`** : navigation spécifique vers la page des charges.
- **`src/cptcopro/Parsing/Lots_Copro.py`** : navigation spécifique vers la page des lots.

### Traitement et parsing HTML (selectolax)
- **`src/cptcopro/Traitement/Charge_Copro.py`** : extraction de la date et du tableau des charges.
- **`src/cptcopro/Traitement/Lots_Copro.py`** : extraction et consolidation des propriétaires et lots.

### Persistance SQLite
- **Package principal** : `src/cptcopro/Database/`
- Modules à connaître : `Creation_BDD.py`, `Charges_To_BDD.py`, `Coproprietaires_To_BDD.py`, `Alertes_Config.py`, `Backup_DB.py`.
- Tables clés : `charge`, `alertes_debit_eleve`, `coproprietaires`, `suivi_alertes`, `config_alerte`.
- **`src/cptcopro/Database/Dedoublonnage.py`** existe encore, mais n'est plus dans le flux principal de `main.py`.

### Système d'alertes
- **Table `config_alerte`** : seuils configurables par type d'appartement.
- **Triggers dynamiques** : s'appuient sur `config_alerte` et `coproprietaires.type_apt`.
- **UI associée** : `src/cptcopro/Pages/Config_Alertes.py` permet de consulter et modifier les seuils.

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
- **Variables d'environnement** (ou `.env`) nécessaires :
  - `login_site_copro` : Identifiant de connexion
  - `password_site_copro` : Mot de passe
  - `url_site_copro` : URL du site du syndic

### Emplacement du `.env`

- **Exécution normale** : le parsing lit les credentials depuis un `.env` à la racine du projet.
- **PyInstaller** : le `.env` est attendu à côté de l'exécutable.
- **Note pratique** : `utils.paths.init_env()` et `utils.env_loader` coexistent ; pour éviter les ambiguïtés, considérer la racine du projet comme emplacement de référence en développement.

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
| `CPTCOPRO_DB_PATH` | Chemin de la base de données | `src/cptcopro/coproprietaires.sqlite` |
| `CPTCOPRO_LOG_FILE` | Fichier de log | `logs/app.log` |

> Note : `CPTCOPRO_LOG_LEVEL` est documenté historiquement mais n'est pas utilisé par le code actuel.

## CLI

```powershell
python -m cptcopro.main [OPTIONS]

Options:
  --no-headless     Lance Playwright en mode visible (debug)
  --db-path PATH    Surcharge le chemin de la base de données
  --no-serve        Ne pas lancer Streamlit après le traitement
  --serve-port N    Port Streamlit (défaut: 8501)
  --serve-host HOST Host Streamlit (défaut: 127.0.0.1)
  --serve-python P  Interpréteur Python pour lancer Streamlit
  --streamlit-no-browser
  --streamlit-no-console
  --streamlit-use-cmd-start
  --streamlit-log-file FILE
  --show-console    Afficher les données dans la console (rich)
```

## Limitations et comportements utiles

- Le dédoublonnage existe encore dans `Database/Dedoublonnage.py`, mais n'est plus appelé par `main.py`.
- Les erreurs de parsing remontent sous forme de codes `KO_*` centralisés dans `src/cptcopro/Parsing/constants.py`.
- Le détail du flux d'appel et des pages Streamlit est maintenu dans `reports/call_graph.md`.

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
| `src/cptcopro/Parsing/constants.py` | Codes d'erreur et timings Playwright |
| `reports/call_graph.md` | Graphe des appels de fonctions |
