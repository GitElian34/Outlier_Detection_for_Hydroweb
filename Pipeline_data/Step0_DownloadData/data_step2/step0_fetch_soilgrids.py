#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_soilgrids.py — Téléchargement SoilGrids (clay/sand/silt)
═══════════════════════════════════════════════════════════════════════════

Télécharge les 9 rasters SoilGrids attendus par step2d_corine_soilgrids.py
(clay/sand/silt × 3 profondeurs 0-30cm), via le service WCS d'ISRIC —
libre d'accès, pas de compte requis.

Adapté du script WCS fourni (owslib), même logique de skip si déjà
téléchargé.

Prérequis : pip install owslib rasterio

Usage :
    python step0_fetch_soilgrids.py
    python step0_fetch_soilgrids.py --bbox 5.5 47.0 15.5 55.5   (Allemagne)
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
from pathlib import Path

import rasterio
from owslib.wcs import WebCoverageService

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step2_Bassin_Versant.config_step2 import (
    SOILGRIDS_DIR as DEST_SOILGRIDS_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_soilgrids")

DEFAULT_BBOX = (-6.0, 41.0, 10.0, 52.0)  # min_lon, min_lat, max_lon, max_lat — France
RESOLUTION = 0.002  # ~200m en degrés

VARIABLES = ["clay", "sand", "silt"]
DEPTHS = ["0-5cm_mean", "5-15cm_mean", "15-30cm_mean"]


def fetch_soilgrids(
    output_dir: str = DEST_SOILGRIDS_DIR,
    bbox: tuple = DEFAULT_BBOX,
    resolution: float = RESOLUTION,
) -> dict:
    """
    Télécharge les 9 rasters SoilGrids (clay/sand/silt × 3 profondeurs)
    sur le bbox donné, via le service WCS d'ISRIC.

    Args:
        output_dir: dossier de destination (doit correspondre à
                    SOILGRIDS_DIR dans config_step2.py)
        bbox: (min_lon, min_lat, max_lon, max_lat)
        resolution: résolution en degrés (~0.002 ≈ 200m)

    Returns:
        {"downloaded": n, "skipped": n, "errors": n}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    total = len(VARIABLES) * len(DEPTHS)
    downloaded = skipped = errors = 0
    compteur = 0

    for var in VARIABLES:
        url = f"https://maps.isric.org/mapserv?map=/map/{var}.map"
        log.info(f"── {var.upper()} ──")

        try:
            wcs = WebCoverageService(url, version="1.0.0")
        except Exception as e:
            log.error(f"  ❌ Connexion impossible : {e}")
            errors += len(DEPTHS)
            continue

        for depth in DEPTHS:
            compteur += 1
            identifier = f"{var}_{depth}"
            output_path = output_dir / f"{identifier}.tif"

            if output_path.exists():
                log.info(f"  [{compteur}/{total}] {identifier} — déjà téléchargé, skip")
                skipped += 1
                continue

            log.info(f"  [{compteur}/{total}] {identifier}...")
            try:
                response = wcs.getCoverage(
                    identifier=identifier,
                    crs="urn:ogc:def:crs:EPSG::4326",
                    bbox=bbox,
                    resx=resolution,
                    resy=resolution,
                    format="GEOTIFF_INT16",
                )
                data = response.read()

                with open(output_path, "wb") as f:
                    f.write(data)

                with rasterio.open(output_path) as src:
                    log.info(f"    ✅ {src.width}×{src.height} px | "
                             f"{output_path.stat().st_size / 1e6:.1f} Mo")
                downloaded += 1

            except Exception as e:
                log.error(f"    ❌ {e}")
                if output_path.exists():
                    output_path.unlink()
                errors += 1

    log.info(f"Terminé : {downloaded} téléchargés, {skipped} déjà présents, {errors} erreurs")
    return {"downloaded": downloaded, "skipped": skipped, "errors": errors}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 — Téléchargement SoilGrids (clay/sand/silt)",
    )
    parser.add_argument("--output", type=str, default=DEST_SOILGRIDS_DIR,
                        help=f"Dossier de sortie (défaut: {DEST_SOILGRIDS_DIR})")
    parser.add_argument("--bbox", type=float, nargs=4, default=DEFAULT_BBOX,
                        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
                        help=f"Bbox (défaut: France {DEFAULT_BBOX})")
    parser.add_argument("--resolution", type=float, default=RESOLUTION,
                        help=f"Résolution en degrés (défaut: {RESOLUTION})")
    args = parser.parse_args()

    fetch_soilgrids(
        output_dir=args.output,
        bbox=tuple(args.bbox),
        resolution=args.resolution,
    )
