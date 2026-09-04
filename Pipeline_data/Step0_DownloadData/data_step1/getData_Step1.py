#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_pt2.py — Récupération de TOUTES les données brutes (étape 0 globale)
═══════════════════════════════════════════════════════════════════════════

Orchestre les 2 sources de données brutes avant l'étape 1 :
    1. HydroWeb Next  → téléchargement API (step0_fetch_hydroweb_next_raw.py)
    2. In-situ SCHAPI → copie depuis le stockage interne (step0_fetch_insitu_raw.py)

N'écrit rien en BDD — c'est uniquement la récupération des fichiers bruts.
Ne fait que réutiliser les fonctions déjà écrites dans les 2 scripts
dédiés, sans dupliquer leur logique.

Usage :
    python step0_pt2.py
    python step0_pt2.py --skip-insitu
    python step0_pt2.py --skip-hydroweb
    python step0_pt2.py --bbox -5.5 41.0 9.5 51.5 --hydroweb-out ./data/Step1_bis/hydroweb_next_France
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from Pipeline_data.Step0_DownloadData.data_step1.fetch_hydroweb_next import (
    fetch_hydroweb_next_raw,
    DEFAULT_BBOX as HW_DEFAULT_BBOX,
    DEFAULT_OUTPUT_DIR as HW_DEFAULT_OUTPUT_DIR,
    COLLECTION_ID as HW_COLLECTION_ID,
)
from Pipeline_data.Step0_DownloadData.data_step1.fetch_in_situ import (
    fetch_insitu_raw,
    DEFAULT_DEST_DIR as INSITU_DEFAULT_DEST_DIR,
    SOURCE_SHP_DIR as INSITU_SOURCE_SHP_DIR,
    SOURCE_CSV_DIR as INSITU_SOURCE_CSV_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0")


def run_step0(
    run_hydroweb: bool = True,
    hydroweb_bbox: list[float] = HW_DEFAULT_BBOX,
    hydroweb_output_dir: str = HW_DEFAULT_OUTPUT_DIR,
    hydroweb_collection: str = HW_COLLECTION_ID,
    run_insitu: bool = True,
    insitu_dest_dir: Path = INSITU_DEFAULT_DEST_DIR,
    insitu_source_shp: Path = INSITU_SOURCE_SHP_DIR,
    insitu_source_csv: Path = INSITU_SOURCE_CSV_DIR,
    insitu_reset: bool = False,
    insitu_year_filter: str | None = "2025",
) -> dict:
    """
    Lance la récupération des données brutes pour les 2 sources.

    Chaque source est indépendante : si l'une échoue (ex: réseau interne
    inaccessible pour l'in-situ, ou API HydroWeb Next indisponible),
    l'autre est quand même tentée. Le détail des erreurs est dans le
    résultat retourné.

    Returns:
        {
            "hydroweb": {"ok": bool, "output_dir": str | None, "error": str | None},
            "insitu":   {"ok": bool, "result": dict | None, "error": str | None},
        }
    """
    results = {}

    # ══════════════════════════════════════════════════════════
    # SOURCE 1 — HydroWeb Next (API)
    # ══════════════════════════════════════════════════════════
    if run_hydroweb:
        print("\n" + "█" * 60)
        print("  ÉTAPE 0 — HydroWeb Next (téléchargement API)")
        print("█" * 60)
        try:
            output_dir = fetch_hydroweb_next_raw(
                bbox=hydroweb_bbox,
                output_dir=hydroweb_output_dir,
                collection_id=hydroweb_collection,
            )
            results["hydroweb"] = {"ok": True, "output_dir": output_dir, "error": None}
        except Exception as e:
            log.error(f"[HydroWeb Next] échec : {e}")
            results["hydroweb"] = {"ok": False, "output_dir": None, "error": str(e)}
    else:
        log.info("HydroWeb Next ignoré (--skip-hydroweb)")

    # ══════════════════════════════════════════════════════════
    # SOURCE 2 — In-situ SCHAPI (copie interne)
    # ══════════════════════════════════════════════════════════
    if run_insitu:
        print("\n" + "█" * 60)
        print("  ÉTAPE 0 — In-situ SCHAPI (copie depuis le stockage interne)")
        print("█" * 60)
        try:
            insitu_result = fetch_insitu_raw(
                dest_dir=insitu_dest_dir,
                source_shp_dir=insitu_source_shp,
                source_csv_dir=insitu_source_csv,
                reset=insitu_reset,
                year_filter=insitu_year_filter,
            )
            results["insitu"] = {"ok": True, "result": insitu_result, "error": None}
        except Exception as e:
            log.error(f"[In-situ] échec : {e}")
            results["insitu"] = {"ok": False, "result": None, "error": str(e)}
    else:
        log.info("In-situ ignoré (--skip-insitu)")

    # ══════════════════════════════════════════════════════════
    # RAPPORT
    # ══════════════════════════════════════════════════════════
    print("\n" + "═" * 60)
    print("  RAPPORT ÉTAPE 0")
    print("═" * 60)
    for source, res in results.items():
        status = "✅" if res["ok"] else "❌"
        print(f"  {status} {source}")
        if not res["ok"]:
            print(f"      → {res['error']}")
    print("═" * 60)

    return results


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 globale — Récupération de toutes les données brutes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python step0_pt2.py
  python step0_pt2.py --skip-insitu
  python step0_pt2.py --skip-hydroweb
  python step0_pt2.py --bbox -5.5 41.0 9.5 51.5 --hydroweb-out ./data/Step1_bis/hydroweb_next_France
        """,
    )

    # ── HydroWeb Next ──
    parser.add_argument("--skip-hydroweb", action="store_true",
                        help="Ne pas télécharger HydroWeb Next")
    parser.add_argument("--bbox", type=float, nargs=4, default=HW_DEFAULT_BBOX,
                        metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"),
                        help=f"Bbox HydroWeb Next (défaut: France {HW_DEFAULT_BBOX})")
    parser.add_argument("--hydroweb-out", type=str, default=HW_DEFAULT_OUTPUT_DIR,
                        help=f"Dossier de sortie HydroWeb Next (défaut: {HW_DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--collection", type=str, default=HW_COLLECTION_ID,
                        help=f"Collection HydroWeb Next (défaut: {HW_COLLECTION_ID})")

    # ── In-situ ──
    parser.add_argument("--skip-insitu", action="store_true",
                        help="Ne pas copier les données in-situ")
    parser.add_argument("--insitu-dest", type=str, default=str(INSITU_DEFAULT_DEST_DIR),
                        help=f"Dossier de destination in-situ (défaut: {INSITU_DEFAULT_DEST_DIR})")
    parser.add_argument("--insitu-source-shp", type=str, default=str(INSITU_SOURCE_SHP_DIR),
                        help="Dossier source du GeoPackage/shapefile (interne)")
    parser.add_argument("--insitu-source-csv", type=str, default=str(INSITU_SOURCE_CSV_DIR),
                        help="Dossier source des CSV stations (interne)")
    parser.add_argument("--insitu-reset", action="store_true",
                        help="Vider et recopier entièrement les données in-situ")
    parser.add_argument("--insitu-year", type=str, default="2025",
                        help="Filtre année sur le dossier shp/ in-situ (défaut: 2025)")

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
    )