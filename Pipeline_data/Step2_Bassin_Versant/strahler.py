#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step2b_strahler.py — Ordre de Strahler (RiverATLAS)
═══════════════════════════════════════════════════════════════════════════

Pour chaque station, trouve le tronçon RiverATLAS le plus proche et
extrait l'ordre de Strahler.

Prérequis :
    pip install geopandas pandas
    Fichier : RiverATLAS_v10_eu.shp

⚠️ CHANGEMENT vs version précédente (fix bug) :
    Le bbox utilisé pour charger RiverATLAS était figé sur la France
    (FRANCE_BBOX codé en dur), quelle que soit la BDD traitée. Une BDD
    couvrant une autre zone (Allemagne, in-situ...) perdait silencieusement
    son Strahler pour les stations hors de ce bbox — aucune erreur visible,
    juste des valeurs jamais remplies.
    Le bbox est maintenant, comme pour step2a :
      - fourni explicitement (paramètre bbox), ou
      - déduit automatiquement des coordonnées des stations sans Strahler
        en base, avec une marge de sécurité.
    FRANCE_BBOX reste dispo pour un usage manuel explicite si besoin.

⚠️ CHANGEMENT (config centrale) :
    DEFAULT_RIVER_ATLAS vient maintenant de config_step2.py (source
    unique), au lieu d'un chemin local qui divergeait de celui utilisé
    par l'orchestrateur step2_run_all.py (sous-dossier HydroSHED/ manquant
    dans l'ancien défaut).
═══════════════════════════════════════════════════════════════════════════
"""

import logging
import sqlite3
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step2_Bassin_Versant.config_step2 import (
    RIVER_ATLAS_PATH as DEFAULT_RIVER_ATLAS,
    BBOX_MARGIN_DEG,
    BBOX_FRANCE,
    bbox_dict_to_tuple,
)

log = logging.getLogger("step2b")

DIST_SEUIL_M = 5000


def _get_bbox_from_stations_df(stations: pd.DataFrame,
                               margin_deg: float = BBOX_MARGIN_DEG) -> tuple:
    """
    Calcule un bbox (left, bottom, right, top) englobant un DataFrame de
    stations (colonnes lon/lat), avec une marge de sécurité en degrés.
    Même logique que get_bbox_from_stations() dans step2a_delineate_bv.py,
    adaptée ici à un DataFrame plutôt qu'une liste de dicts (format déjà
    utilisé par ce sous-module).
    """
    lon_min, lon_max = stations["lon"].min(), stations["lon"].max()
    lat_min, lat_max = stations["lat"].min(), stations["lat"].max()

    bbox = (
        lon_min - margin_deg,
        lat_min - margin_deg,
        lon_max + margin_deg,
        lat_max + margin_deg,
    )
    log.info(f"Bbox auto-détecté depuis {lon_min:.2f},{lat_min:.2f} → "
             f"{lon_max:.2f},{lat_max:.2f} (marge {margin_deg}°) : {bbox}")
    return bbox


def run_step2b(conn: sqlite3.Connection,
               river_atlas_path: str = DEFAULT_RIVER_ATLAS,
               bbox: dict | tuple | None = None) -> dict:
    """
    Étape 2b : calcule l'ordre de Strahler pour toutes les stations.

    Args:
        conn: Connexion à la BDD pipeline
        river_atlas_path: Chemin vers RiverATLAS
        bbox: Zone de chargement de RiverATLAS. Accepte soit un dict
              {"left","right","bottom","top"} (même format que step2a,
              pour un appel uniforme depuis run_step2), soit un tuple
              (left, bottom, right, top) (format geopandas natif).
              Si None (défaut), déduit automatiquement des coordonnées
              des stations sans Strahler en base, avec une marge de
              sécurité — comme step2a.

    Returns:
        {"updated": n, "suspects": n}
    """
    from Pipeline_data.Database.db_operations import update_strahler_batch

    # 1. Charger les stations D'ABORD (nécessaire pour l'auto-bbox)
    stations = pd.read_sql("""
        SELECT station_code, reference_longitude AS lon, reference_latitude AS lat
        FROM stations
        WHERE reference_longitude IS NOT NULL AND reference_latitude IS NOT NULL
          AND strahler IS NULL
    """, conn)
    log.info(f"  {len(stations)} stations sans Strahler")

    if stations.empty:
        log.info("Toutes les stations ont déjà un Strahler")
        return {"updated": 0, "suspects": 0}

    # 2. Déterminer le bbox de chargement de RiverATLAS
    if bbox is None:
        bbox_tuple = _get_bbox_from_stations_df(stations)
    elif isinstance(bbox, dict):
        bbox_tuple = bbox_dict_to_tuple(bbox)
        log.info(f"Bbox fourni explicitement : {bbox}")
    else:
        bbox_tuple = tuple(bbox)
        log.info(f"Bbox fourni explicitement : {bbox_tuple}")

    # 3. Charger RiverATLAS sur ce bbox
    log.info("Chargement RiverATLAS...")
    rivers = gpd.read_file(river_atlas_path, bbox=bbox_tuple)
    log.info(f"  {len(rivers)} tronçons chargés")

    if "ORD_STRA" not in rivers.columns:
        log.error("Colonne ORD_STRA introuvable dans RiverATLAS")
        return {"updated": 0, "suspects": 0}

    # 4. GeoDataFrame + reprojection mètres
    stations_gdf = gpd.GeoDataFrame(
        stations,
        geometry=gpd.points_from_xy(stations.lon, stations.lat),
        crs="EPSG:4326",
    ).to_crs("EPSG:3857")

    rivers = rivers.to_crs("EPSG:3857")

    # 5. sjoin_nearest
    log.info("Matching stations → tronçons RiverATLAS...")
    result = gpd.sjoin_nearest(
        stations_gdf,
        rivers[["geometry", "ORD_STRA"]],
        how="left",
        distance_col="dist_m",
    )

    # 6. Contrôle qualité
    suspects = result[result["dist_m"] > DIST_SEUIL_M]
    if not suspects.empty:
        log.warning(f"{len(suspects)} stations à >{DIST_SEUIL_M/1000:.0f}km d'un tronçon")

    # 7. Insérer
    valid = result.dropna(subset=["ORD_STRA"])
    updates = [(int(row["ORD_STRA"]), row["station_code"]) for _, row in valid.iterrows()]
    n = update_strahler_batch(conn, updates)

    log.info(f"Étape 2b terminée : {n} stations avec Strahler")
    return {"updated": n, "suspects": len(suspects)}


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(
        description="Étape 2b — Strahler",
        epilog="""
Exemples :
  python step2b_strahler.py --db ./data/test.db
      (bbox auto-détecté depuis les stations sans Strahler en base)

  python step2b_strahler.py --db ./data/test.db --bbox 5.5 47.0 15.5 55.5
      (bbox forcé, ici Allemagne — ordre LEFT BOTTOM RIGHT TOP)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", type=str, default="./data/test.db")
    parser.add_argument("--atlas", type=str, default=DEFAULT_RIVER_ATLAS)
    parser.add_argument("--bbox", type=float, nargs=4, default=None,
                        metavar=("LEFT", "BOTTOM", "RIGHT", "TOP"),
                        help="Bbox explicite (défaut : auto-détecté depuis les stations)")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    bbox = tuple(args.bbox) if args.bbox else None
    run_step2b(conn, args.atlas, bbox=bbox)
    conn.close()