#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0pt3.py — Récupération des données brutes ERA5 (étape 0, partie 3)
═══════════════════════════════════════════════════════════════════════════

Fichier séparé de step0.py / step0pt2.py (à fusionner ensemble plus
tard). Orchestre :
    1. Météo (precip + PET + température)  → step0_fetch_era5_meteo.py
    2. Neige (snow_depth + snowmelt)        → step0_fetch_era5_snow.py

Le bbox est, par défaut, auto-détecté depuis les polygones bv_data de la
BDD donnée (--db) — nécessite que l'étape 2a ait déjà tourné dessus.
Sinon, passe --bbox explicitement (format CDS : Nord Ouest Sud Est).

Usage :
    python step0pt3.py --db ./ta_bdd.db
    python step0pt3.py --bbox 52 -6 40 10
    python step0pt3.py --db ./ta_bdd.db --start 2020-01-01 --end 2020-12-31
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from step0_fetch_era5_meteo import fetch_era5_meteo
from step0_fetch_era5_snow import fetch_era5_snow
from Pipeline_data.Step3_ERA5.config_step3 import (
    START_DATE as DEFAULT_START_DATE,
    END_DATE as DEFAULT_END_DATE,
    RAW_DATA_DIR as DEFAULT_RAW_DATA_DIR,
    USABLE_DATA_DIR as DEFAULT_USABLE_DATA_DIR,
    get_bbox_from_bv,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0pt3")


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


def run_step0pt3(
    db_path: str | None = None,
    bbox: list[float] | None = None,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    raw_dir: str = DEFAULT_RAW_DATA_DIR,
    usable_dir: str = DEFAULT_USABLE_DATA_DIR,
    run_meteo: bool = True,
    run_snow: bool = True,
) -> dict:
    """
    Lance la récupération ERA5 (météo + neige) pour la période/bbox donnés.

    Args:
        db_path: si bbox est None, sert à auto-détecter le bbox depuis
                 bv_data (nécessite l'étape 2a déjà faite sur cette BDD)
        bbox: [Nord, Ouest, Sud, Est]. Prioritaire sur db_path si fourni.

    Returns:
        Dict {label: {"ok": bool, "result": ..., "error": str | None}}
    """
    results = {}

    if bbox is None and db_path:
        conn = sqlite3.connect(db_path)
        bbox = get_bbox_from_bv(conn)
        conn.close()
        log.info(f"Bbox auto-détecté depuis bv_data ({db_path}) : {bbox}")
    elif bbox is None:
        log.warning("Ni --bbox ni --db fournis : utilisation du défaut "
                     "(BBOX_FRANCE de config_step3.py)")

    _run_source(
        "ERA5 météo (precip/PET/temp)", run_meteo, fetch_era5_meteo, results,
        start_date=start_date, end_date=end_date, bbox=bbox,
        raw_dir=raw_dir, usable_dir=usable_dir,
    )

    _run_source(
        "ERA5 neige (snow_depth/snowmelt)", run_snow, fetch_era5_snow, results,
        start_date=start_date, end_date=end_date, bbox=bbox,
        raw_dir=raw_dir, usable_dir=usable_dir,
    )

    # ── Rapport ──────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  RAPPORT ÉTAPE 0 (partie 3 — ERA5)")
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
        description="Étape 0 (partie 3) — ERA5 météo + neige",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python step0pt3.py --db ./database/hydroweb_next_France.db
  python step0pt3.py --bbox 52 -6 40 10
  python step0pt3.py --db ./ta_bdd.db --start 2020-01-01 --end 2020-12-31
        """,
    )
    parser.add_argument("--db", type=str, default=None,
                        help="BDD pour auto-détecter le bbox depuis bv_data")
    parser.add_argument("--bbox", type=float, nargs=4, default=None,
                        metavar=("NORD", "OUEST", "SUD", "EST"))
    parser.add_argument("--start", type=str, default=DEFAULT_START_DATE)
    parser.add_argument("--end", type=str, default=DEFAULT_END_DATE)
    parser.add_argument("--raw-dir", type=str, default=DEFAULT_RAW_DATA_DIR)
    parser.add_argument("--usable-dir", type=str, default=DEFAULT_USABLE_DATA_DIR)
    parser.add_argument("--skip-meteo", action="store_true")
    parser.add_argument("--skip-snow", action="store_true")
    args = parser.parse_args()

    run_step0pt3(
        db_path=args.db,
        bbox=args.bbox,
        start_date=args.start,
        end_date=args.end,
        raw_dir=args.raw_dir,
        usable_dir=args.usable_dir,
        run_meteo=not args.skip_meteo,
        run_snow=not args.skip_snow,
    )
