#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
pipeline_0_4.py — Étapes 0 → 1 → 2 → 3 → 4, source au choix
═══════════════════════════════════════════════════════════════════════════

Extension de pipeline_23_4.py : ajoute la récupération des données brutes
(étape 0, toutes sources) et l'import en BDD (étape 1, source au choix via
--source hydroweb|insitu) avant d'enchaîner les étapes 2/3/4 déjà en place.

    0. Récupération données brutes (7 sources)        → step0.py
    1. Import BDD (HydroWeb OU in-situ, au choix)      → step1_importWaterLvL.py / step1_stations_in_situ.py
    2. Attributs station (BV + Strahler + ...)         → step2_data_Watershed.py
    3. Step3_ERA5 sur BV + features                    → Step3_ERA5_compute.py
    4. Génération .nc + attributes.csv (source au choix aussi) :
         - hydroweb → step4_db_to_ncdf.py (multi-fréquence 27j/10j/21j/autres)
         - insitu   → step4_create_dataset_insitu.py (dossier unique, pas de fréquence)

Usage :
    python pipeline_0_4.py --source hydroweb --db ./database/hydroweb_next_France.db
    python pipeline_0_4.py --source insitu --db ./database/insitu_data.db
    python pipeline_0_4.py --source hydroweb --db ./database/test.db --skip-step0
    python pipeline_0_4.py --source hydroweb --db ./database/test.db --step 2
    python pipeline_0_4.py --source hydroweb --db ./database/test.db --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ⚠️ Adapte ces imports si les noms de fichiers réels diffèrent chez toi
# (vérifié par le passé : plusieurs fichiers ont des noms différents de
# ceux évoqués dans leur propre docstring — utilise `find` pour confirmer).
from Step0_DownloadData.Step0_final import run_step0
from Pipeline_data.Step1_Niveau_deau.step1_importWaterLvL import run_step1 as run_step1_hydroweb
from Pipeline_data.Step1_Niveau_deau.step1_stations_in_situ import run_step1_insitu
from Pipeline_data.Step1_Niveau_deau.config_step1 import HW_DB_PATH, INSITU_DB_PATH
from Pipeline_data.Step2_Bassin_Versant.step2_data_Watershed import run_step2
from Pipeline_data.Step3_ERA5.Step3_ERA5_compute import run_step3
from Pipeline_data.Step3_ERA5.config_step3 import USABLE_DATA_DIR as DEFAULT_ERA5_BASE
from Pipeline_data.Step4_DB_to_NetCDF.step4_db_to_ncdf import run_step4_hydroweb
from Pipeline_data.Step4_DB_to_NetCDF.step4_in_situ_to_ncdf import (
    run_step4_insitu,
    OUTPUT_DIR as INSITU_DEFAULT_OUTPUT_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline_0_4")

HYDROWEB_DEFAULT_OUTPUT_DIR = "./data/IA/Dataset"


def format_duration(seconds: float) -> str:
    """Formate une durée en secondes en HH:MM:SS."""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    elif m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def run_step1_source(source: str, db_path: str, reset: bool) -> dict:
    """
    Dispatch vers le bon import étape 1 selon la source choisie.

    Args:
        source: "hydroweb" ou "insitu"
        db_path: BDD à remplir
        reset: si True, supprime et recrée la BDD

    Returns:
        Dict de résultats (format dépend de la source, voir chaque script)
    """
    if source == "hydroweb":
        return run_step1_hydroweb(db_path=db_path, reset=reset)
    elif source == "insitu":
        return run_step1_insitu(db_path=db_path, reset=reset)
    else:
        raise ValueError(f"Source inconnue : {source!r} (attendu: 'hydroweb' ou 'insitu')")


def run_step4_source(source: str, db_path: str, output_dir: str,
                     date_deb: str, date_fin: str, reset: bool) -> dict:
    """
    Dispatch vers le bon générateur de dataset étape 4 selon la source :
      - hydroweb → step4_db_to_ncdf.py (sous-dossiers 27j/10j/21j/autres,
                   car les stations HydroWeb ont des fréquences satellite
                   variées selon la mission)
      - insitu   → step4_create_dataset_insitu.py (dossier unique, données
                   journalières, pas de notion de fréquence satellite)

    Args:
        source: "hydroweb" ou "insitu"
        db_path, output_dir, date_deb, date_fin, reset: voir chaque script

    Returns:
        Dict de résultats (format dépend de la source)
    """
    if source == "hydroweb":
        return run_step4_hydroweb(
            db_path=db_path, output_dir=output_dir,
            date_deb=date_deb, date_fin=date_fin, reset=reset,
        )
    elif source == "insitu":
        return run_step4_insitu(
            db_path=db_path, output_dir=output_dir,
            date_deb=date_deb, date_fin=date_fin, reset=reset,
        )
    else:
        raise ValueError(f"Source inconnue : {source!r} (attendu: 'hydroweb' ou 'insitu')")


def run_pipeline_0_4(
    source: str,
    db_path: str,
    output_dir: str | None = None,
    era5_base: str = DEFAULT_ERA5_BASE,
    date_deb: str = "2016-01-01",
    date_fin: str = "2025-12-31",
    start_step: int = 1,
    run_step0_first: bool = True,
    reset: bool = False,
) -> dict:
    """
    Enchaîne étapes 0, 1 (source au choix), 2, 3, 4 (source au choix aussi).

    Args:
        source: "hydroweb" ou "insitu" — détermine quel import étape 1 ET
                quel générateur étape 4 utiliser
        db_path: BDD SQLite (créée/remplie par l'étape 1, puis enrichie par 2/3)
        output_dir: dossier de sortie pour les .nc / attributes.csv (étape 4).
                    Si None (défaut), résolu automatiquement selon la source
                    (HYDROWEB_DEFAULT_OUTPUT_DIR ou INSITU_DEFAULT_OUTPUT_DIR)
        era5_base: chemin racine des fichiers Step3_ERA5 (étape 3)
        date_deb, date_fin: bornes pour la génération des séries (étape 4)
        start_step: étape à laquelle commencer (1, 2, 3 ou 4) — l'étape 0
                    est contrôlée séparément par run_step0_first, pas par
                    start_step (elle n'est pas liée à une BDD en particulier)
        run_step0_first: si True (défaut), lance l'étape 0 (récupération
                          des données brutes, 7 sources) avant tout le reste
        reset: si True, recrée la BDD (étape 1) ET régénère les .nc
               existants (étape 4) — couvre les deux, comme convenu

    Returns:
        Dict {"step0": ..., "step1": ..., "step2": ..., "step3": ..., "step4": ...}
    """
    if output_dir is None:
        output_dir = HYDROWEB_DEFAULT_OUTPUT_DIR if source == "hydroweb" else INSITU_DEFAULT_OUTPUT_DIR
        log.info(f"output_dir non fourni, utilisation du défaut pour '{source}' : {output_dir}")

    results = {}
    t_start = time.time()

    # ── ÉTAPE 0 — Données brutes (toutes sources) ──────────────────
    if run_step0_first:
        print("\n" + "█" * 60)
        print("  ÉTAPE 0/4 — Récupération des données brutes")
        print("█" * 60)
        t0 = time.time()
        results["step0"] = run_step0()
        log.info(f"Étape 0 terminée en {format_duration(time.time() - t0)}")
    else:
        log.info("Étape 0 ignorée (--skip-step0)")

    # ── ÉTAPE 1 — Import BDD (source au choix) ──────────────────────
    if start_step <= 1:
        print("\n" + "█" * 60)
        print(f"  ÉTAPE 1/4 — Import BDD (source: {source})")
        print("█" * 60)
        t1 = time.time()
        results["step1"] = run_step1_source(source=source, db_path=db_path, reset=reset)
        log.info(f"Étape 1 terminée en {format_duration(time.time() - t1)}")

    # ── ÉTAPE 2 — Attributs station ──────────────────────────────────
    if start_step <= 2:
        print("\n" + "█" * 60)
        print("  ÉTAPE 2/4 — Attributs station (BV + Strahler + ...)")
        print("█" * 60)
        t2 = time.time()
        results["step2"] = run_step2(db_path=db_path)
        log.info(f"Étape 2 terminée en {format_duration(time.time() - t2)}")

    # ── ÉTAPE 3 — Step3_ERA5 + features ──────────────────────────────
    if start_step <= 3:
        print("\n" + "█" * 60)
        print("  ÉTAPE 3/4 — Step3_ERA5 sur BV + features")
        print("█" * 60)
        t3 = time.time()
        results["step3"] = run_step3(db_path=db_path, era5_base=era5_base)
        log.info(f"Étape 3 terminée en {format_duration(time.time() - t3)}")

    # ── ÉTAPE 4 — Génération dataset (source au choix) ───────────────
    if start_step <= 4:
        print("\n" + "█" * 60)
        print(f"  ÉTAPE 4/4 — Génération dataset (source: {source})")
        print("█" * 60)
        t4 = time.time()
        results["step4"] = run_step4_source(
            source=source, db_path=db_path, output_dir=output_dir,
            date_deb=date_deb, date_fin=date_fin, reset=reset,
        )
        log.info(f"Étape 4 terminée en {format_duration(time.time() - t4)}")

    total_time = time.time() - t_start
    print(f"\n⏱️  Pipeline 0→4 terminée en {format_duration(total_time)}")
    print(f"  Source       : {source}")
    print(f"  BDD          : {db_path}")
    print(f"  Dataset      : {output_dir}")

    return results


# ══════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étapes 0 → 1 → 2 → 3 → 4, source au choix pour l'étape 1 ET l'étape 4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python pipeline_0_4.py --source hydroweb --db ./database/hydroweb_next_France.db
  python pipeline_0_4.py --source insitu --db ./database/insitu_data.db
  python pipeline_0_4.py --source hydroweb --db ./database/test.db --skip-step0
  python pipeline_0_4.py --source hydroweb --db ./database/test.db --step 2
  python pipeline_0_4.py --source hydroweb --db ./database/test.db --reset
        """,
    )
    parser.add_argument("--source", type=str, required=True, choices=["hydroweb", "insitu"],
                        help="Source pour l'étape 1 ET l'étape 4 : hydroweb ou insitu")
    parser.add_argument("--db", type=str, default=None,
                        help="Chemin BDD (défaut selon --source : HW_DB_PATH ou INSITU_DB_PATH de config_step1.py)")
    parser.add_argument("--output", type=str, default=None,
                        help="Dossier de sortie du dataset, étape 4 (défaut selon --source : "
                             f"{HYDROWEB_DEFAULT_OUTPUT_DIR} ou {INSITU_DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--era5", type=str, default=DEFAULT_ERA5_BASE,
                        help=f"Chemin racine Step3_ERA5 (défaut: {DEFAULT_ERA5_BASE})")
    parser.add_argument("--deb", type=str, default="2016-01-01",
                        help="Date de début (étape 4)")
    parser.add_argument("--fin", type=str, default="2025-12-31",
                        help="Date de fin (étape 4)")
    parser.add_argument("--step", type=int, default=1, choices=[1, 2, 3, 4],
                        help="Étape à laquelle commencer, hors étape 0 (défaut: 1)")
    parser.add_argument("--skip-step0", action="store_true",
                        help="Ne pas lancer l'étape 0 (récupération données brutes)")
    parser.add_argument("--reset", action="store_true",
                        help="Recrée la BDD (étape 1) ET régénère les .nc existants (étape 4)")
    args = parser.parse_args()

    db_path = args.db
    if db_path is None:
        db_path = HW_DB_PATH if args.source == "hydroweb" else INSITU_DB_PATH
        log.info(f"--db non fourni, utilisation du défaut pour '{args.source}' : {db_path}")

    run_pipeline_0_4(
        source=args.source,
        db_path=db_path,
        output_dir=args.output,
        era5_base=args.era5,
        date_deb=args.deb,
        date_fin=args.fin,
        start_step=args.step,
        run_step0_first=not args.skip_step0,
        reset=args.reset,
    )