#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
run_step2_bis.py — Lance l'étape 2 avec les chemins de config_step2_bis.py
═══════════════════════════════════════════════════════════════════════════

Ne modifie ni step2_run_all.py ni config_step2.py — se contente d'appeler
run_step2() (déjà existant) en lui passant explicitement les chemins de
config_step2_bis.py via ses kwargs (dir_path, acc_path, river_atlas_path,
dem_path, slope_path, corine_path, soilgrids_dir, roe_dir — tous déjà
supportés par run_step2 depuis le début).

Usage :
    python run_step2_bis.py --db ./ta_bdd.db
    python run_step2_bis.py --db ./ta_bdd.db --bbox 5.5 47.0 15.5 55.5
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Pipeline_data.Step2_Bassin_Versant.step2_data_Watershed import run_step2
from Pipeline_data.Step2_Bassin_Versant import config_step2_bis as cfg

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 2 sur data/Step2_bis (config_step2_bis.py)",
    )
    parser.add_argument("--db", type=str, required=True)
    parser.add_argument("--bbox", type=float, nargs=4, default=None,
                        metavar=("LEFT", "BOTTOM", "RIGHT", "TOP"))
    args = parser.parse_args()

    bbox = None
    if args.bbox:
        left, bottom, right, top = args.bbox
        bbox = {"left": left, "bottom": bottom, "right": right, "top": top}

    run_step2(
        db_path=args.db,
        bbox=bbox,
        dir_path=cfg.DIR_PATH,
        acc_path=cfg.ACC_PATH,
        river_atlas_path=cfg.RIVER_ATLAS_PATH,
        dem_path=cfg.DEM_PATH,
        slope_path=cfg.SLOPE_PATH,
        corine_path=cfg.CORINE_PATH,
        soilgrids_dir=cfg.SOILGRIDS_DIR,
        roe_dir=cfg.ROE_DIR,
    )