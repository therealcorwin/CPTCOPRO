# CPTCOPRO - Suivi des Copropriétaires

Application de suivi des charges et des lots des copropriétaires, avec récupération depuis un extranet de syndic, parsing HTML, persistance SQLite et visualisation Streamlit.

## Fonctionnalités

- 🔄 **Extraction automatique** : Récupération parallèle des données depuis l'extranet (Playwright)
- 📊 **Interface web** : Visualisation des données via Streamlit
- 💾 **Base SQLite** : Stockage local, sauvegarde et historique des alertes
- ☁️ **Sauvegarde pCloud** : Backup distant après écriture, avec restauration automatique si la base locale manque
- 🚨 **Alertes** : Détection automatique des débits élevés
- 📦 **Exécutable** : Packaging PyInstaller pour distribution

## Installation

### Avec Poetry (recommandé)

```powershell
poetry install
poetry run playwright install
```

### Avec pip

```powershell
pip install -r requirements.txt
playwright install
```

## Configuration

Créez un fichier `.env` à la racine du projet :

```env
login_site_copro=votre_identifiant
password_site_copro=votre_mot_de_passe
url_site_copro=https://url-du-syndic.com
```

En mode PyInstaller, le `.env` doit être placé à côté de l'exécutable.

Si la configuration pCloud est activée, le programme utilise un token local `.pcloud_credentials` à la racine du projet pour l'authentification et sauvegarde les archives dans le dossier distant configuré.

## Utilisation

```powershell
# Lancer l'application complète (extraction + interface Streamlit)
poetry run python -m cptcopro.main

# Options disponibles
poetry run python -m cptcopro.main --no-headless    # Mode visible (debug)
poetry run python -m cptcopro.main --no-serve       # Sans interface Streamlit
poetry run python -m cptcopro.main --no-backup       # Pas de backup pCloud après écriture
poetry run python -m cptcopro.main --deco-pcloud     # Déconnexion pCloud + suppression du token
poetry run python -m cptcopro.main --show-console   # Affichage console
poetry run python -m cptcopro.main --serve-port 8502
poetry run python -m cptcopro.main --streamlit-no-browser
```

Comportement de sauvegarde:

- Une sauvegarde locale est créée avant les écritures en base.
- Une sauvegarde pCloud est effectuée après l'écriture et la mise à jour des alertes, sauf avec `--no-backup`.
- Si la base locale est absente au démarrage, le programme tente d'abord de restaurer le dernier backup pCloud.
- L'option `--deco-pcloud` déconnecte la session pCloud et supprime le token local en fin d'exécution.

## Tests

```powershell
poetry run pytest -v
```

## Variables d'environnement

| Variable | Description | Défaut |
| ---------- | ----------- | -------- |
| `CPTCOPRO_DB_NAME` | Nom du fichier SQLite si `CPTCOPRO_DB_PATH` n'est pas défini | `coproprietaires.sqlite` |
| `CPTCOPRO_DB_PATH` | Chemin de la base de données | `src/cptcopro/BDD/coproprietaires.sqlite` |
| `CPTCOPRO_LOG_FILE` | Fichier de log | `logs/app.log` |

`CPTCOPRO_LOG_LEVEL` n'est pas utilisé par le code actuel.

## Architecture

```text
src/cptcopro/
├── main.py                    # Point d'entrée, orchestration
├── Affichage_Stream.py        # Navigation Streamlit multi-pages
├── Parsing/                   # Playwright: login + récupération HTML
├── Traitement/                # Selectolax: extraction et consolidation
├── Database/                  # Persistance SQLite et alertes
├── Pages/                     # Pages Streamlit
└── utils/                     # Chemins, .env, navigateur, Streamlit
```

Voir [`reports/call_graph.md`](reports/call_graph.md) pour le graphe complet des appels.

## Notes utiles

- Le dédoublonnage existe encore dans `Database/Dedoublonnage.py`, mais n'est plus appelé par `main.py`.
- Les erreurs de parsing remontent via des codes `KO_*` définis dans `src/cptcopro/Parsing/constants.py`.
- Les données persistantes vivent sous `src/cptcopro/BDD`, `src/cptcopro/logs` et `src/cptcopro/Backup` en développement.
- En cas d'absence de base locale, `main.py` tente une restauration depuis pCloud avant d'écrire de nouvelles données.
- Consulter `reports/call_graph.md` pour la vue détaillée des flux applicatifs.
- Consulter `.github/copilot-instructions.md` pour le guide agent condensé et les conventions utiles au dépôt.
