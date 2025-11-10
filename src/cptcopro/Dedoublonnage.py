"""
Module pour le nettoyage et la maintenance de la base de données.
"""
import csv
import os
import sqlite3
from loguru import logger
import sys
from datetime import datetime

logger.remove()
logger = logger.bind(type_log="DEDOUBLONNAGE")

# Initialisation des noms de fichiers de rapport avec horodatage et répertoire
now: datetime = datetime.now()
rapport_dir: str = os.path.join(os.path.dirname(__file__), "Rapports")
rapport_resume = f"rapport_resume-{now.strftime('%d-%m-%y-%H-%M-%S')}.csv"
rapport_complet = f"rapport_complet-{now.strftime('%d-%m-%y-%H-%M-%S')}.csv"
rapport_resume_dir = os.path.join(rapport_dir, rapport_resume)
rapport_complet_dir = os.path.join(rapport_dir, rapport_complet)

# Chemin par défaut vers la base de données SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), "BDD", "test.sqlite")


def analyse_doublons(DB_PATH: str) -> list[int]:
    """
    Dédoublonne la table 'coproprietaires' dans la base de données SQLite.

    La règle de dédoublonnage est la suivante : pour un ensemble de lignes
    ayant les mêmes 'code', 'coproprietaire' et 'date', seul l'enregistrement
    avec la date 'last_check' la plus récente est conservé. Les autres sont
    supprimés.

    Args:
        db_path (Union[str, Path]): Le chemin vers le fichier de la base de données SQLite.
    """
    logger.info("Début du processus de dédoublonnage de la base de données.")
    logger.info("Analyse des doublons dans la base de données : {}", DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    liste_ids: list[int] = []
    try:
        cur.execute(
            """
            WITH ranked AS (
              SELECT id,
                     ROW_NUMBER() OVER (
                       PARTITION BY nom_proprietaire, date
                       ORDER BY COALESCE(last_check, '0001-01-01') DESC, id DESC
                     ) AS rn
              FROM charge
            )
            SELECT id FROM ranked WHERE rn > 1;
            """
        )
        ids = cur.fetchall()
        liste_ids = [r[0] for r in ids]
    except sqlite3.OperationalError:
        # Fallback : requête corrélée compatible avec d'anciennes versions SQLite
        logger.warning("ROW_NUMBER() non supporté → utilisation du fallback corrélé")
        try:
            cur.execute(
                """
                SELECT c.id
                FROM charge c
                WHERE EXISTS (
                  SELECT 1 FROM charge c2
                  WHERE c2.nom_proprietaire = c.nom_proprietaire
                    AND c2.date = c.date
                    AND (
                      COALESCE(c2.last_check, '0001-01-01') > COALESCE(c.last_check, '0001-01-01')
                      OR (
                        COALESCE(c2.last_check, '0001-01-01') = COALESCE(c.last_check, '0001-01-01')
                        AND c2.id > c.id
                      )
                    )
                );
                """
            )
            ids = cur.fetchall()
            liste_ids = [r[0] for r in ids]
        except Exception as e:
            logger.error(f"Erreur lors du fallback corrélé pour récupérer les doublons : {e}")
            liste_ids = []
    finally:
        conn.close()

    return liste_ids

def suppression_doublons(DB_PATH: str, liste_ids: list[int]):
    """Supprime les ids et retourne le nombre de lignes supprimées."""
    logger.info("Suppression des doublons...")
    if not liste_ids:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        placeholders = ",".join("?" for _ in liste_ids)
        cur.execute(f"DELETE FROM charge WHERE id IN ({placeholders})", liste_ids)
        nb_doublons_supprimes = cur.rowcount
        conn.commit()
        logger.info("Suppression des doublons terminée. Nombre de lignes supprimées: {}", nb_doublons_supprimes)
    except Exception:
        logger.error("Erreur lors de la suppression des doublons")
        conn.rollback()
        raise
    finally:
        conn.close()
    


def rapport_doublon(DB_PATH: str, liste_ids: list[int] , rapport_resume_dir: str = rapport_resume_dir, rapport_complet_dir: str = rapport_complet_dir) -> None:
    logger.info("Génération des rapports de doublons.")

     # Connexion à la base de données
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"DB file not found: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Nbre enregistrements par propriétaire
    cur.execute("SELECT nom_proprietaire, COUNT(*) FROM charge GROUP BY nom_proprietaire")
    totals = {row[0]: row[1] for row in cur.fetchall()}

    # groupes par propriétaire avec leurs tailles
    cur.execute(
        """
        SELECT nom_proprietaire, date, COUNT(*) as cnt
        FROM charge
        GROUP BY nom_proprietaire, date
        HAVING cnt > 1
        """
    )
    groups = {}
    for proprietaire, date, nbre in cur.fetchall():
        groups.setdefault(proprietaire, []).append((date, nbre))

    # Si aucune id n'est fournie après tentative, éviter d'exécuter une requête invalide
    if liste_ids:
        placeholders = ",".join("?" for _ in liste_ids)
        cur.execute(
            f"SELECT * FROM charge WHERE id IN ({placeholders}) ORDER BY nom_proprietaire, date",
            tuple(liste_ids),
        )
        liste_complete = cur.fetchall()
        logger.info("Exemples de lignes candidates à suppression: {}", min(len(liste_complete), 10))
    else:
        liste_complete = []

    conn.close()

    # Rapport par propriétaire
    enregistrements = []
    for proprietaire, total in totals.items():
        g = groups.get(proprietaire, [])
        groupe_doublons = len(g)
        nombre_doublons = sum(nbre - 1 for (_, nbre) in g)
        enregistrements.append({
            "nom_proprietaire": proprietaire,
            "Nbre enregistrements": total,
            "Nbre groupes doublons": groupe_doublons,
            "Nbre lignes doublons": nombre_doublons,
        })

    # Creation du dossier rapport s'il n'existe pas
    logger.info("Vérification de l'existence du dossier des rapports : {}", rapport_dir)
    os.makedirs(rapport_dir, exist_ok=True)

    # Creation du rapport doublons au format CSV
    with open(rapport_resume_dir, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["nom_proprietaire", "Nbre enregistrements", "Nbre groupes doublons", "Nbre lignes doublons"])
        writer.writeheader()
        for r in enregistrements:
            writer.writerow(r)
    logger.info("Rapport résumé des doublons créé : {}", rapport_resume_dir)

    # Creation du rapport doublons au format CSV
    with open(rapport_complet_dir, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "nom_proprietaire", "code_proprietaire", "debit", "credit", "date", "last_check"])
        writer.writeheader()
        fieldnames = ["id", "nom_proprietaire", "code_proprietaire", "debit", "credit", "date", "last_check"]
        for i in liste_complete:
            writer.writerow({k: v for k, v in zip(fieldnames, i)})
    logger.info("Rapport complet des doublons créé : {}", rapport_complet_dir)

    # Affichage des doublons par propriétaire
    liste_doublons = sorted(enregistrements, key=lambda r: r["Nbre lignes doublons"], reverse=True)
    logger.info("Liste resumée des doublons par propriétaire :")
    for r in liste_doublons:
        toto = f"{r['nom_proprietaire']!r}: Nbre lignes doublons={r['Nbre lignes doublons']}, Nbre groupes doublons={r['Nbre groupes doublons']}, Nbre enregistrements={r['Nbre enregistrements']}"
        logger.info(toto)

if __name__ == "__main__":
    # Exemple d'utilisation
    
    if DB_PATH:
       analyse = analyse_doublons(str(DB_PATH))
    else:
        logger.warning(f"La base de données '{DB_PATH}' n'a pas été trouvée.")
    if not analyse:
        logger.info("Aucun doublon détecté. Rien à faire.")
        exit()
    else:
        logger.info(f"Doublons détectés (ids à supprimer) : {len(analyse)}")
        rapport_doublon(str(DB_PATH), analyse)
        suppression_doublons(str(DB_PATH), analyse)