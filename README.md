# CPTCOPRO - Suivi des Copropriétaires

Application de suivi des charges et lots des copropriétaires, avec extraction automatique depuis un extranet de syndic.

## Fonctionnalités

- 🔄 **Extraction automatique** : Récupération parallèle des données depuis l'extranet (Playwright)
- 📊 **Interface web** : Visualisation des données via Streamlit
- 💾 **Base SQLite** : Stockage local avec gestion des doublons et historique
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

## Utilisation

```powershell
# Lancer l'application complète (extraction + interface Streamlit)
poetry run python -m cptcopro.main

# Options disponibles
poetry run python -m cptcopro.main --no-headless    # Mode visible (debug)
poetry run python -m cptcopro.main --no-serve       # Sans interface Streamlit
poetry run python -m cptcopro.main --show-console   # Affichage console
```

## Tests

```powershell
poetry run pytest -v
```

## Variables d'environnement

| Variable | Description | Défaut |
|----------|-------------|--------|
| `CPTCOPRO_DB_PATH` | Chemin de la base de données | `src/cptcopro/coproprietaires.sqlite` |
| `CPTCOPRO_LOG_LEVEL` | Niveau de log (`DEBUG`, `INFO`, `WARNING`) | `INFO` |
| `CPTCOPRO_LOG_FILE` | Fichier de log | `logs/app.log` |

## Architecture

```
src/cptcopro/
├── main.py                    # Point d'entrée, orchestration
├── Parsing_Commun.py          # Authentification, parsing parallèle
├── Parsing_Charge_Copro.py    # Navigation pour les charges
├── Parsing_Lots_Copro.py      # Navigation pour les lots
├── Traitement_Charge_Copro.py # Parsing HTML des charges
├── Traitement_Lots_Copro.py   # Parsing HTML des lots
├── Data_To_BDD.py             # Opérations SQLite
├── Dedoublonnage.py           # Nettoyage des doublons
├── Backup_DB.py               # Sauvegarde de la base
├── Affichage_Stream.py        # Interface Streamlit
└── utils/                     # Utilitaires (paths, env, browser)
```

Voir [`reports/call_graph.md`](reports/call_graph.md) pour le graphe complet des appels.

## Migration (v2.0+)

Les variables d'environnement ont été renommées pour corriger les fautes de frappe :
- `CTPCOPRO_DB_PATH` → `CPTCOPRO_DB_PATH`

Les anciennes variables restent supportées pour compatibilité.

