## But rapide

Ce dépôt extrait et stocke le "solde des copropriétaires" depuis un extranet (Playwright), parse le HTML (selectolax) et écrit dans une base SQLite locale. Ce fichier donne aux agents IA l'essentiel pour être productifs rapidement.

## Points d'entrée et architecture

- Point d'entrée principal : `src/cptcopro/main.py` — orchestre la récupération HTML, le parsing, l'affichage et la sauvegarde en base.
- Récupération HTML : `src/cptcopro/Parsing_Site_Syndic.py` (asynchrone, Playwright). Retourne une chaîne HTML ou des codes d'erreur texte (p.ex. `KO_OPEN_BROWSER`).
- Parsing et affichage : `src/cptcopro/Traitement_Parsing.py` (selectolax + rich). Cherche spécifiquement `td#lzA1` pour la date et `table#ctzA1` pour le tableau.
- Persistance : `src/cptcopro/Data_To_BDD.py` (création/insertion SQLite). Le fichier DB s'appelle `coproprietaires.sqlite` à côté du module (voir `DB_PATH` dans `main.py`).
- Variable d'environnement `CPTCOPRO_DB_PATH` : peut être utilisée pour forcer un chemin de base de données différent (ex : une machine CI). L'ancienne variable `CTPCOPRO_DB_PATH` reste supportée pour compatibilité. Si non définie, le chemin par défaut est `src/cptcopro/coproprietaires.sqlite`.
- Sauvegarde : `src/cptcopro/Backup_DB.py` crée un dossier `Backup` dans le répertoire courant (os.getcwd()) et y copie la DB.
- Logging : `src/cptcopro/logger_config.py` configure `loguru` et contient un shim vers `logging` si `loguru` absent. Les modules utilisent `logger.bind(type_log=...)` pour classifier les logs.

## Dépendances et environnement

- Python requis : `>=3.14` (défini dans `pyproject.toml`).
- Dépendances listées dans `pyproject.toml` : `loguru`, `selectolax`, `pandas`, `plotly`, `rich`, `dotenv`, `playwright`.
- Variables d'environnement (ou `.env`) nécessaires pour Playwright :
  - `login_site_copro`
  - `password_site_copro`
  - `url_site_copro`

Conseil d'exécution local rapide : ajouter `src` au PYTHONPATH puis exécuter le module :

  - Avec PowerShell (session seulement) :
    $env:PYTHONPATH = 'src'
    python -m cptcopro.main

  - Ou, si vous utilisez Poetry :
    poetry install
    poetry run python -m cptcopro.main

Important : après l'installation de `playwright`, exécuter `playwright install` pour installer les navigateurs.

## Patterns et conventions à connaître

- Sélecteurs CSS attendus : date -> `td#lzA1`; tableau -> `table#ctzA1`; colonnes classes : `td.ttA3/ttA4/ttA5/ttA6`.
- Les fonctions de parsing renvoient une liste de tuples de la forme `(code, coproprietaire, debit, credit, date, last_check)`.
- Beaucoup de fonctions utilisent `data[3:]` avant insertion/affichage — attention aux lignes d'en-tête du tableau HTML : un agent doit vérifier la structure du HTML avant de modifier le slicing.
- Le module `logger_config.py` expose les variables d'environnement `CPTCOPRO_LOG_LEVEL` et `CPTCOPRO_LOG_FILE` pour contrôler le logging côté production/debug.

## Opérations risquées / effets de bord connus

- `Backup_DB.backup_db()` utilise `os.getcwd()` pour créer `Backup/` — la sauvegarde est relative au répertoire courant d'exécution.
- `Data_To_BDD.enregistrer_donnees_sqlite()` fait `executemany(..., data[3:])` : vérifier la longueur et le contenu de `data` avant de l'appeler.
- Playwright est exécuté en `headless=True` dans `Parsing_Site_Syndic.py`. Pour déboguer des problèmes d'interaction, exécuter avec `headless=False` et/ou ajouter des `await page.screenshot()` temporaires.

## CLI & CI

- `main.py` expose désormais deux options CLI utiles : `--no-headless` (lance Playwright en mode visible) et `--db-path <path>` (surcharge le chemin de la DB). Exemple :

  $env:PYTHONPATH = 'src'
  python -m cptcopro.main --no-headless --db-path "C:\tmp\copro.sqlite"

- Un workflow GitHub Actions est ajouté dans `.github/workflows/ci.yml` : il installe les dépendances, installe les navigateurs Playwright et lance `pytest`. Le CI fixe `CPTCOPRO_DB_PATH` vers `src/cptcopro/coproprietaires.sqlite`.

## Migration

### Renommage de variables d'environnement (v2.0+)

Les variables d'environnement ont été renommées pour corriger les fautes de frappe :
- `CTPCOPRO_DB_PATH` → `CPTCOPRO_DB_PATH`
- `CTPCOPRO_LOG_LEVEL` → `CPTCOPRO_LOG_LEVEL`
- `CTPCOPRO_LOG_FILE` → `CPTCOPRO_LOG_FILE`

Les anciennes variables restent supportées pour compatibilité mais sont dépréciées.

## Fichiers à consulter rapidement

- `pyproject.toml` (dépendances / version Python)
- `src/cptcopro/main.py` (flux orchestration)
- `src/cptcopro/Parsing_Site_Syndic.py` (Playwright, env vars, selectors)
- `src/cptcopro/Traitement_Parsing.py` (selectolax parsing, format de sortie)
- `src/cptcopro/Data_To_BDD.py` (création/insertion SQLite)
- `src/cptcopro/Backup_DB.py` (comportement de backup relatif au CWD)
- `src/cptcopro/logger_config.py` (contrôles de log)

Si une section n'est pas claire, indiquez exactement quel scénario vous voulez automatiser (ex : "exécuter avec headless False et sauvegarder les captures d'écran"), je mettrai à jour ce fichier.
