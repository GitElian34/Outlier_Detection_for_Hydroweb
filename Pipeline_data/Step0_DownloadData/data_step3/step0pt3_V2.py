#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0pt3_v2.py — Récupération ERA5 (étape 0, partie 3, méthode ANNEXE)
═══════════════════════════════════════════════════════════════════════════

⚠️ Script à USAGE INTERNE UNIQUEMENT.

Alternative à step0pt3.py (qui télécharge via l'API CDS — peut prendre
plusieurs JOURS sur 10 ans de données). Si les données ERA5 ont déjà été
téléchargées une fois par quelqu'un de l'équipe et déposées sur le
stockage interne partagé, ce script se contente de les COPIER — bien
plus rapide.

Copie récursivement toute l'arborescence {annee}/{mois}/data_0.nc (+
Snow/{annee}/{mois}/data_0.nc) depuis le stockage interne vers
USABLE_DATA_DIR (config_step3.py) — le dossier lu ensuite par
step3b_era5_meteo.py / step3c_era5_snow.py.

Copie incrémentale : un fichier déjà présent avec la même taille côté
destination est sauté — permet de reprendre une copie interrompue (utile
vu le volume potentiellement important) sans tout recopier depuis zéro.

Les deux méthodes (step0pt3.py et step0pt3_v2.py) produisent le même
résultat final : USABLE_DATA_DIR rempli et prêt pour step3b/step3c.

Usage :
    python step0pt3_v2.py
    python step0pt3_v2.py --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step3_ERA5.config_step3 import USABLE_DATA_DIR as DEST_USABLE_DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0pt3_v2")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — chemin interne (réseau boîte uniquement)
# ═══════════════════════════════════════════════════════════════
SOURCE_USABLE_DIR = Path("/home/sar_hydro/STUDIES/EtudesEB/data/Step2/ERA_5/usable_data_LAND_France/")


def fetch_era5_internal(
    dest_dir: str = DEST_USABLE_DATA_DIR,
    source_dir: Path = SOURCE_USABLE_DIR,
    reset: bool = False,
) -> dict:
    """
    Copie récursivement l'arborescence ERA5 déjà téléchargée depuis le
    stockage interne vers dest_dir (structure {annee}/{mois}/data_0.nc,
    + Snow/{annee}/{mois}/data_0.nc conservée telle quelle).

    Returns:
        {"copied": n, "skipped": n, "total_size_mo": float}
    """
    source_dir = Path(source_dir)
    dest_dir = Path(dest_dir)

    if not source_dir.exists():
        raise FileNotFoundError(
            f"Source introuvable : {source_dir}\n"
            f"  → Ce script ne fonctionne que depuis le réseau interne. "
            f"Si les données n'ont jamais été déposées, il faudra passer "
            f"par step0pt3.py (téléchargement API, plus lent)."
        )

    if reset and dest_dir.exists():
        shutil.rmtree(dest_dir)
        log.info(f"Dossier destination réinitialisé : {dest_dir}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    all_files = [f for f in source_dir.rglob("*") if f.is_file()]
    log.info(f"{len(all_files)} fichiers trouvés dans {source_dir}")

    copied = skipped = 0
    total_size = 0

    for i, src_file in enumerate(all_files):
        rel_path = src_file.relative_to(source_dir)
        dest_file = dest_dir / rel_path

        if dest_file.exists() and dest_file.stat().st_size == src_file.stat().st_size and not reset:
            skipped += 1
            continue

        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        total_size += src_file.stat().st_size
        copied += 1

        if (i + 1) % 100 == 0:
            log.info(f"  [{i+1}/{len(all_files)}] {copied} copiés, {skipped} sautés...")

    log.info(f"Terminé : {copied} fichiers copiés ({total_size / 1e6:.0f} Mo), "
             f"{skipped} déjà présents")

    return {"copied": copied, "skipped": skipped, "total_size_mo": total_size / 1e6}


def run_step0pt3_v2(
    dest_dir: str = DEST_USABLE_DATA_DIR,
    source_dir: Path = SOURCE_USABLE_DIR,
    reset: bool = False,
) -> dict:
    """Copie ERA5 depuis le stockage interne (méthode annexe à step0pt3.py)."""
    print("\n" + "█" * 60)
    print("  ÉTAPE 0 (pt3 V2) — ERA5 (copie interne)")
    print("█" * 60)

    try:
        result = fetch_era5_internal(dest_dir=dest_dir, source_dir=source_dir, reset=reset)
        status = {"ok": True, "result": result, "error": None}
    except Exception as e:
        log.error(f"échec : {e}")
        status = {"ok": False, "result": None, "error": str(e)}

    print("\n" + "═" * 60)
    print("  RAPPORT ÉTAPE 0 (pt3 V2 — ERA5 interne)")
    print("═" * 60)
    icon = "✅" if status["ok"] else "❌"
    print(f"  {icon} ERA5 (copie interne)")
    if not status["ok"]:
        print(f"      → {status['error']}")
    print("═" * 60)

    return status


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 (pt3, méthode annexe) — Copie ERA5 depuis le stockage interne",
    )
    parser.add_argument("--dest", type=str, default=DEST_USABLE_DATA_DIR,
                        help=f"Destination (défaut: {DEST_USABLE_DATA_DIR})")
    parser.add_argument("--source", type=str, default=str(SOURCE_USABLE_DIR),
                        help=f"Dossier source (interne, défaut: {SOURCE_USABLE_DIR})")
    parser.add_argument("--reset", action="store_true",
                        help="Vider et recopier entièrement (sinon : copie incrémentale)")
    args = parser.parse_args()

    run_step0pt3_v2(dest_dir=args.dest, source_dir=Path(args.source), reset=args.reset)