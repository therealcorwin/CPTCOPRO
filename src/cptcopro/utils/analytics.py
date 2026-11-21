"""Services d'analytique et de cache partagé pour CPTCOPRO.

Ce module centralise :
- Le chargement unique et optimisé des charges (`load_charges_dataset`)
- L'algorithme de calcul de la balance âgée ininterrompue (`compute_aging_balance`)
- La cartographie des statuts de relance par copropriétaire (`load_relance_status_map`)
- La santé du système mise en cache (`load_system_health`)
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from cptcopro.Database.connection import get_db_cursor
from cptcopro.utils.db_helpers import fetch_dataframe, normalize_numeric_columns


@st.cache_data(ttl=300, show_spinner=False)
def load_charges_dataset() -> pd.DataFrame:
    """Charge l'ensemble des charges de la vue `vw_charge_coproprietaires` de manière unifiée."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                "SELECT nom_proprietaire AS proprietaire, nom_proprietaire, "
                "code_proprietaire AS code, code_proprietaire, "
                "num_apt, type_apt, debit, credit, date FROM vw_charge_coproprietaires"
            )
            df = fetch_dataframe(cur)
        if df.empty:
            return df

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = normalize_numeric_columns(df, ["debit", "credit"])
        return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    except Exception as exc:
        st.error(f"Erreur lors du chargement des charges : {exc}")
        return pd.DataFrame()


def _classify_tranche(jours: int) -> tuple[str, int, str]:
    """Détermine la tranche d'ancienneté, son ordre d'affichage et sa couleur standard."""
    if jours <= 30:
        return "< 30 j", 1, "#22c55e"
    if jours <= 60:
        return "30-60 j", 2, "#f59e0b"
    if jours <= 90:
        return "60-90 j", 3, "#f97316"
    return "> 90 j", 4, "#ef4444"


def _normalize_charges_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise tolérante des colonnes courantes (casse, alias)."""
    col_mapping: dict[str, str] = {}
    for c in df.columns:
        clow = str(c).lower()
        if clow == "date" and "date" not in df.columns:
            col_mapping[c] = "date"
        elif clow in ("code", "compte", "code_copro", "code_proprietaire") and "code" not in df.columns:
            col_mapping[c] = "code"
        elif clow in ("debit", "débit") and "debit" not in df.columns:
            col_mapping[c] = "debit"
        elif clow in ("nom", "proprietaire", "nom_proprietaire") and "proprietaire" not in df.columns:
            col_mapping[c] = "proprietaire"
    if col_mapping:
        df = df.rename(columns=col_mapping)
    return df


def _find_debt_start_date(copro_hist: pd.DataFrame, default_date: object) -> object:
    """Trouve la date de début de l'impayé ininterrompu."""
    date_debut = default_date
    for _, h in copro_hist.iloc[::-1].iterrows():
        if float(h["debit"]) > 0:
            date_debut = h["date"]
        else:
            break
    return date_debut


def compute_aging_balance(
    charges_df: pd.DataFrame,
    target_date: object | None = None,
) -> pd.DataFrame:
    """Calcule la balance âgée (ancienneté ininterrompue de la dette) à une date de référence.

    Tranches standards :
    - '< 30 j'  : order 1, color '#22c55e'
    - '30-60 j' : order 2, color '#f59e0b'
    - '60-90 j' : order 3, color '#f97316'
    - '> 90 j'  : order 4, color '#ef4444'

    Returns:
        DataFrame trié par montant de débit décroissant.
    """
    if charges_df.empty:
        return pd.DataFrame()

    df = _normalize_charges_columns(charges_df.copy())
    if "date" not in df.columns or "code" not in df.columns or "debit" not in df.columns:
        return pd.DataFrame()

    if not pd.api.types.is_datetime64_any_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if target_date is not None:
        ref_dt = pd.to_datetime(target_date)
        df = df[df["date"] <= ref_dt]
        if df.empty:
            return pd.DataFrame()
        derniere_date = ref_dt
    else:
        derniere_date = df["date"].max()

    snap = df[df["date"] == derniere_date]
    debiteurs = snap[snap["debit"] > 0].copy()
    if debiteurs.empty:
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for _, row in debiteurs.iterrows():
        code = str(row["code"])
        copro_hist = df[df["code"] == code].sort_values("date")
        if copro_hist.empty:
            continue

        date_debut = _find_debt_start_date(copro_hist, derniere_date)
        jours = max(0, (derniere_date - date_debut).days) if pd.notna(derniere_date) and pd.notna(date_debut) else 0
        tranche, order, color = _classify_tranche(jours)

        nom_prop = str(row.get("proprietaire") or row.get("nom_proprietaire") or row.get("nom") or "")
        records.append({
            "code": code,
            "nom": nom_prop,
            "proprietaire": nom_prop,
            "num_apt": row.get("num_apt", "—"),
            "type_apt": row.get("type_apt", "—"),
            "debit": float(row["debit"]),
            "jours": jours,
            "jours_anciennete": jours,
            "tranche": tranche,
            "order": order,
            "tranche_order": order,
            "color": color,
            "date_debut": date_debut,
            "date_debut_dette": date_debut,
        })

    return pd.DataFrame(records).sort_values("debit", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=120, show_spinner=False)
def load_relance_status_map() -> dict[str, dict[str, Any]]:
    """Retourne la synthèse des dernières relances par copropriétaire {code: metadata}."""
    try:
        with get_db_cursor() as cur:
            cur.execute(
                """
                SELECT
                    code_proprietaire,
                    MAX(created_at) AS derniere_relance,
                    COUNT(*) AS nb_relances,
                    MAX(status) AS dernier_statut
                FROM relance_draft
                WHERE status NOT IN ('deleted')
                GROUP BY code_proprietaire
                """
            )
            rows = cur.fetchall()

        result: dict[str, dict[str, Any]] = {}
        for r in rows:
            if not r or not r.get("code_proprietaire"):
                continue
            code = str(r["code_proprietaire"])
            nb = int(r.get("nb_relances") or 0)
            date_raw = r.get("derniere_relance")
            date_str = str(date_raw)[:10] if date_raw else "—"
            statut = str(r.get("dernier_statut") or "").lower()

            if statut == "sent":
                label = f"✅ Envoyé {date_str if date_str != '—' else ''}".strip()
            elif statut in ("draft_imap", "draft_local"):
                label = f"📝 Brouillon ({date_str})"
            elif statut == "error":
                label = "❌ Erreur relance"
            else:
                label = f"📬 {nb} relance(s)"

            result[code] = {
                "dernier_statut": statut,
                "derniere_date": date_str,
                "nb_relances": nb,
                "label": label,
            }
        return result
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def load_system_health() -> dict[str, Any]:
    """Contrôle la santé globale (MariaDB + Hotmail OAuth2) avec mise en cache 5 minutes."""
    health: dict[str, Any] = {
        "db_ok": False,
        "db_msg": "Déconnecté",
        "max_date_str": "N/A",
        "hotmail_ok": False,
        "hotmail_msg": "Non vérifié",
    }
    try:
        with get_db_cursor() as cur:
            cur.execute("SELECT MAX(date) AS max_date FROM charge")
            row = cur.fetchone()
            max_d = row["max_date"] if row else None
            max_d_str = (
                max_d.strftime("%d/%m/%Y")
                if max_d and hasattr(max_d, "strftime")
                else (str(max_d) if max_d else "N/A")
            )
        health["db_ok"] = True
        health["db_msg"] = "Connecté"
        health["max_date_str"] = max_d_str
    except Exception as err:
        health["db_msg"] = f"Déconnecté ({err})"

    try:
        from cptcopro.utils.hotmail_oauth import verifier_statut_token_hotmail

        token_ok, msg_token = verifier_statut_token_hotmail()
        health["hotmail_ok"] = token_ok
        health["hotmail_msg"] = msg_token
    except Exception as exc:
        health["hotmail_msg"] = f"Non vérifié ({exc})"

    return health
