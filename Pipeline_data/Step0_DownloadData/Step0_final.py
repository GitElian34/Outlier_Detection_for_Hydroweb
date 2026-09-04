#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0.py — Récupération de TOUTES les données brutes (étape 0, finale)
═══════════════════════════════════════════════════════════════════════════

Fusion de step0.py + step0pt2.py + step0pt3.py (ce dernier remplacé par
la méthode V2 — copie interne, plus simple et rapide que le
téléchargement API, voir step0pt3_v2.py).

Orchestre 7 sources de données brutes, chacune INDÉPENDANTE (si l'une
échoue, les autres sont quand même tentées) :

    1. HydroWeb Next  → téléchargement API           (step0_fetch_hydroweb_next_raw.py)
    2. In-situ SCHAPI → copie stockage interne        (step0_fetch_insitu_raw.py)
    3. HydroSHEDS     → téléchargement direct         (step0_fetch_hydrosheds.py)
    4. RiverATLAS     → copie stockage interne        (step0_fetch_river_atlas.py)
    5. SoilGrids      → téléchargement WCS            (step0_fetch_soilgrids.py)
    6. SRTM + Corine  → copie stockage interne        (step0_fetch_step2_rasters.py)
    7. ERA5           → copie stockage interne (V2)   (step0pt3_v2.py)

Note : le ROE (barrages, étape 2e) n'a PAS besoin d'entrée ici — il se
télécharge tout seul à l'intérieur de step2e_dist_barrage.py au premier
lancement de l'étape 2.

⚠️ ERA5 utilise la méthode V2 (copie depuis le stockage interne) plutôt
que la V1 (téléchargement API, qui a besoin d'un bbox déduit de bv_data
— donc de l'étape 2 déjà faite, et peut prendre plusieurs JOURS). La V2
ne dépend de rien d'autre : elle peut tourner dès maintenant, avant même
l'étape 1.

N'écrit rien en BDD — c'est uniquement la récupération des fichiers bruts.
Ne fait que réutiliser les fonctions déjà écrites dans chaque script
dédié, sans dupliquer leur logique.

Usage :
    python step0.py
    python step0.py --skip-insitu --skip-step2-rasters --skip-era5   (que le public)
    python step0.py --skip-hydroweb
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_step1.fetch_hydroweb_next import (
    fetch_hydroweb_next_raw,
    DEFAULT_BBOX as HW_DEFAULT_BBOX,
    DEFAULT_OUTPUT_DIR as HW_DEFAULT_OUTPUT_DIR,
    COLLECTION_ID as HW_COLLECTION_ID,
)
from data_step1.fetch_in_situ import (
    fetch_insitu_raw,
    DEFAULT_DEST_DIR as INSITU_DEFAULT_DEST_DIR,
    SOURCE_SHP_DIR as INSITU_SOURCE_SHP_DIR,
    SOURCE_CSV_DIR as INSITU_SOURCE_CSV_DIR,
)
from data_step2.step0_fetch_hydrosheds import fetch_hydrosheds
from data_step2.step0_fetch_river_atlas import (
    fetch_river_atlas,
    SOURCE_DIR as RIVER_ATLAS_SOURCE_DIR,
    SOURCE_SHP_NAME as RIVER_ATLAS_SOURCE_NAME,
)
from data_step2.step0_fetch_soilgrids import fetch_soilgrids, DEFAULT_BBOX as SOILGRIDS_DEFAULT_BBOX
from data_step2.step0_fetch_step2_rasters import (
    fetch_step2_rasters,
    SOURCE_SRTM,
    SOURCE_CORINE,
)
from data_step3.step0pt3_V2 import (
    fetch_era5_internal,
    DEST_USABLE_DATA_DIR as ERA5_DEST_DIR,
    SOURCE_USABLE_DIR as ERA5_SOURCE_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0")


def _run_source(label: str, enabled: bool, fn, results: dict, **kwargs):
    """Exécute une source si activée, capture le succès/échec dans results."""
    if not enabled:
        log.info(f"{label} ignoré (désactivé)")
        return

    print("\n" + "█" * 60)
    print(f"  ÉTAPE 0 — {label}")
    print("█" * 60)
    try:
        out = fn(**kwargs)
        results[label] = {"ok": True, "result": out, "error": None}
    except Exception as e:
        log.error(f"[{label}] échec : {e}")
        results[label] = {"ok": False, "result": None, "error": str(e)}


def run_step0(
    # ── HydroWeb Next ──
    run_hydroweb: bool = True,
    hydroweb_bbox: list[float] = HW_DEFAULT_BBOX,
    hydroweb_output_dir: str = HW_DEFAULT_OUTPUT_DIR,
    hydroweb_collection: str = HW_COLLECTION_ID,

    # ── In-situ ──
    run_insitu: bool = True,
    insitu_dest_dir: Path = INSITU_DEFAULT_DEST_DIR,
    insitu_source_shp: Path = INSITU_SOURCE_SHP_DIR,
    insitu_source_csv: Path = INSITU_SOURCE_CSV_DIR,
    insitu_reset: bool = False,
    insitu_year_filter: str | None = "2025",

    # ── HydroSHEDS / RiverATLAS / SoilGrids ──
    run_hydrosheds: bool = True,
    run_river_atlas: bool = True,
    river_atlas_source_dir: Path = RIVER_ATLAS_SOURCE_DIR,
    river_atlas_source_name: str = RIVER_ATLAS_SOURCE_NAME,
    run_soilgrids: bool = True,
    soilgrids_bbox: tuple = SOILGRIDS_DEFAULT_BBOX,

    # ── SRTM + Corine (interne) ──
    run_step2_rasters: bool = True,
    step2_rasters_source_srtm: Path = SOURCE_SRTM,
    step2_rasters_source_corine: Path = SOURCE_CORINE,

    # ── ERA5 (V2, interne) ──
    run_era5: bool = True,
    era5_dest_dir: str = ERA5_DEST_DIR,
    era5_source_dir: Path = ERA5_SOURCE_DIR,
    era5_reset: bool = False,
) -> dict:
    """
    Lance la récupération des données brutes pour les 7 sources.

    Chaque source est indépendante : si l'une échoue, les autres sont
    quand même tentées. Le détail des erreurs est dans le résultat
    retourné.

    Returns:
        Dict {label: {"ok": bool, "result": ..., "error": str | None}}
    """
    results = {}

    _run_source(
        "HydroWeb Next", run_hydroweb, fetch_hydroweb_next_raw, results,
        bbox=hydroweb_bbox, output_dir=hydroweb_output_dir,
        collection_id=hydroweb_collection,
    )

    _run_source(
        "In-situ SCHAPI", run_insitu, fetch_insitu_raw, results,
        dest_dir=insitu_dest_dir, source_shp_dir=insitu_source_shp,
        source_csv_dir=insitu_source_csv, reset=insitu_reset,
        year_filter=insitu_year_filter,
    )

    _run_source(
        "HydroSHEDS", run_hydrosheds, fetch_hydrosheds, results,
    )

    _run_source(
        "RiverATLAS", run_river_atlas, fetch_river_atlas, results,
        source_dir=river_atlas_source_dir, source_shp_name=river_atlas_source_name,
    )

    _run_source(
        "SoilGrids", run_soilgrids, fetch_soilgrids, results,
        bbox=soilgrids_bbox,
    )

    _run_source(
        "SRTM + Corine", run_step2_rasters, fetch_step2_rasters, results,
        source_srtm=step2_rasters_source_srtm,
        source_corine=step2_rasters_source_corine,
    )

    _run_source(
        "ERA5 (copie interne)", run_era5, fetch_era5_internal, results,
        dest_dir=era5_dest_dir, source_dir=era5_source_dir, reset=era5_reset,
    )

    # ── Rapport ──────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  RAPPORT ÉTAPE 0")
    print("═" * 60)
    for source, res in results.items():
        status = "✅" if res["ok"] else "❌"
        print(f"  {status} {source}")
        if not res["ok"]:
            print(f"      → {res['error']}")
    print("═" * 60)
    print("  ℹ️  ROE (barrages) : pas besoin ici, se télécharge tout seul")
    print("     au premier lancement de l'étape 2 (step2e_dist_barrage.py)")
    print("═" * 60)

    return results


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 — Récupération de toutes les données brutes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python step0.py
  python step0.py --skip-insitu --skip-step2-rasters --skip-era5
  python step0.py --skip-hydroweb
        """,
    )

    # ── HydroWeb Next ──
    parser.add_argument("--skip-hydroweb", action="store_true")
    parser.add_argument("--bbox", type=float, nargs=4, default=HW_DEFAULT_BBOX,
                        metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"))
    parser.add_argument("--hydroweb-out", type=str, default=HW_DEFAULT_OUTPUT_DIR)
    parser.add_argument("--collection", type=str, default=HW_COLLECTION_ID)

    # ── In-situ ──
    parser.add_argument("--skip-insitu", action="store_true")
    parser.add_argument("--insitu-dest", type=str, default=str(INSITU_DEFAULT_DEST_DIR))
    parser.add_argument("--insitu-source-shp", type=str, default=str(INSITU_SOURCE_SHP_DIR))
    parser.add_argument("--insitu-source-csv", type=str, default=str(INSITU_SOURCE_CSV_DIR))
    parser.add_argument("--insitu-reset", action="store_true")
    parser.add_argument("--insitu-year", type=str, default="2025")

    # ── HydroSHEDS / RiverATLAS / SoilGrids ──
    parser.add_argument("--skip-hydrosheds", action="store_true")
    parser.add_argument("--skip-river-atlas", action="store_true")
    parser.add_argument("--river-atlas-source-dir", type=str, default=str(RIVER_ATLAS_SOURCE_DIR))
    parser.add_argument("--river-atlas-source-name", type=str, default=RIVER_ATLAS_SOURCE_NAME)
    parser.add_argument("--skip-soilgrids", action="store_true")
    parser.add_argument("--soilgrids-bbox", type=float, nargs=4,
                        default=SOILGRIDS_DEFAULT_BBOX,
                        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))

    # ── SRTM + Corine (interne) ──
    parser.add_argument("--skip-step2-rasters", action="store_true")
    parser.add_argument("--source-srtm", type=str, default=str(SOURCE_SRTM))
    parser.add_argument("--source-corine", type=str, default=str(SOURCE_CORINE))

    # ── ERA5 (V2, interne) ──
    parser.add_argument("--skip-era5", action="store_true")
    parser.add_argument("--era5-dest", type=str, default=ERA5_DEST_DIR)
    parser.add_argument("--era5-source", type=str, default=str(ERA5_SOURCE_DIR))
    parser.add_argument("--era5-reset", action="store_true")

    args = parser.parse_args()

    run_step0(
        run_hydroweb=not args.skip_hydroweb,
        hydroweb_bbox=args.bbox,
        hydroweb_output_dir=args.hydroweb_out,
        hydroweb_collection=args.collection,

        run_insitu=not args.skip_insitu,
        insitu_dest_dir=Path(args.insitu_dest),
        insitu_source_shp=Path(args.insitu_source_shp),
        insitu_source_csv=Path(args.insitu_source_csv),
        insitu_reset=args.insitu_reset,
        insitu_year_filter=args.insitu_year or None,

        run_hydrosheds=not args.skip_hydrosheds,
        run_river_atlas=not args.skip_river_atlas,
        river_atlas_source_dir=Path(args.river_atlas_source_dir),
        river_atlas_source_name=args.river_atlas_source_name,
        run_soilgrids=not args.skip_soilgrids,
        soilgrids_bbox=tuple(args.soilgrids_bbox),

        run_step2_rasters=not args.skip_step2_rasters,
        step2_rasters_source_srtm=Path(args.source_srtm),
        step2_rasters_source_corine=Path(args.source_corine),

        run_era5=not args.skip_era5,
        era5_dest_dir=args.era5_dest,
        era5_source_dir=Path(args.era5_source),
        era5_reset=args.era5_reset,
    )