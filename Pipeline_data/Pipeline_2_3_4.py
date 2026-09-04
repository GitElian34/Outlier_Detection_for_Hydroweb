#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
pipeline_23_4.py — Étapes 2 → 3 → 4 sur une BDD déjà remplie (étape 1)
═══════════════════════════════════════════════════════════════════════════

Prend en entrée une BDD SQLite déjà peuplée par une étape 1 (HydroWeb,
in-situ, ou toute autre source respectant le schéma commun — table
`stations` avec station_code, `measurements` avec station_code/measure_date/
orthometric_height/is_valid, etc.) et enchaîne :

    2. Attributs station (BV + Strahler + Elevation + Corine + ROE)
    3. Step3_ERA5 sur BV + features (pixels + météo + neige + moyennes glissantes)
    4. Génération des fichiers .nc + attributes.csv (NeuralHydrology)

Usage :
    python pipeline_23_4.py --db ./data/test.db
    python pipeline_23_4.py --db ./data/insitu_data.db --step 3
    python pipeline_23_4.py --db ./data/test.db --output ./data/IA/MonDataset --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Pipeline_data.Step2_Bassin_Versant.step2_data_Watershed import run_step2
from Pipeline_data.Step3_ERA5.Step3_ERA5_compute import run_step3
from Pipeline_data.Step4_DB_to_NetCDF.step4_db_to_ncdf import run_step4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline_23_4")


def format_duration(seconds: float) -> str:
    """Formate une durée en secondes en HH:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    elif m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def run_pipeline_23_4(
    db_path: str,
    output_dir: str = "./data/IA/Dataset",
    era5_base: str = "./data/Step3_ERA5/usable_data_LAND_France",
    date_deb: str = "2016-01-01",
    date_fin: str = "2025-12-31",
    start_step: int = 2,
    reset: bool = False,
) -> dict:
    """
    Enchaîne étapes 2, 3, 4 sur une BDD déjà remplie par l'étape 1.

    Args:
        db_path: BDD SQLite en entrée (déjà peuplée par une étape 1 quelconque)
        output_dir: dossier de sortie pour les .nc / attributes.csv (étape 4)
        era5_base: chemin racine des fichiers Step3_ERA5 (étape 3)
        date_deb: date de début pour la génération des séries (étape 4)
        date_fin: date de fin pour la génération des séries (étape 4)
        start_step: étape à laquelle commencer (2, 3 ou 4)
        reset: pour l'étape 4, régénère les .nc existants / vide output_dir

    Returns:
        Dict {"step2": ..., "step3": ..., "step4": ...}
    """
    results = {}
    t_start = time.time()

    if start_step <= 2:
        print("\n" + "█" * 60)
        print("  ÉTAPE 2/4 — Attributs station (BV + Strahler + ...)")
        print("█" * 60)
        t2 = time.time()
        results["step2"] = run_step2(db_path=db_path)
        log.info(f"Étape 2 terminée en {format_duration(time.time() - t2)}")

    if start_step <= 3:
        print("\n" + "█" * 60)
        print("  ÉTAPE 3/4 — Step3_ERA5 sur BV + features")
        print("█" * 60)
        t3 = time.time()
        results["step3"] = run_step3(db_path=db_path, era5_base=era5_base)
        log.info(f"Étape 3 terminée en {format_duration(time.time() - t3)}")

    if start_step <= 4:
        print("\n" + "█" * 60)
        print("  ÉTAPE 4/4 — Génération dataset (.nc + attributes.csv)")
        print("█" * 60)
        t4 = time.time()
        results["step4"] = run_step4(
            db_path=db_path,
            output_dir=output_dir,
            date_deb=date_deb,
            date_fin=date_fin,
            reset=reset,
        )
        log.info(f"Étape 4 terminée en {format_duration(time.time() - t4)}")

    total_time = time.time() - t_start
    print(f"\n⏱️  Pipeline 2→3→4 terminée en {format_duration(total_time)}")
    print(f"  BDD          : {db_path}")
    print(f"  Dataset      : {output_dir}")

    return results


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étapes 2 → 3 → 4, à partir d'une BDD déjà remplie par l'étape 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python pipeline_23_4.py --db ./data/test.db
  python pipeline_23_4.py --db ./data/insitu_data.db --step 3
  python pipeline_23_4.py --db ./data/test.db --output ./data/IA/MonDataset --reset
        """,
    )
    parser.add_argument("--db", type=str, required=True,
                        help="Chemin vers la BDD (déjà remplie par l'étape 1)")
    parser.add_argument("--output", type=str, default="./data/IA/Dataset",
                        help="Dossier de sortie du dataset (étape 4)")
    parser.add_argument("--era5", type=str,
                        default="./data/Step3_ERA5/usable_data_LAND_France",
                        help="Chemin racine Step3_ERA5")
    parser.add_argument("--deb", type=str, default="2016-01-01",
                        help="Date de début (étape 4)")
    parser.add_argument("--fin", type=str, default="2025-12-31",
                        help="Date de fin (étape 4)")
    parser.add_argument("--step", type=int, default=2, choices=[2, 3, 4],
                        help="Étape à laquelle commencer (défaut: 2)")
    parser.add_argument("--reset", action="store_true",
                        help="Régénère les .nc existants (étape 4)")
    args = parser.parse_args()

    run_pipeline_23_4(
        db_path=args.db,
        output_dir=args.output,
        era5_base=args.era5,
        date_deb=args.deb,
        date_fin=args.fin,
        start_step=args.step,
        reset=args.reset,
    )