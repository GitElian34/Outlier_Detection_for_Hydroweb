#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_step2_rasters.py — Copie SRTM + Corine (fichiers lourds, interne)
═══════════════════════════════════════════════════════════════════════════

⚠️ Script à USAGE INTERNE UNIQUEMENT (comme step0_fetch_insitu_raw.py).

SRTM (448 Mo) et Corine (197 Mo) sont trop lourds pour être commités
directement sur GitHub (limite dure à 100 Mo/fichier). Ils sont donc
stockés sur un dossier partagé accessible depuis le réseau interne, et
ce script se contente de les copier vers l'emplacement attendu par
config_step2.py (DEM_PATH, CORINE_PATH).

Alternative (hors réseau interne) : Corine peut être re-téléchargé via
l'API CLMS (land.copernicus.eu/api) avec un compte + une service key —
voir la doc échangée sur ce sujet. SRTM peut être retrouvé/reconstruit
depuis les tuiles HydroSHEDS void-filled DEM (mêmes tuiles à la source),
ou toute autre source SRTM standard couvrant la France. Ces deux
alternatives ne sont pas scriptées ici, seulement documentées.

Usage :
    python step0_fetch_step2_rasters.py
    python step0_fetch_step2_rasters.py --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step2_Bassin_Versant.config_step2 import (
    DEM_PATH as DEST_DEM_PATH,
    CORINE_PATH as DEST_CORINE_PATH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_step2_rasters")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — chemins internes (réseau boîte uniquement)
# ═══════════════════════════════════════════════════════════════
SOURCE_SRTM   = Path("/home/sar_hydro/STUDIES/EtudesEB/data/Step2/SRTM/srtm_france.tif")
SOURCE_CORINE = Path("/home/sar_hydro/STUDIES/EtudesEB/data/Step2/Corine/U2018_CLC2018_V2020_20u1.tif")


def _copy_file(src: Path, dst: Path, label: str, reset: bool) -> bool:
    """
    Copie un fichier unique src → dst.
    Skip si dst existe déjà avec la même taille (sauf --reset).
    Retourne True si copié, False si skip ou erreur.
    """
    if not src.exists():
        log.error(
            f"[{label}] Source introuvable : {src}\n"
            f"  → Ce script ne fonctionne que depuis le réseau interne. "
            f"Si tu es bien sur le bon réseau, vérifie que le fichier n'a "
            f"pas été déplacé."
        )
        return False

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists() and not reset:
        if dst.stat().st_size == src.stat().st_size:
            log.info(f"[{label}] Déjà présent (même taille) → {dst}, skip")
            return False
        log.warning(f"[{label}] {dst} existe avec une taille différente — "
                    f"re-copie (utilise --reset pour forcer sans ce check)")

    size_mo = src.stat().st_size / 1e6
    log.info(f"[{label}] Copie {src} → {dst} ({size_mo:.0f} Mo)...")
    shutil.copy2(src, dst)
    log.info(f"[{label}] ✅ Copié → {dst}")
    return True


def fetch_step2_rasters(
    dest_dem: str = DEST_DEM_PATH,
    dest_corine: str = DEST_CORINE_PATH,
    source_srtm: Path = SOURCE_SRTM,
    source_corine: Path = SOURCE_CORINE,
    reset: bool = False,
) -> dict:
    """
    Copie SRTM + Corine depuis le stockage interne vers les emplacements
    attendus par config_step2.py.

    Returns:
        {"srtm_copied": bool, "corine_copied": bool}
    """
    log.info("Récupération des rasters SRTM + Corine (stockage interne)")

    srtm_copied = _copy_file(Path(source_srtm), Path(dest_dem), "SRTM", reset)
    corine_copied = _copy_file(Path(source_corine), Path(dest_corine), "Corine", reset)

    return {"srtm_copied": srtm_copied, "corine_copied": corine_copied}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 (interne) — Copie SRTM + Corine depuis le stockage partagé",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python step0_fetch_step2_rasters.py
  python step0_fetch_step2_rasters.py --reset
        """,
    )
    parser.add_argument("--dest-dem", type=str, default=DEST_DEM_PATH,
                        help=f"Destination SRTM (défaut: {DEST_DEM_PATH})")
    parser.add_argument("--dest-corine", type=str, default=DEST_CORINE_PATH,
                        help=f"Destination Corine (défaut: {DEST_CORINE_PATH})")
    parser.add_argument("--source-srtm", type=str, default=str(SOURCE_SRTM),
                        help="Chemin source SRTM (interne)")
    parser.add_argument("--source-corine", type=str, default=str(SOURCE_CORINE),
                        help="Chemin source Corine (interne)")
    parser.add_argument("--reset", action="store_true",
                        help="Force la re-copie même si un fichier de même taille existe déjà")
    args = parser.parse_args()

    fetch_step2_rasters(
        dest_dem=args.dest_dem,
        dest_corine=args.dest_corine,
        source_srtm=Path(args.source_srtm),
        source_corine=Path(args.source_corine),
        reset=args.reset,
    )
