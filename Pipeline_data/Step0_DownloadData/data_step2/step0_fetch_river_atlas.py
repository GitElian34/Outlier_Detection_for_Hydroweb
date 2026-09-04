#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_river_atlas.py — Copie RiverATLAS (interne, comme SRTM/Corine)
═══════════════════════════════════════════════════════════════════════════

⚠️ Script à USAGE INTERNE UNIQUEMENT (comme step0_fetch_step2_rasters.py).

Le téléchargement automatique depuis figshare est bloqué par une
protection anti-bot (403 Forbidden, même avec un User-Agent navigateur
et le bon sous-domaine ndownloader.figshare.com). Plutôt que de lutter
contre cette protection, on applique la même solution que pour SRTM et
Corine : dépôt manuel UNE FOIS sur le stockage interne partagé, ce
script se contente de copier vers l'emplacement attendu.

Fichier attendu : RiverATLAS_v10_eu.shp (version pré-découpée sur
l'Europe, plus légère que le fichier mondial complet — 2.55 Go).

Pour déposer le fichier la première fois (depuis un poste qui a accès
au site, hors script) :
    https://www.hydrosheds.org/hydroatlas
    → "Global RiverATLAS in shapefile format" (2.55 Go, seul format
      disponible en téléchargement direct — il n'y a pas de version EU
      pré-découpée côté HydroSHEDS)
    → dézipper, puis découper sur l'Europe si besoin (ex: en Python,
      gpd.read_file(path, bbox=BBOX_EUROPE).to_file("RiverATLAS_v10_eu.shp")
      ou avec le fichier _eu déjà utilisé par l'équipe s'il existe)
    → déposer RiverATLAS_v10_eu.shp + ses fichiers compagnons
      (.dbf, .shx, .prj, ...) dans SOURCE_DIR (voir plus bas)

Usage :
    python step0_fetch_river_atlas.py
    python step0_fetch_river_atlas.py --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step2_Bassin_Versant.config_step2 import (
    RIVER_ATLAS_PATH as DEST_RIVER_ATLAS_PATH,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_river_atlas")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — chemin interne (réseau boîte uniquement)
# ═══════════════════════════════════════════════════════════════
SOURCE_DIR = Path("/home/sar_hydro/STUDIES/EtudesEB/data/Step2/River_Atlas")
SOURCE_SHP_NAME = "RiverATLAS_v10_eu.shp"


def fetch_river_atlas(
    dest_path: str = DEST_RIVER_ATLAS_PATH,
    source_dir: Path = SOURCE_DIR,
    source_shp_name: str = SOURCE_SHP_NAME,
    reset: bool = False,
) -> bool:
    """
    Copie le shapefile RiverATLAS (+ compagnons .dbf/.shx/.prj/...) depuis
    le stockage interne vers l'emplacement attendu par config_step2.py.

    Returns:
        True si copié, False si déjà présent (skip).
    """
    dest_path = Path(dest_path)
    source_shp = Path(source_dir) / source_shp_name

    if not source_shp.exists():
        raise FileNotFoundError(
            f"Source introuvable : {source_shp}\n"
            f"  → Ce script ne fonctionne que depuis le réseau interne. "
            f"Si le fichier n'a jamais été déposé, télécharge-le manuellement "
            f"depuis https://www.hydrosheds.org/hydroatlas "
            f"('Global RiverATLAS in shapefile format') et dépose "
            f"{source_shp_name} + ses fichiers compagnons dans {source_dir}"
        )

    if dest_path.exists() and not reset:
        log.info(f"Déjà présent → {dest_path}, skip")
        return False

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Copier le .shp + tous les fichiers compagnons (même radical de nom)
    radical = source_shp.stem
    companions = list(Path(source_dir).glob(f"{radical}.*"))

    log.info(f"Copie de {len(companions)} fichier(s) RiverATLAS "
             f"({sum(f.stat().st_size for f in companions) / 1e6:.0f} Mo)...")

    for f in companions:
        target = dest_path.with_suffix(f.suffix)
        shutil.copy2(f, target)

    log.info(f"✅ Copié → {dest_path}")
    return True


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 (interne) — Copie RiverATLAS depuis le stockage partagé",
    )
    parser.add_argument("--dest", type=str, default=DEST_RIVER_ATLAS_PATH,
                        help=f"Destination (défaut: {DEST_RIVER_ATLAS_PATH})")
    parser.add_argument("--source-dir", type=str, default=str(SOURCE_DIR),
                        help=f"Dossier source (interne, défaut: {SOURCE_DIR})")
    parser.add_argument("--source-name", type=str, default=SOURCE_SHP_NAME,
                        help=f"Nom du .shp source (défaut: {SOURCE_SHP_NAME})")
    parser.add_argument("--reset", action="store_true",
                        help="Re-copier même si le fichier existe déjà")
    args = parser.parse_args()

    fetch_river_atlas(
        dest_path=args.dest,
        source_dir=Path(args.source_dir),
        source_shp_name=args.source_name,
        reset=args.reset,
    )