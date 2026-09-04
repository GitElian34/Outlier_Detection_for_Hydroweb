#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0_fetch_hydroweb_next_raw.py — Téléchargement HydroWeb Next (API only)
═══════════════════════════════════════════════════════════════════════════

Télécharge les stations HydroWeb Next via py_hydroweb (API CNES/Theia)
pour une bbox donnée, et extrait les fichiers .txt bruts dans un dossier
local. NE PARSE RIEN, N'ÉCRIT RIEN EN BDD — c'est uniquement la
récupération des données brutes (étape 0).

Les .txt produits sont au même format que HydroWeb classique, donc
l'étape 1 correspondante est simplement :
    Pipeline_data/Step1_Niveau_deau/step1_importWaterLvL.py
pointée sur le dossier téléchargé ici (pas besoin d'un parseur dédié).

Prérequis :
    Variable d'environnement HYDROWEB_API_KEY définie (ex: dans un .env,
    voir .env.example à la racine du projet). Aucune valeur par défaut
    n'est codée en dur, pour rester safe à publier sur GitHub.

Usage :
    python step0_fetch_hydroweb_next_raw.py --bbox -5.5 41.0 9.5 51.5 --out ./data/Step1_bis/hydroweb_next_France
    python step0_fetch_hydroweb_next_raw.py --bbox 5.5 47.0 15.5 55.5 --out ./data/Step1_bis/hydroweb_next_Allemagne

Usage depuis un autre script :
    from step0_fetch_hydroweb_next_raw import fetch_hydroweb_next_raw
    dossier = fetch_hydroweb_next_raw(bbox=[-5.5, 41.0, 9.5, 51.5],
                                       output_dir="./data/Step1_bis/hydroweb_next_France")
    # puis, pour l'étape 1 :
    #   run_step1(dossier=dossier, db_path="./database/hydroweb_next_France.db", reset=True)
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path

import py_hydroweb

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from Pipeline_data.Step1_Niveau_deau.config_step1 import (
    HW_BBOX_FRANCE as DEFAULT_BBOX,
    HW_COLLECTION_ID as COLLECTION_ID,
    HW_RAW_OUTPUT_DIR as DEFAULT_OUTPUT_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0_hw_next")

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
# COLLECTION_ID, DEFAULT_BBOX, DEFAULT_OUTPUT_DIR viennent maintenant de
# config_step1.py (source unique, partagée avec step1_importWaterLvL.py
# et step1_stations_in_situ.py).
DOWNLOAD_TMP_DIR  = Path("./data/Step1_bis/_hydroweb_next_tmp")


def _get_api_key() -> str:
    """Clé API HydroWeb Next (en dur, comme convenu pour CDSAPI_KEY)."""
    return "AJerWWCpm4wIaH8CMgPZlf67hNBC0VRMeCeeB1KgkaDHctfvYP"


# ═══════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT VIA PY_HYDROWEB
# ═══════════════════════════════════════════════════════════════
def download_zip(bbox: list[float], tmp_dir: Path,
                 collection_id: str = COLLECTION_ID) -> Path:
    """
    Télécharge le zip HydroWeb Next pour la bbox donnée.
    Retourne le chemin du zip.
    """
    api_key = _get_api_key()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    zip_path = tmp_dir / "hydroweb_next_download.zip"

    log.info(f"Connexion à HydroWeb Next (collection={collection_id})...")
    client = py_hydroweb.Client(api_key=api_key)
    basket = py_hydroweb.DownloadBasket("hw_next_import")
    basket.add_collection(collection_id, bbox=bbox)

    log.info("Soumission et téléchargement...")
    client.submit_and_download_zip(
        basket,
        zip_filename=zip_path.name,
        output_folder=str(tmp_dir),
    )
    log.info(f"✅ Zip téléchargé → {zip_path}")
    return zip_path


def extract_txt_files(zip_path: Path, output_dir: Path) -> list[Path]:
    """
    Extrait les fichiers .txt du zip dans output_dir, puis APLATIT
    l'arborescence (tous les .txt remontés à la racine de output_dir).

    ⚠️ Nécessaire car le zip livré par l'API imbrique les .txt dans des
    sous-dossiers (ex: hydroweb_next/HYDROWEB_RIVERS_OPE/HYDROWEB_RIVERS_OPE/*.txt),
    alors que le parseur de l'étape 1 (parse_hydroweb_directory) ne
    regarde que le premier niveau du dossier (pas de récursion) — sans
    cet aplatissement, l'étape 1 ne trouve aucun fichier malgré leur
    présence réelle (plus bas dans l'arborescence).

    Retourne la liste des fichiers .txt (à la racine de output_dir).
    """
    import shutil as _shutil

    output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as z:
        txt_names = [n for n in z.namelist() if n.endswith(".txt")]
        log.info(f"  {len(txt_names)} fichiers .txt dans le zip")
        z.extractall(output_dir)

    # Aplatir : déplacer tous les .txt trouvés (à n'importe quelle
    # profondeur) directement à la racine de output_dir.
    nested_txt_files = list(output_dir.rglob("*.txt"))
    for f in nested_txt_files:
        if f.parent != output_dir:
            target = output_dir / f.name
            if target.exists():
                target.unlink()
            _shutil.move(str(f), str(target))

    # Nettoyer les sous-dossiers désormais vides laissés par l'extraction
    for sub in sorted(output_dir.iterdir(), reverse=True):
        if sub.is_dir():
            _shutil.rmtree(sub, ignore_errors=True)

    txt_files = list(output_dir.glob("*.txt"))
    log.info(f"  {len(txt_files)} fichiers .txt extraits (aplatis) → {output_dir}")
    return txt_files


# ═══════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ═══════════════════════════════════════════════════════════════
def fetch_hydroweb_next_raw(
    bbox: list[float] = DEFAULT_BBOX,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    collection_id: str = COLLECTION_ID,
    keep_tmp_zip: bool = False,
) -> str:
    """
    Étape 0 HydroWeb Next : télécharge + extrait les .txt bruts.
    Ne parse rien, n'écrit rien en BDD.

    Args:
        bbox: Bounding box [lon_min, lat_min, lon_max, lat_max]
        output_dir: dossier où extraire les .txt (sera lu ensuite par l'étape 1)
        collection_id: collection HydroWeb Next à interroger
        keep_tmp_zip: si True, conserve le zip téléchargé (sinon supprimé après extraction)

    Returns:
        Le chemin du dossier contenant les .txt extraits (= output_dir),
        prêt à être passé à run_step1(dossier=..., db_path=..., ...)
        depuis step1_importWaterLvL.py.
    """
    output_dir_path = Path(output_dir)

    zip_path = download_zip(bbox, DOWNLOAD_TMP_DIR, collection_id)
    extract_txt_files(zip_path, output_dir_path)

    if not keep_tmp_zip:
        shutil.rmtree(DOWNLOAD_TMP_DIR, ignore_errors=True)
        log.info("Zip temporaire supprimé (--keep-tmp-zip pour conserver)")

    log.info(f"Terminé. Pour l'étape 1, utilise :")
    log.info(f"    python Pipeline_data/Step1_Niveau_deau/step1_importWaterLvL.py "
             f"{output_dir_path} --db <ta_bdd.db> --reset")

    return str(output_dir_path)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 HydroWeb Next — Téléchargement brut (API only, pas de parsing/BDD)",
        epilog="""
Exemples :
  python step0_fetch_hydroweb_next_raw.py
  python step0_fetch_hydroweb_next_raw.py --bbox -5.5 41.0 9.5 51.5 --out ./data/Step1_bis/hydroweb_next_France
  python step0_fetch_hydroweb_next_raw.py --bbox 5.5 47.0 15.5 55.5 --out ./data/Step1_bis/hydroweb_next_Allemagne
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--bbox", type=float, nargs=4,
                        default=DEFAULT_BBOX,
                        metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"),
                        help=f"Bounding box (défaut: France {DEFAULT_BBOX})")
    parser.add_argument("--out", type=str, default=DEFAULT_OUTPUT_DIR,
                        help=f"Dossier de sortie des .txt (défaut: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--collection", type=str, default=COLLECTION_ID,
                        help=f"Collection HydroWeb Next (défaut: {COLLECTION_ID})")
    parser.add_argument("--keep-tmp-zip", action="store_true",
                        help="Conserver le zip téléchargé après extraction")
    args = parser.parse_args()

    fetch_hydroweb_next_raw(
        bbox=args.bbox,
        output_dir=args.out,
        collection_id=args.collection,
        keep_tmp_zip=args.keep_tmp_zip,
    )