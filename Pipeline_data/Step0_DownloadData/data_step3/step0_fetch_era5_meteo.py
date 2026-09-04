#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_era5_meteo.py — Téléchargement ERA5-Land (precip + PET + temp)
═══════════════════════════════════════════════════════════════════════════

Télécharge, mois par mois, les données ERA5-Land précipitation + PET
(cumuls journaliers via décalage 00:00) et température (moyenne
journalière via daily-statistics), fusionnées dans un seul fichier
{ERA5_BASE}/{annee}/{mois}/data_0.nc — lu ensuite par step3b_era5_meteo.py.

Adapté du script original pour :
  - accepter start_date/end_date/bbox/dossiers en paramètres au lieu de
    constantes en dur
  - lire CDSAPI_URL/CDSAPI_KEY depuis config_step3.py (un seul endroit)

Prérequis : pip install cdsapi xarray pandas

⚠️ Dépend de Exploring_data.dezip.unzip (module du projet, pas modifié
ici) pour gérer le cas où CDS renvoie un zip au lieu d'un netcdf direct.

Usage :
    python step0_fetch_era5_meteo.py --db ./ta_bdd.db
    python step0_fetch_era5_meteo.py --bbox 52 -6 40 10
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import calendar
import logging
import os
import sys
import zipfile
import glob
from pathlib import Path

import cdsapi
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step3_ERA5.config_step3 import (
    CDSAPI_URL, CDSAPI_KEY,
    START_DATE as DEFAULT_START_DATE,
    END_DATE as DEFAULT_END_DATE,
    BBOX_FRANCE as DEFAULT_BBOX,
    RAW_DATA_DIR as DEFAULT_RAW_DATA_DIR,
    USABLE_DATA_DIR as DEFAULT_USABLE_DATA_DIR,
    KEEP_RAW_PIECES as DEFAULT_KEEP_RAW_PIECES,
    get_bbox_from_bv,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_era5_meteo")


def unzip(zip_path: str, mois: str, year: str, extract_dir: str) -> None:
    """
    Extrait un zip téléchargé (repris de Exploring_data.dezip.unzip,
    intégré ici pour ne plus dépendre d'un autre projet — l'original
    vivait dans PythonProject, pas dans ce repo).
    """
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)


def _year_months(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """Liste des (année, mois) couvrant [start_date, end_date] (granularité mensuelle)."""
    months = pd.period_range(start=start_date, end=end_date, freq="M")
    return [(str(p.year), f"{p.month:02d}") for p in months]


def resolve_netcdf(path: str, extract_dir: str) -> str:
    """
    CDS renvoie parfois un vrai .nc, parfois un zip contenant un .nc,
    même quand on demande format='netcdf'. Retourne toujours le vrai
    chemin NetCDF à ouvrir avec xarray.
    """
    if zipfile.is_zipfile(path):
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(path, 'r') as zf:
            zf.extractall(extract_dir)
        nc_candidates = sorted(glob.glob(os.path.join(extract_dir, "*.nc")))
        if not nc_candidates:
            raise FileNotFoundError(f"Aucun .nc trouvé dans le zip extrait : {extract_dir}")
        return nc_candidates[0]
    return path


def normalize_time_dim(ds: xr.Dataset) -> xr.Dataset:
    """CDS nomme parfois la dimension temporelle 'valid_time' au lieu de 'time'."""
    if "valid_time" in ds.dims and "time" not in ds.dims:
        ds = ds.rename({"valid_time": "time"})
    return ds


def _next_month(year: str, m: str) -> tuple[str, str]:
    y, mo = int(year), int(m)
    if mo == 12:
        return str(y + 1), "01"
    return str(y), f"{mo + 1:02d}"


def fetch_era5_meteo(
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    bbox: list[float] = None,
    raw_dir: str = DEFAULT_RAW_DATA_DIR,
    usable_dir: str = DEFAULT_USABLE_DATA_DIR,
    keep_raw_pieces: bool = DEFAULT_KEEP_RAW_PIECES,
) -> dict:
    """
    Télécharge precip + PET + température pour la période et le bbox
    donnés, mois par mois, avec cache fichier (skip si déjà téléchargé).

    Args:
        start_date, end_date: bornes (granularité mensuelle — un mois
                               partiellement inclus est téléchargé en entier)
        bbox: [Nord, Ouest, Sud, Est] (format CDS). Si None, utilise
              DEFAULT_BBOX (France).
        raw_dir: dossier des fichiers intermédiaires (fusionnés ensuite)
        usable_dir: dossier final lu par step3b_era5_meteo.py
        keep_raw_pieces: si True, conserve les fichiers intermédiaires

    Returns:
        {"downloaded": n, "skipped": n, "errors": n}
    """
    bbox = bbox or DEFAULT_BBOX

    os.environ["CDSAPI_URL"] = CDSAPI_URL
    os.environ["CDSAPI_KEY"] = CDSAPI_KEY
    client = cdsapi.Client()

    Path(raw_dir).mkdir(parents=True, exist_ok=True)

    downloaded = skipped = errors = 0

    def fetch_hourly_00(year: str, m: str, days: list[str], out_path: str) -> str:
        client.retrieve(
            'reanalysis-era5-land',
            {
                'product_type': 'reanalysis',
                'variable': ['total_precipitation', 'potential_evaporation'],
                'year': year, 'month': m, 'day': days,
                'time': ['00:00'], 'area': bbox, 'format': 'netcdf',
            },
            out_path
        )
        extract_dir = os.path.join(usable_dir, year, m)
        unzip(out_path, mois=m, year=year, extract_dir=extract_dir)
        return resolve_netcdf(out_path, extract_dir)

    def download_precip_pet(year: str, m: str) -> str | None:
        daily_path = os.path.join(raw_dir, f'precip_pet_{year}_{m}.nc')
        if os.path.exists(daily_path):
            log.info(f"  Déjà téléchargé : precip_pet {year}-{m}")
            return daily_path

        n_days = calendar.monthrange(int(year), int(m))[1]
        ny, nm = _next_month(year, m)
        log.info(f"Téléchargement precip_pet {year}-{m}...")
        try:
            main_days = [f"{d:02d}" for d in range(2, n_days + 1)]
            main_zip_path = os.path.join(raw_dir, f'_tmp_main_{year}_{m}.nc')
            main_nc_path = fetch_hourly_00(year, m, main_days, main_zip_path)

            tail_zip_path = os.path.join(raw_dir, f'_tmp_tail_{year}_{m}.nc')
            tail_nc_path = fetch_hourly_00(ny, nm, ['01'], tail_zip_path)

            ds_main = normalize_time_dim(xr.open_dataset(main_nc_path))
            ds_tail = normalize_time_dim(xr.open_dataset(tail_nc_path))
            ds = xr.concat([ds_main, ds_tail], dim="time").sortby("time")
            ds["time"] = ds["time"] - pd.Timedelta(days=1)
            ds.to_netcdf(daily_path)
            ds_main.close(); ds_tail.close(); ds.close()

            if not keep_raw_pieces:
                for p in [main_zip_path, tail_zip_path, main_nc_path, tail_nc_path]:
                    if p and os.path.exists(p):
                        os.remove(p)

            log.info(f"  ✅ Sauvegardé : {daily_path}")
            return daily_path
        except Exception as e:
            log.error(f"  ❌ Erreur precip_pet {year}-{m} : {e}")
            return None

    def download_temperature(year: str, m: str) -> str | None:
        file_path = os.path.join(raw_dir, f'temperature_{year}_{m}.nc')
        if os.path.exists(file_path):
            log.info(f"  Déjà téléchargé : temperature {year}-{m}")
            return file_path

        jours = [f"{i:02d}" for i in range(1, 32)]
        log.info(f"Téléchargement temperature {year}-{m}...")
        try:
            client.retrieve(
                'derived-era5-land-daily-statistics',
                {
                    'variable': ['2m_temperature'],
                    'year': year, 'month': m, 'day': jours,
                    'daily_statistic': 'daily_mean',
                    'time_zone': 'utc+00:00', 'frequency': '1_hourly',
                    'area': bbox, 'format': 'netcdf',
                },
                file_path
            )
            log.info(f"  ✅ Sauvegardé : {file_path}")
            extract_dir = os.path.join(usable_dir, year, m)
            unzip(file_path, mois=m, year=year, extract_dir=extract_dir)
            return file_path
        except Exception as e:
            log.error(f"  ❌ Erreur temperature {year}-{m} : {e}")
            return None

    for year, m in _year_months(start_date, end_date):
        pp = download_precip_pet(year, m)
        tp = download_temperature(year, m)
        if pp and tp:
            downloaded += 1
        elif pp is None or tp is None:
            errors += 1

    log.info(f"Terminé : {downloaded} mois traités, {errors} erreurs")
    return {"downloaded": downloaded, "errors": errors}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sqlite3

    parser = argparse.ArgumentParser(
        description="Étape 0 (pt3) — Téléchargement ERA5-Land precip/PET/température",
    )
    parser.add_argument("--start", type=str, default=DEFAULT_START_DATE)
    parser.add_argument("--end", type=str, default=DEFAULT_END_DATE)
    parser.add_argument("--bbox", type=float, nargs=4, default=None,
                        metavar=("NORD", "OUEST", "SUD", "EST"),
                        help="Bbox explicite (défaut: BBOX_FRANCE de config_step3.py)")
    parser.add_argument("--db", type=str, default=None,
                        help="Si fourni sans --bbox, auto-détecte le bbox depuis "
                             "bv_data de cette BDD (nécessite l'étape 2a déjà faite)")
    parser.add_argument("--raw-dir", type=str, default=DEFAULT_RAW_DATA_DIR)
    parser.add_argument("--usable-dir", type=str, default=DEFAULT_USABLE_DATA_DIR)
    args = parser.parse_args()

    bbox = args.bbox
    if bbox is None and args.db:
        conn = sqlite3.connect(args.db)
        bbox = get_bbox_from_bv(conn)
        conn.close()
        log.info(f"Bbox auto-détecté depuis bv_data : {bbox}")

    fetch_era5_meteo(
        start_date=args.start, end_date=args.end, bbox=bbox,
        raw_dir=args.raw_dir, usable_dir=args.usable_dir,
    )