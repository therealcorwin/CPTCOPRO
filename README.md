## Run & Test

Instructions rapides pour lancer le projet et exécuter les tests.

- Utiliser le venv du dépôt (si présent) :

	PowerShell:

		$env:PYTHONPATH = 'src'
		d:/Dev/Projet/Python/CPTCOPRO/.venv/Scripts/python.exe -m pip install -r requirements.txt
		d:/Dev/Projet/Python/CPTCOPRO/.venv/Scripts/python.exe -m playwright install
		d:/Dev/Projet/Python/CPTCOPRO/.venv/Scripts/python.exe -m pytest -q

- Avec Poetry :

		poetry install
		poetry run playwright install
		poetry run pytest -q

Notes :
- Les variables d'environnement nécessaires pour l'accès Playwright sont : `login_site_copro`, `password_site_copro`, `url_site_copro`.
- Vous pouvez surcharger la base de données avec la variable d'environnement `CPTCOPRO_DB_PATH` (ou l'ancienne `CTPCOPRO_DB_PATH` pour compatibilité) ou le flag `--db-path`.

## Migration

### Renommage de variable d'environnement (v2.0+)

La variable d'environnement `CTPCOPRO_DB_PATH` a été renommée en `CPTCOPRO_DB_PATH` pour corriger la faute de frappe.
L'ancienne variable reste supportée pour compatibilité mais est dépréciée. Mettez à jour vos scripts CI/CD et configurations.

