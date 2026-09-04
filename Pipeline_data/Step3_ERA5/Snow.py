#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
Snow.py — Step3_ERA5 neige quotidien sur les BV
═══════════════════════════════════════════════════════════════════════════

Extrait snow_depth et snowmelt depuis Step3_ERA5-Land (dossier Snow) et
complète les colonnes snow_depth_bv et snowmelt_bv dans era5_bv_jour.

Structure attendue :
    {ERA5_BASE}/Snow/{annee}/{mois}/data_0.nc
    Variables : sde/sd (snow depth m), smlt (snowmelt m)

Prérequis : pip install xarray netCDF4 numpy

⚠️ OPTIMISATION (déjà en place) :
    Les UPDATE sont accumulés dans un batch par mois puis exécutés en un
    seul executemany(), au lieu d'un execute() individuel par ligne.

⚠️ CHANGEMENT (config centrale) :
    DEFAULT_ERA5_BASE et la période (YEARS/MONTHS) viennent maintenant
    de config_step3.py — même source que Meteo_Temp_Precip_ETP.py,
    évite toute divergence entre les deux (le bug de chemin corrigé
    côté météo ne peut plus se reproduire ici).
═══════════════════════════════════════════════════════════════════════════
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step3_ERA5.config_step3 import (
    USABLE_DATA_DIR as DEFAULT_ERA5_BASE,
    year_months,
)

log = logging.getLogger("step3c")


def load_snow_month(era5_base: str, year: int, month: str) -> dict | None:
    """
    Charge le fichier snow Step3_ERA5-Land mensuel.
    - sde/sd : snow_depth en m (instantané à 23h) → mm
    - smlt   : snowmelt en m eq. eau (cumul à 23h) → mm
    """
    path = f"{era5_base}/Snow/{year}/{month}/data_0.nc"
    if not os.path.exists(path):
        return None

    ds = xr.open_dataset(path)

    var_sd = next((v for v in ds.data_vars if v in ("sde", "sd", "snow_depth")), None)
    var_smlt = next((v for v in ds.data_vars if v in ("smlt", "snowmelt")), None)

    if var_sd is None or var_smlt is None:
        log.warning(f"Variables snow manquantes dans {path}: {list(ds.data_vars)}")
        ds.close()
        return None

    data = {
        "sd": ds[var_sd] * 1000,    # m → mm
        "smlt": ds[var_smlt] * 1000,  # m → mm
    }
    ds.close()
    return data


def extract_snow_bv_means(data_month: dict, pixels: list[tuple]) -> dict:
    """
    Extrait les moyennes spatiales snow sur les pixels du BV.

    Returns:
        {date_str: (snow_depth_mm, snowmelt_mm)}
    """
    lons = xr.DataArray([p[0] for p in pixels], dims="pixel")
    lats = xr.DataArray([p[1] for p in pixels], dims="pixel")

    sd_bv = data_month["sd"].sel(longitude=lons, latitude=lats, method="nearest").values
    smlt_bv = data_month["smlt"].sel(longitude=lons, latitude=lats, method="nearest").values
    dates = data_month["sd"].valid_time.values

    results = {}
    for i, t in enumerate(dates):
        date_str = str(t)[:10]
        results[date_str] = (
            round(float(np.nanmean(sd_bv[i])), 4),
            round(float(np.nanmean(smlt_bv[i])), 4),
        )
    return results


def update_era5_snow_batch(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """
    Met à jour snow_depth_bv / snowmelt_bv pour plusieurs lignes d'un coup.

    Args:
        rows: liste de tuples (snow_depth_mm, snowmelt_mm, station_code, date_str)

    Returns:
        Nombre de lignes mises à jour (nombre de tuples envoyés — SQLite
        n'expose pas facilement le rowcount cumulé d'un executemany).
    """
    if not rows:
        return 0
    conn.executemany("""
        UPDATE era5_bv_jour
        SET snow_depth_bv = ?, snowmelt_bv = ?
        WHERE station_code = ? AND date = ?
    """, rows)
    return len(rows)


def run_step3c(conn: sqlite3.Connection,
               era5_base: str = DEFAULT_ERA5_BASE) -> dict:
    """
    Étape 3c optimisée : boucle mois → stations, écriture en BATCH.
    Chaque .nc snow est chargé UNE SEULE FOIS pour toutes les stations,
    et chaque mois ne fait qu'UN SEUL executemany() (au lieu d'un UPDATE
    par station × par date).
    """
    from Pipeline_data.Database.db_operations import get_era5_pixels

    # Stations avec pixels Step3_ERA5
    stations = conn.execute("""
        SELECT station_code, COUNT(*) as nb_pixels
        FROM era5_transfert
        GROUP BY station_code
    """).fetchall()

    log.info(f"{len(stations)} stations à traiter pour la neige")

    # Pré-charger tous les pixels
    all_pixels = {}
    for station_code, nb_pixels in stations:
        all_pixels[station_code] = get_era5_pixels(conn, station_code)

    # Dates manquantes par station (set pour lookup rapide)
    missing_dates = {}
    for station_code, _ in stations:
        rows = conn.execute("""
            SELECT date FROM era5_bv_jour
            WHERE station_code = ? AND snow_depth_bv IS NULL
        """, (station_code,)).fetchall()
        missing_dates[station_code] = {r[0] for r in rows}

    total_updated = 0
    errors = 0

    # Boucle MOIS → stations
    for year, month in year_months():
        data = load_snow_month(era5_base, year, month)
        if data is None:
            continue

        # Accumulateur du mois : un seul executemany() à la fin
        batch: list[tuple] = []

        for station_code, nb_pixels in stations:
            dates_set = missing_dates[station_code]
            if not dates_set:
                continue

            pixels = all_pixels[station_code]

            try:
                results = extract_snow_bv_means(data, pixels)
            except Exception as e:
                errors += 1
                continue

            for date_str, (sd, smlt) in results.items():
                if date_str in dates_set:
                    batch.append((sd, smlt, station_code, date_str))

        n = update_era5_snow_batch(conn, batch)
        if n:
            conn.commit()

        total_updated += n
        log.info(f"  {year}/{month} — {n} jours mis à jour (total: {total_updated})")

    log.info(f"Étape 3c terminée : {total_updated} jours avec neige, {errors} erreurs")
    return {"stations": len(stations), "days_updated": total_updated, "errors": errors}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="Étape 3c — Step3_ERA5 neige")
    parser.add_argument("--db", type=str, default="./data/test.db")
    parser.add_argument("--era5", type=str, default=DEFAULT_ERA5_BASE)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    run_step3c(conn, args.era5)
    conn.close()