#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_roe.py — Copie ROE (interne, comme SRTM/Corine/RiverATLAS)
═══════════════════════════════════════════════════════════════════════════

⚠️ Script à USAGE INTERNE UNIQUEMENT.

Le téléchargement automatique du ROE (dans step2e_dist_barrage.py) échoue
systématiquement avec une erreur DNS côté proxy (ERR_DNS_FAIL sur
atom.geo-ide.e2.rie.gouv.fr). Même solution que pour SRTM/Corine/RiverATLAS :
dépôt manuel UNE FOIS sur le stockage interne, ce script copie ensuite
vers l'emplacement attendu par config_step2.py (ROE_DIR).

Pour déposer le fichier la première fois (depuis un poste qui a accès
au site, hors script) :
    https://www.data.gouv.fr/fr/datasets/obstacles-a-lecoulement-issus-du-roe-en-france-metropole/
    → télécharger le shapefile ROE France Métropole
    → dézipper, déposer le .shp + ses fichiers compagnons
      (.dbf, .shx, .prj, ...) dans SOURCE_DIR (voir plus bas)

Une fois copié ici, step2e_dist_barrage.py le trouve directement dans
ROE_DIR (config_step2.py) et NE TENTE PLUS AUCUN téléchargement — son
cache fichier (`if shp_files: return`) saute cette étape automatiquement.

Usage :
    python step0_fetch_roe.py
    python step0_fetch_roe.py --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step2_Bassin_Versant.config_step2 import ROE_DIR as DEST_ROE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_roe")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — chemin interne (réseau boîte uniquement)
# ═══════════════════════════════════════════════════════════════
SOURCE_DIR = Path("/home/sar_hydro/STUDIES/EtudesEB/Outlier_Detection_DL/data/Step2/Barrage/dataset")


def fetch_roe(
    dest_dir: str = DEST_ROE_DIR,
    source_dir: Path = SOURCE_DIR,
    reset: bool = False,
) -> dict:
    """
    Copie le shapefile ROE (+ compagnons) depuis le stockage interne vers
    ROE_DIR (config_step2.py) — même dossier que step2e_dist_barrage.py
    vérifie avant de tenter un téléchargement.

    Returns:
        {"copied": n}
    """
    source_dir = Path(source_dir)
    dest_dir = Path(dest_dir)

    if not source_dir.exists():
        raise FileNotFoundError(
            f"Source introuvable : {source_dir}\n"
            f"  → Ce script ne fonctionne que depuis le réseau interne. "
            f"Si le fichier n'a jamais été déposé, télécharge-le manuellement "
            f"depuis https://www.data.gouv.fr/fr/datasets/"
            f"obstacles-a-lecoulement-issus-du-roe-en-france-metropole/ "
            f"et dépose le .shp + compagnons dans {source_dir}"
        )

    if reset and dest_dir.exists():
        shutil.rmtree(dest_dir)
        log.info(f"Dossier destination réinitialisé : {dest_dir}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    files = [f for f in source_dir.iterdir() if f.is_file()]
    if not files:
        log.warning(f"Aucun fichier trouvé dans {source_dir}")
        return {"copied": 0}

    copied = 0
    for f in files:
        target = dest_dir / f.name
        if target.exists() and target.stat().st_size == f.stat().st_size and not reset:
            continue
        shutil.copy2(f, target)
        copied += 1

    log.info(f"✅ {copied}/{len(files)} fichier(s) copié(s) → {dest_dir}")
    return {"copied": copied}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 (interne) — Copie ROE depuis le stockage partagé",
    )
    parser.add_argument("--dest", type=str, default=DEST_ROE_DIR,
                        help=f"Destination (défaut: {DEST_ROE_DIR})")
    parser.add_argument("--source", type=str, default=str(SOURCE_DIR),
                        help=f"Dossier source (interne, défaut: {SOURCE_DIR})")
    parser.add_argument("--reset", action="store_true",
                        help="Vider et recopier entièrement")
    args = parser.parse_args()

    fetch_roe(dest_dir=args.dest, source_dir=Path(args.source), reset=args.reset)