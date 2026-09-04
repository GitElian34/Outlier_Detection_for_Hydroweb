#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_hydrosheds.py — Téléchargement HydroSHEDS (dir + acc, Europe)
═══════════════════════════════════════════════════════════════════════════

Télécharge les rasters flow direction + flow accumulation HydroSHEDS pour
l'Europe (15 arcsec), directement depuis data.hydrosheds.org — pas de
compte requis, licence libre (usage commercial et non-commercial).

Sources (vérifiées) :
    DIR : https://data.hydrosheds.org/file/hydrosheds-v1-dir/hyd_eu_dir_15s.zip
    ACC : https://data.hydrosheds.org/file/hydrosheds-v1-acc/hyd_eu_acc_15s.zip

Usage :
    python step0_fetch_hydrosheds.py
    python step0_fetch_hydrosheds.py --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
import zipfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step2_Bassin_Versant.config_step2 import (
    DIR_PATH as DEST_DIR_PATH,
    ACC_PATH as DEST_ACC_PATH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_hydrosheds")

DIR_URL = "https://data.hydrosheds.org/file/hydrosheds-v1-dir/hyd_eu_dir_15s.zip"
ACC_URL = "https://data.hydrosheds.org/file/hydrosheds-v1-acc/hyd_eu_acc_15s.zip"


def _download_and_extract_tif(url: str, dest_path: Path, label: str, reset: bool) -> bool:
    """
    Télécharge un zip HydroSHEDS et extrait le .tif qu'il contient vers
    dest_path. Retourne True si téléchargé, False si déjà présent (skip).
    """
    dest_path = Path(dest_path)

    if dest_path.exists() and not reset:
        log.info(f"[{label}] Déjà présent → {dest_path}, skip")
        return False

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_zip = dest_path.parent / f"_tmp_{label.lower()}.zip"

    log.info(f"[{label}] Téléchargement depuis {url}...")
    resp = requests.get(url, timeout=300, stream=True)
    resp.raise_for_status()
    with open(tmp_zip, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
    log.info(f"[{label}] Téléchargé ({tmp_zip.stat().st_size / 1e6:.0f} Mo)")

    log.info(f"[{label}] Extraction...")
    with zipfile.ZipFile(tmp_zip) as z:
        tif_names = [n for n in z.namelist() if n.lower().endswith(".tif")]
        if not tif_names:
            tmp_zip.unlink(missing_ok=True)
            raise RuntimeError(f"[{label}] Aucun .tif trouvé dans le zip téléchargé")
        # Extraire directement le .tif vers dest_path
        with z.open(tif_names[0]) as src, open(dest_path, "wb") as dst:
            dst.write(src.read())

    tmp_zip.unlink(missing_ok=True)
    log.info(f"[{label}] ✅ Extrait → {dest_path}")
    return True


def fetch_hydrosheds(
    dest_dir: str = DEST_DIR_PATH,
    dest_acc: str = DEST_ACC_PATH,
    reset: bool = False,
) -> dict:
    """
    Télécharge flow direction + flow accumulation HydroSHEDS Europe (15s).

    Returns:
        {"dir_downloaded": bool, "acc_downloaded": bool}
    """
    log.info("Récupération HydroSHEDS (Europe, 15s)")

    dir_downloaded = _download_and_extract_tif(DIR_URL, dest_dir, "DIR", reset)
    acc_downloaded = _download_and_extract_tif(ACC_URL, dest_acc, "ACC", reset)

    return {"dir_downloaded": dir_downloaded, "acc_downloaded": acc_downloaded}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 — Téléchargement HydroSHEDS (dir + acc, Europe)",
    )
    parser.add_argument("--dest-dir", type=str, default=DEST_DIR_PATH,
                        help=f"Destination flow direction (défaut: {DEST_DIR_PATH})")
    parser.add_argument("--dest-acc", type=str, default=DEST_ACC_PATH,
                        help=f"Destination flow accumulation (défaut: {DEST_ACC_PATH})")
    parser.add_argument("--reset", action="store_true",
                        help="Re-télécharger même si les fichiers existent déjà")
    args = parser.parse_args()

    fetch_hydrosheds(dest_dir=args.dest_dir, dest_acc=args.dest_acc, reset=args.reset)
