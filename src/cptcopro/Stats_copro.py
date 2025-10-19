import sqlite3


def analyser_evolution_soldes(db_path="ctpcopro/coproprietaires.sqlite"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Récupérer les soldes les plus récents et les dates antérieures pour chaque copropriétaire
    query = """
    WITH recent_soldes AS (
        SELECT 
            code,
            coproprietaire,
            debit,
            credit,
            date,
            MAX(date) OVER (PARTITION BY code) AS date_plus_recente
        FROM coproprietaires
    ),
    comparaison AS (
        SELECT 
            r1.code,
            r1.coproprietaire,
            r1.debit AS debit_recent,
            r1.credit AS credit_recent,
            r2.debit AS debit_precedent,
            r2.credit AS credit_precedent
        FROM recent_soldes r1
        LEFT JOIN coproprietaires r2
        ON r1.code = r2.code AND r2.date < r1.date_plus_recente
        WHERE r1.date = r1.date_plus_recente
    )
    SELECT 
        code,
        coproprietaire,
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
            code,
            coproprietaire,
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
        evolution.append((code, coproprietaire, tag))

    conn.close()

    # Afficher les résultats
    for code, coproprietaire, tag in evolution:
        print(f"Code: {code}, Copropriétaire: {coproprietaire}, Évolution: {tag}")

    return evolution


evolution = analyser_evolution_soldes()
