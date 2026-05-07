# CPTCOPRO - Suivi des Copropriétaires

Application de suivi des charges et des lots des copropriétaires, avec récupération depuis un extranet de syndic, parsing HTML, persistance SQLite et visualisation Streamlit.

## Fonctionnalités

- 🔄 **Extraction automatique** : Récupération parallèle des données depuis l'extranet (Playwright)
- 📊 **Interface web** : Visualisation des données via Streamlit
- 💾 **Base SQLite** : Stockage local, sauvegarde et historique des alertes
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

## Utilisation

```powershell
# Lancer l'application complète (extraction + interface Streamlit)
poetry run python -m cptcopro.main

# Options disponibles
poetry run python -m cptcopro.main --no-headless    # Mode visible (debug)
poetry run python -m cptcopro.main --no-serve       # Sans interface Streamlit
poetry run python -m cptcopro.main --show-console   # Affichage console
poetry run python -m cptcopro.main --serve-port 8502
poetry run python -m cptcopro.main --streamlit-no-browser
```

## Tests

```powershell
poetry run pytest -v
```

## Variables d'environnement

| Variable | Description | Défaut |
| ---------- | ----------- | -------- |
| `CPTCOPRO_DB_NAME` | Nom du fichier SQLite si `CPTCOPRO_DB_PATH` n'est pas défini | `coproprietaires.sqlite` |
| `CPTCOPRO_DB_PATH` | Chemin de la base de données | `src/cptcopro/coproprietaires.sqlite` |
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
- Consulter `reports/call_graph.md` pour la vue détaillée des flux applicatifs.
- Consulter `.github/copilot-instructions.md` pour le guide agent condensé et les conventions utiles au dépôt.

