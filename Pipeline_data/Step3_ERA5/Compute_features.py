#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
Compute_features.py — Calcul des features pour measure_attributes
═══════════════════════════════════════════════════════════════════════════

À partir de era5_bv_jour (quotidien), calcule pour chaque date de mesure
les moyennes glissantes et features dérivées, puis remplit measure_attributes.

Features calculées :
    - precipitation_J0, temperature_J0, pet_J0 (valeurs du jour)
    - precip_mean_J3, pet_mean_J3, temp_mean_J3 (moyenne 3 derniers jours)
    - precip_mean_J10, temp_mean_J10 (moyenne 10 derniers jours)
    - precip_mean_J27 (moyenne 27 derniers jours)
    - clim_mean_20j, clim_std_20j (climatologie fenêtrée ±20j, leave-one-year-out)
    - precip_max_J27 (pic journalier max sur 27j)
    - precip_last7 (moyenne des 7 derniers jours)

Fix v2 : gestion des doublons de dates (multi-mission DAHITI) —
  tous les measurement_id d'une même date reçoivent les mêmes attributs.

⚠️ OPTIMISATION (fix v3) — cette étape était très lente sur l'in-situ
(stations avec des milliers de mesures journalières sur 10 ans), pour 2
raisons corrigées ici :

  1. Insertion individuelle (SELECT dedup + INSERT par mesure) remplacée
     par un batch executemany() par station, via insert_measure_attributes_batch
     (même principe que l'optimisation déjà faite sur step3c_era5_snow.py).

  2. La climatologie fenêtrée ±20j était recalculée en boucle Python avec
     df.loc[mask, ...] (pandas) POUR CHAQUE DATE DE MESURE — chaque appel
     .loc a un coût fixe important, répété des milliers de fois par
     station in-situ. Remplacé par un calcul vectorisé en numpy pur
     (tableaux bruts, pas de pandas dans la boucle), fait UNE SEULE FOIS
     par station sur toute sa série, avant la boucle sur les dates de
     mesure — celles-ci ne font plus qu'un lookup, pas un recalcul.
═══════════════════════════════════════════════════════════════════════════
"""

import logging
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("step3d")


# ═══════════════════════════════════════════════════════════════
# CLIMATOLOGIE FENÊTRÉE ±20j — VECTORISÉE (numpy pur, calculée une
# seule fois par station sur toute la série, pas par date de mesure)
# ═══════════════════════════════════════════════════════════════
def compute_precip_clim_vectorized(df: pd.DataFrame, window: int = 20) -> tuple:
    """
    Calcule clim_mean/clim_std (climatologie de precip_sum_bv, ±window
    jours, leave-one-year-out) pour CHAQUE date de df.index, en une seule
    passe vectorisée numpy — au lieu d'un recalcul pandas .loc par date
    de mesure (l'ancien goulot d'étranglement).

    Returns:
        (clim_mean: np.ndarray, clim_std: np.ndarray), alignés sur df.index
    """
    precip = df["precip_sum_bv"].values.astype(float)
    doys = np.clip(df.index.dayofyear.values, 1, 365)
    years = df.index.year.values
    n = len(df)

    clim_mean = np.zeros(n, dtype=np.float64)
    clim_std = np.ones(n, dtype=np.float64)

    valid_mask = ~np.isnan(precip)
    valid_doys = doys[valid_mask]
    valid_years = years[valid_mask]
    valid_vals = precip[valid_mask]

    if len(valid_vals) < 30:
        # Pas assez de données pour une climatologie fiable — comportement
        # identique à l'ancienne fonction (defaults 0.0/1.0 partout)
        return clim_mean, clim_std

    for i in range(n):
        doy_diff = np.abs(valid_doys - doys[i])
        doy_diff = np.minimum(doy_diff, 365 - doy_diff)
        mask = (doy_diff <= window) & (valid_years != years[i])
        vals = valid_vals[mask]
        if len(vals) >= 3:
            clim_mean[i] = vals.mean()
            s = vals.std()
            clim_std[i] = s if s > 0.01 else 1.0
        else:
            clim_mean[i] = 0.0
            clim_std[i] = 1.0

    return clim_mean, clim_std


def compute_rolling_features(era5_df: pd.DataFrame, measure_dates: list[str]) -> list[dict]:
    """
    Calcule toutes les features pour une station à partir de son Step3_ERA5 quotidien.

    Args:
        era5_df: DataFrame avec colonnes [date, temp_moy_bv, precip_sum_bv, pet_sum_bv, ...]
        measure_dates: Liste des dates de mesure uniques (YYYY-MM-DD)

    Returns:
        Liste de dicts, un par date de mesure, avec toutes les features
    """
    if era5_df.empty:
        return []

    df = era5_df.copy()
    df = df.sort_values("date").set_index("date")

    # Pré-calculer les rolling means sur toute la série (déjà vectorisé,
    # inchangé)
    df["precip_J3"]    = df["precip_sum_bv"].rolling(3,  min_periods=1).mean()
    df["pet_J3"]       = df["pet_sum_bv"].rolling(3,     min_periods=1).mean()
    df["temp_J3"]      = df["temp_moy_bv"].rolling(3,    min_periods=1).mean()
    df["precip_J10"]   = df["precip_sum_bv"].rolling(10, min_periods=1).mean()
    df["temp_J10"]     = df["temp_moy_bv"].rolling(10,   min_periods=1).mean()
    df["precip_J27"]   = df["precip_sum_bv"].rolling(27, min_periods=1).mean()
    df["precip_last7"] = df["precip_sum_bv"].rolling(7,  min_periods=1).mean()
    df["precip_max27"] = df["precip_sum_bv"].rolling(27, min_periods=1).max()
    df["doy"]          = df.index.dayofyear

    # Climatologie vectorisée — calculée UNE FOIS pour toute la série,
    # puis simple lookup par date dans la boucle ci-dessous (au lieu
    # d'un recalcul pandas .loc à chaque date de mesure).
    clim_mean_arr, clim_std_arr = compute_precip_clim_vectorized(df)
    clim_series = pd.DataFrame(
        {"clim_mean": clim_mean_arr, "clim_std": clim_std_arr}, index=df.index
    )

    results = []
    for date_str in measure_dates:
        date = pd.Timestamp(date_str)
        if date not in df.index:
            continue

        row = df.loc[date]
        clim_row = clim_series.loc[date]

        features = {
            "precipitation_J0": _round(row.get("precip_sum_bv")),
            "temperature_J0"  : _round(row.get("temp_moy_bv")),
            "pet_J0"          : _round(row.get("pet_sum_bv")),
            "precip_mean_J3"  : _round(row.get("precip_J3")),
            "pet_mean_J3"     : _round(row.get("pet_J3")),
            "temp_mean_J3"    : _round(row.get("temp_J3")),
            "precip_mean_J10" : _round(row.get("precip_J10")),
            "temp_mean_J10"   : _round(row.get("temp_J10")),
            "precip_mean_J27" : _round(row.get("precip_J27")),
            "clim_mean_20j"   : _round(clim_row.get("clim_mean")),
            "clim_std_20j"    : _round(clim_row.get("clim_std")),
            "precip_max_J27"  : _round(row.get("precip_max27")),
            "precip_last7"    : _round(row.get("precip_last7")),
        }

        results.append({"date": date_str, **features})

    return results


def _round(val, decimals=4):
    """Round avec gestion des NaN."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return round(float(val), decimals)


def run_step3d(conn: sqlite3.Connection) -> dict:
    """
    Étape 3d : calcule les features et remplit measure_attributes.

    Fix v2 : gère les doublons de dates (multi-mission) — tous les
    measurement_id d'une même date reçoivent les mêmes attributs Step3_ERA5.

    Fix v3 (optimisation) : insertion en batch par station (executemany)
    au lieu d'un insert individuel par mesure, + climatologie vectorisée.

    Returns:
        {"stations": n, "measures_filled": n, "errors": n}
    """
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from Pipeline_data.Database.db_operations import (
        get_all_station_codes, get_era5_bv_jour,
        get_measurement_dates, insert_measure_attributes_batch,
    )

    station_codes = get_all_station_codes(conn)
    log.info(f"{len(station_codes)} stations à traiter")

    total_filled = 0
    errors       = 0

    for sta_idx, code in enumerate(station_codes):
        try:
            # Step3_ERA5 quotidien
            era5_df = get_era5_bv_jour(conn, code)
            if era5_df.empty:
                continue

            # Dates de mesure uniques (pour le calcul des features)
            measure_dates = get_measurement_dates(conn, code)
            if not measure_dates:
                continue

            # Calculer les features une fois par date unique
            features_list    = compute_rolling_features(era5_df, measure_dates)
            features_by_date = {f["date"]: f for f in features_list}

            # Récupérer TOUS les measurement_id sans attributs
            # (gère les doublons multi-mission : plusieurs IDs par date)
            rows = conn.execute("""
                SELECT m.measurement_id, m.measure_date
                FROM measurements m
                LEFT JOIN measure_attributes a ON m.measurement_id = a.measurement_id
                WHERE m.station_code = ?
                  AND a.measurement_id IS NULL
                ORDER BY m.measure_date
            """, (code,)).fetchall()

            # Accumulation en batch — UN SEUL executemany() pour toute
            # la station, au lieu d'un insert individuel par mesure.
            batch_rows = []
            for measurement_id, date_str in rows:
                feat = features_by_date.get(date_str)
                if feat is None:
                    continue
                f = {k: v for k, v in feat.items() if k != "date"}
                batch_rows.append({
                    "measurement_id": measurement_id,
                    "station_code": code,
                    "measure_date": date_str,
                    **f,
                })

            if batch_rows:
                n = insert_measure_attributes_batch(conn, batch_rows)
                total_filled += n

        except Exception as e:
            log.error(f"  {code} — ERREUR : {e}")
            errors += 1

        if (sta_idx + 1) % 10 == 0:
            log.info(f"  {sta_idx+1}/{len(station_codes)} stations "
                     f"({total_filled} mesures remplies)")

    log.info(f"Étape 3d terminée : {total_filled} mesures remplies, {errors} erreurs")
    return {"stations": len(station_codes), "measures_filled": total_filled, "errors": errors}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Étape 3d — Calcul features")
    parser.add_argument("--db", type=str, default="./data/test.db")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    run_step3d(conn)
    conn.close()