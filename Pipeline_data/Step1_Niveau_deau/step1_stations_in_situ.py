#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step1_import_insitu.py — Étape 1 : Import stations in-situ (CSV) → BDD
═══════════════════════════════════════════════════════════════════════════

Même logique que step1_import_hydroweb_next.py, mais la source des données
n'est plus l'API HydroWeb Next : ce sont des fichiers CSV in-situ locaux
(WSH_<code_station>.csv), avec le nom de rivière récupéré depuis un
GeoPackage (.gpkg).

Pour chaque station :
  - le code station est extrait du nom de fichier CSV
  - le nom de rivière est récupéré dans le GeoPackage
  - une valeur WSH par jour est calculée (médiane des mesures du jour)
  - la station + les mesures sont insérées via les fonctions communes
    du pipeline (insert_station / insert_measurements)

Usage standalone :
    python step1_import_insitu.py
    python step1_import_insitu.py --db ./data/insitu.db --reset
    python step1_import_insitu.py --csv-dir ./data/insitu/data --gpkg ./data/insitu/shp/station.gpkg

Usage depuis la pipeline :
    from step1_import_insitu import run_step1_insitu
    run_step1_insitu(db_path="./data/insitu.db", reset=True)

⚠️ CHANGEMENT (config centrale) :
    DEFAULT_CSV_DIR, DEFAULT_GPKG_PATH, DEFAULT_DB_PATH et
    MIN_MEASUREMENTS viennent maintenant de config_step1.py — même
    dossier que step0_fetch_insitu_raw.py remplit (INSITU_RAW_DIR), même
    seuil qu'avant (5, valeur inchangée, juste centralisée).
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Database.DB_schema import create_database
from Pipeline_data.Database.db_operations import (
    insert_station, insert_measurements, print_report
)
from Pipeline_data.Step1_Niveau_deau.config_step1 import (
    INSITU_CSV_DIR as DEFAULT_CSV_DIR_STR,
    INSITU_GPKG_PATH as DEFAULT_GPKG_PATH_STR,
    INSITU_DB_PATH as DEFAULT_DB_PATH_STR,
    INSITU_MIN_MEASUREMENTS as MIN_MEASUREMENTS,
)
from Pipeline_data.Step2_Bassin_Versant.config_step2 import BBOX_FRANCE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step1_insitu")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
# Valeurs venant de config_step1.py (converties en Path pour compat avec
# le reste du fichier, qui les utilise comme tel).
DEFAULT_GPKG_PATH = Path(DEFAULT_GPKG_PATH_STR)
DEFAULT_CSV_DIR   = Path(DEFAULT_CSV_DIR_STR)
DEFAULT_DB_PATH   = Path(DEFAULT_DB_PATH_STR)

STATION_CODE_RE = re.compile(r"WSH_([A-Z0-9]\d{9})\.csv")


# ═══════════════════════════════════════════════════════════════
# EXTRACTION DU CODE STATION / NOM DE RIVIÈRE
# ═══════════════════════════════════════════════════════════════
def extract_station_code(fichier: Path) -> str | None:
    """Extrait le code station depuis le nom de fichier WSH_<code>.csv"""
    match = STATION_CODE_RE.match(os.path.basename(fichier))
    return match.group(1) if match else None


def get_station_info_from_gpkg(gdf: gpd.GeoDataFrame, station_code: str) -> dict:
    """
    Cherche le nom de rivière ET les coordonnées (lon/lat, WGS84) associés
    au code station dans le GeoPackage.

    Returns:
        {"river_name": str|None, "lon": float|None, "lat": float|None}
    """
    row = gdf[gdf["code_sta"] == station_code]
    if row.empty:
        return {"river_name": None, "lon": None, "lat": None}

    r = row.iloc[0]
    geom = r.geometry
    lon, lat = (geom.x, geom.y) if geom is not None else (None, None)

    return {"river_name": r["river_name"], "lon": lon, "lat": lat}


# ═══════════════════════════════════════════════════════════════
# PARSING D'UN FICHIER CSV IN-SITU
# ═══════════════════════════════════════════════════════════════
def parse_insitu_file(filepath: Path, gdf: gpd.GeoDataFrame):
    """
    Parse un fichier CSV in-situ et retourne (metadata, measurements)
    au même format que parse_hydroweb_file, pour rester compatible
    avec insert_station / insert_measurements.

    measurements : liste de tuples (date_str, valeur_mediane_du_jour)
    """
    station_code = extract_station_code(filepath)
    if station_code is None:
        return None, []

    info = get_station_info_from_gpkg(gdf, station_code)

    metadata = {
        "ID": station_code,
        "RIVER": info["river_name"],
        "REFERENCE LONGITUDE": info["lon"],
        "REFERENCE LATITUDE": info["lat"],
    }

    df = pd.read_csv(filepath)
    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    df["date_only"] = df["Date"].dt.date

    # insert_measurements attend une liste de dicts (format mesures satellite
    # HydroWeb). Pour l'in-situ, on ne remplit que date + height (médiane du
    # jour) ; le reste (champs spécifiques satellite) reste à None.
    measurements = []
    for date, jour in df.groupby("date_only"):
        valeurs = jour["WSH"].dropna().values
        if len(valeurs) == 0:
            continue
        mediane = float(np.median(valeurs))
        measurements.append({
            "date": str(date),
            "time": None,
            "height": mediane,
            "uncertainty": None,
            "longitude": None,
            "latitude": None,
            "ellipsoidal_height": None,
            "geoidal_ondulation": None,
            "distance_to_ref": None,
            "satellite": "in-situ",
            "orbit_mission": None,
            "track_number": None,
            "cycle_number": None,
            "retracking_algo": None,
            "gdr_version": None,
            "is_valid": 1,
        })

    return metadata, measurements


# ═══════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════
def run_step1_insitu(
    csv_dir : Path = DEFAULT_CSV_DIR,
    gpkg_path: Path = DEFAULT_GPKG_PATH,
    db_path : Path = DEFAULT_DB_PATH,
    reset   : bool = False,
) -> dict:
    """
    Étape 1 in-situ : lecture des CSV + parse + insertion BDD.

    Args:
        csv_dir   : dossier contenant les fichiers WSH_<code>.csv
        gpkg_path : chemin vers le GeoPackage des stations
        db_path   : chemin vers la BDD SQLite
        reset     : si True, supprime et recrée la BDD

    Returns:
        Dict {"inserted": n, "skipped": n, "errors": n, "total_measurements": n}
    """
    csv_dir   = Path(csv_dir)
    gpkg_path = Path(gpkg_path)
    db_path   = Path(db_path)

    # 1. Créer / ouvrir la BDD (même schéma que le reste du pipeline)
    conn = create_database(db_path, reset=reset)
    log.info(f"BDD : {db_path}")

    # 2. Charger le GeoPackage une seule fois
    log.info(f"Chargement du GeoPackage : {gpkg_path}")
    gdf = gpd.read_file(gpkg_path)

    # Reprojeter en WGS84 si nécessaire — insert_station attend des
    # coordonnées en degrés (lon/lat), pas dans le CRS d'origine du
    # GeoPackage (souvent une projection métrique type Lambert93 pour
    # des données françaises).
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        log.info(f"  Reprojection {gdf.crs} → EPSG:4326 (WGS84)")
        gdf = gdf.to_crs(epsg=4326)
    elif gdf.crs is None:
        log.warning("  GeoPackage sans CRS défini — coordonnées supposées déjà en WGS84")

    # Filtre France métropolitaine — le GeoPackage SCHAPI couvre aussi les
    # DOM-TOM (Guadeloupe, etc.), hors de portée du reste du pipeline
    # (HydroSHEDS Europe, bbox ERA5 France métropole...). Décision actée :
    # on garde uniquement la métropole pour l'instant.
    n_before = len(gdf)
    gdf = gdf[
        (gdf.geometry.x >= BBOX_FRANCE["left"]) & (gdf.geometry.x <= BBOX_FRANCE["right"]) &
        (gdf.geometry.y >= BBOX_FRANCE["bottom"]) & (gdf.geometry.y <= BBOX_FRANCE["top"])
    ]
    n_filtered = n_before - len(gdf)
    if n_filtered:
        log.info(f"  {n_filtered} stations hors métropole (DOM-TOM) filtrées "
                 f"({len(gdf)}/{n_before} conservées)")

    # 3. Lister les fichiers CSV
    csv_files = sorted(csv_dir.glob("*.csv"))
    log.info(f"{len(csv_files)} fichiers CSV trouvés dans {csv_dir}")

    if not csv_files:
        log.warning("Aucun fichier CSV trouvé")
        conn.close()
        return {"inserted": 0, "skipped": 0, "errors": 0, "total_measurements": 0}

    # 4. Parser + insérer station par station
    log.info(f"\nParsing + insertion ({len(csv_files)} fichiers)...")
    inserted = skipped = errors = total_meas = 0
    no_coords = 0

    for i, filepath in enumerate(csv_files):
        try:
            metadata, measurements = parse_insitu_file(filepath, gdf)

            if metadata is None:
                log.warning(f"  [{i+1:3d}/{len(csv_files)}] {filepath.name} — nom de fichier non reconnu → skip")
                skipped += 1
                continue

            station_code = metadata["ID"]

            if metadata["REFERENCE LONGITUDE"] is None or metadata["REFERENCE LATITUDE"] is None:
                no_coords += 1
                log.warning(f"  [{i+1:3d}/{len(csv_files)}] {station_code} — "
                            f"pas de coordonnées dans le GeoPackage (étape 2 impossible pour cette station)")

            if len(measurements) < MIN_MEASUREMENTS:
                log.info(f"  [{i+1:3d}/{len(csv_files)}] {station_code} — "
                         f"trop peu de mesures ({len(measurements)}) → skip")
                skipped += 1
                continue

            ok = insert_station(conn, metadata)
            if not ok:
                log.debug(f"  [{i+1:3d}/{len(csv_files)}] {station_code} — déjà présente")

            nb = insert_measurements(conn, station_code, measurements)
            total_meas += nb
            inserted   += 1

            river_display = metadata["RIVER"] or "?"
            log.info(f"  [{i+1:3d}/{len(csv_files)}] {station_code:15s} | "
                     f"{river_display:30s} | "
                     f"{nb} mesures")

        except Exception as e:
            log.error(f"  [{i+1:3d}/{len(csv_files)}] {filepath.name} — erreur : {e}")
            errors += 1

    # 5. Rapport
    log.info(f"\nÉtape 1 (in-situ) terminée : {inserted} stations insérées, "
             f"{skipped} ignorées, {errors} erreurs, "
             f"{total_meas} mesures au total")
    if no_coords:
        log.warning(f"⚠️  {no_coords} stations SANS coordonnées (absentes du GeoPackage) — "
                    f"l'étape 2 (BV/Strahler/etc.) ne pourra rien calculer pour elles")
    print_report(conn)
    conn.close()

    return {
        "inserted"          : inserted,
        "skipped"           : skipped,
        "errors"            : errors,
        "total_measurements": total_meas,
        "no_coords"         : no_coords,
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 1 in-situ — Import CSV → SQLite",
        epilog="""
Exemples :
  python step1_import_insitu.py
  python step1_import_insitu.py --db ./data/insitu.db --reset
  python step1_import_insitu.py --csv-dir ./data/insitu/data --gpkg ./data/insitu/shp/station.gpkg
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH),
                        help=f"Chemin BDD (défaut: {DEFAULT_DB_PATH})")
    parser.add_argument("--csv-dir", type=str, default=str(DEFAULT_CSV_DIR),
                        help=f"Dossier des CSV in-situ (défaut: {DEFAULT_CSV_DIR})")
    parser.add_argument("--gpkg", type=str, default=str(DEFAULT_GPKG_PATH),
                        help=f"Chemin GeoPackage (défaut: {DEFAULT_GPKG_PATH})")
    parser.add_argument("--reset", action="store_true",
                        help="Supprimer et recréer la BDD")
    args = parser.parse_args()

    run_step1_insitu(
        csv_dir  = Path(args.csv_dir),
        gpkg_path= Path(args.gpkg),
        db_path  = Path(args.db),
        reset    = args.reset,
    )