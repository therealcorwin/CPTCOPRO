import sqlite3
import os
DB_PATH = os.path.join(os.path.dirname(__file__), "BDD", "copropriete.sqlite")

def analyser_evolution_soldes(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Récupérer les soldes les plus récents et les dates antérieures pour chaque copropriétaire
    query = """
    WITH recent_soldes AS (
        SELECT 
            code_proprietaire AS code_proprietaire,
            nom_proprietaire AS nom_proprietaire,
            debit,
            credit,
            date,
            MAX(date) OVER (PARTITION BY code_proprietaire) AS date_plus_recente
        FROM coproprietaires
    ),
    comparaison AS (
        SELECT 
        r1.code_proprietaire,
        r1.nom_proprietaire,
            r1.debit AS debit_recent,
            r1.credit AS credit_recent,
            r2.debit AS debit_precedent,
            r2.credit AS credit_precedent
        FROM recent_soldes r1
        LEFT JOIN coproprietaires r2
        ON r1.code_proprietaire = r2.code_proprietaire AND r2.date < r1.date_plus_recente
        WHERE r1.date = r1.date_plus_recente
    )
    SELECT 
        code_proprietaire,
        nom_proprietaire,
        debit_recent,
        credit_recent,
        debit_precedent,
        credit_precedent
    FROM comparaison
    """
    cur.execute(query)
    result = cur.fetchall()

    # Analyser l'évolution des soldes
    evolution = []
    for row in result:
        (
            code_proprietaire,
            nom_proprietaire,
            debit_recent,
            credit_recent,
            debit_precedent,
            credit_precedent,
        ) = row
        if debit_precedent is None or credit_precedent is None:
            tag = "AUCUNE_COMPARAISON"  # Pas de données antérieures disponibles
        else:
            solde_recent = float(debit_recent) - float(credit_recent)
            solde_precedent = float(debit_precedent) - float(credit_precedent)
            if solde_recent > solde_precedent:
                tag = "SUPERIEUR"
            elif solde_recent < solde_precedent:
                tag = "INFERIEUR"
            else:
                tag = "EGAL"
    evolution.append((code_proprietaire, nom_proprietaire, tag))

    conn.close()

    # Afficher les résultats
    for code_proprietaire, nom_proprietaire, tag in evolution:
        print(f"Code: {code_proprietaire}, Copropriétaire: {nom_proprietaire}, Évolution: {tag}")

    return evolution


evolution = analyser_evolution_soldes()
