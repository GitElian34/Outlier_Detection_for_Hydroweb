#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_insitu_raw.py — Récupération des données brutes in-situ (SCHAPI)
═══════════════════════════════════════════════════════════════════════════

⚠️ Script à USAGE INTERNE UNIQUEMENT.
Les chemins source pointent vers un stockage partagé accessible seulement
depuis le réseau/serveur de la boîte (px-1021 et similaires). Il ne
fonctionnera PAS depuis l'extérieur — c'est voulu : les données in-situ
FULL_SCHAPI ne sont pas publiques.

Copie :
    /data/sar_hydro/dad/insitu/FULL_SCHAPI/shp/   → ./data/Step1_bis/shp/
    /data/sar_hydro/dad/insitu/FULL_SCHAPI/data/  → ./data/Step1_bis/data/

Une fois copiées, ces données sont utilisées par
Pipeline_data/Step1_Niveau_deau/step1_stations_in_situ.py (--csv-dir /
--gpkg pointant vers ce dossier ./data/Step1_bis).

Usage :
    python step0_fetch_insitu_raw.py
    python step0_fetch_insitu_raw.py --dest ./data/Step1_bis --reset
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step1_Niveau_deau.config_step1 import INSITU_RAW_DIR as DEFAULT_DEST_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_insitu_raw")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — chemins internes (réseau boîte uniquement)
# ═══════════════════════════════════════════════════════════════
SOURCE_SHP_DIR = Path("/data/sar_hydro/dad/insitu/FULL_SCHAPI/shp")
SOURCE_CSV_DIR = Path("/data/sar_hydro/dad/insitu/FULL_SCHAPI/data")

# DEFAULT_DEST_DIR vient maintenant de config_step1.py (INSITU_RAW_DIR),
# source unique partagée avec step1_stations_in_situ.py.
DEFAULT_DEST_DIR = Path(DEFAULT_DEST_DIR)


def _copy_dir(src: Path, dst: Path, label: str, reset: bool,
              year_filter: str | None = None) -> int:
    """
    Copie le contenu de src vers dst (fichiers directs, non récursif dans
    les sous-dossiers). Retourne le nombre de fichiers copiés.

    Args:
        year_filter: si fourni (ex: "2025"), ne copie que les fichiers
                     dont le nom contient cette chaîne — utile quand le
                     dossier source contient plusieurs versions datées
                     (ex: station_..._2023_river.gpkg, ..._2025_...).
    """
    if not src.exists():
        raise FileNotFoundError(
            f"Source introuvable : {src}\n"
            f"  → Ce script ne fonctionne que depuis le réseau interne "
            f"(accès au stockage partagé /data/sar_hydro/...). "
            f"Si tu es bien sur le bon réseau, vérifie que le chemin n'a "
            f"pas changé."
        )

    if reset and dst.exists():
        shutil.rmtree(dst)
        log.info(f"[{label}] Dossier destination réinitialisé : {dst}")

    dst.mkdir(parents=True, exist_ok=True)

    files = [f for f in src.iterdir() if f.is_file()]
    if year_filter:
        files = [f for f in files if year_filter in f.name]
        log.info(f"[{label}] Filtre '{year_filter}' → {len(files)} fichier(s) retenu(s)")

    if not files:
        log.warning(f"[{label}] Aucun fichier trouvé dans {src}"
                    + (f" (avec le filtre '{year_filter}')" if year_filter else ""))
        return 0

    copied = 0
    for f in files:
        dest_file = dst / f.name
        if dest_file.exists() and dest_file.stat().st_size == f.stat().st_size and not reset:
            # Déjà copié (même taille) → on saute, pour ne pas re-copier
            # inutilement des gros volumes à chaque run.
            continue
        shutil.copy2(f, dest_file)
        copied += 1

    log.info(f"[{label}] {copied}/{len(files)} fichiers copiés → {dst} "
             f"({len(files) - copied} déjà présents, sautés)")
    return copied


def fetch_insitu_raw(
    dest_dir: Path = DEFAULT_DEST_DIR,
    source_shp_dir: Path = SOURCE_SHP_DIR,
    source_csv_dir: Path = SOURCE_CSV_DIR,
    reset: bool = False,
    year_filter: str | None = "2025",
) -> dict:
    """
    Copie les données brutes in-situ (GeoPackage/shapefile + CSV) depuis
    le stockage partagé vers un dossier local du projet.

    Args:
        dest_dir: dossier local de destination (contiendra shp/ et data/)
        source_shp_dir: dossier source du GeoPackage/shapefile
        source_csv_dir: dossier source des CSV stations
        reset: si True, vide les dossiers destination avant de recopier
        year_filter: filtre appliqué au dossier shp/ (plusieurs versions
                     datées y cohabitent) — ex "2025" pour ne récupérer
                     que le fichier de cette année. None = tout copier.
                     Le dossier CSV n'est pas filtré (pas de date dans
                     les noms de fichiers WSH_<code>.csv).

    Returns:
        {"shp_copied": n, "csv_copied": n, "dest_shp": str, "dest_csv": str}
    """
    dest_dir = Path(dest_dir)
    dest_shp = dest_dir / "shp"
    dest_csv = dest_dir / "data"

    log.info(f"Récupération des données in-situ FULL_SCHAPI → {dest_dir}")

    n_shp = _copy_dir(Path(source_shp_dir), dest_shp, "GeoPackage/shp", reset,
                      year_filter=year_filter)
    n_csv = _copy_dir(Path(source_csv_dir), dest_csv, "CSV stations", reset)

    log.info(f"Terminé : {n_shp} fichier(s) shp/gpkg, {n_csv} CSV copiés")
    log.info(f"  Pour l'étape 1 in-situ, utilise :")
    log.info(f"    --csv-dir {dest_csv}")
    log.info(f"    --gpkg <le .gpkg trouvé dans {dest_shp}>")

    return {
        "shp_copied": n_shp,
        "csv_copied": n_csv,
        "dest_shp": str(dest_shp),
        "dest_csv": str(dest_csv),
    }


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0bis (interne) — Copie les données brutes in-situ SCHAPI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python step0_fetch_insitu_raw.py
  python step0_fetch_insitu_raw.py --dest ./data/Step1_bis --reset
        """,
    )
    parser.add_argument("--dest", type=str, default=str(DEFAULT_DEST_DIR),
                        help=f"Dossier de destination (défaut: {DEFAULT_DEST_DIR})")
    parser.add_argument("--source-shp", type=str, default=str(SOURCE_SHP_DIR),
                        help="Dossier source du GeoPackage/shapefile (interne)")
    parser.add_argument("--source-csv", type=str, default=str(SOURCE_CSV_DIR),
                        help="Dossier source des CSV stations (interne)")
    parser.add_argument("--reset", action="store_true",
                        help="Vider et recopier entièrement (sinon : copie incrémentale)")
    parser.add_argument("--year", type=str, default="2025",
                        help="Filtre sur le dossier shp/ (défaut: 2025). "
                             "Vide ('') = tout copier.")
    args = parser.parse_args()

    fetch_insitu_raw(
        dest_dir=Path(args.dest),
        source_shp_dir=Path(args.source_shp),
        source_csv_dir=Path(args.source_csv),
        reset=args.reset,
        year_filter=args.year or None,
    )