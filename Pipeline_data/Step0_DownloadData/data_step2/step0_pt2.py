#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
step0pt2.py — Récupération de données brutes (étape 0, partie 2)
═══════════════════════════════════════════════════════════════════════════

⚠️ Fichier séparé du step0.py existant (volontairement, pour l'instant) —
à fusionner ensemble plus tard. Reprend le même principe (orchestrateur
qui appelle des fonctions déjà écrites ailleurs, chaque source
indépendante) mais couvre uniquement les 4 nouvelles sources ci-dessous
(HydroWeb Next / in-situ restent dans step0.py, pas dupliquées ici).

Orchestre :
    1. HydroSHEDS     → téléchargement direct         (step0_fetch_hydrosheds.py)
    2. RiverATLAS     → copie depuis stockage interne (step0_fetch_river_atlas.py)
    3. SoilGrids      → téléchargement WCS            (step0_fetch_soilgrids.py)
    4. SRTM + Corine  → copie depuis stockage interne (step0_fetch_step2_rasters.py)
    5. ROE (barrages) → copie depuis stockage interne (step0_fetch_roe.py)

⚠️ Le ROE était auparavant auto-téléchargé dans step2e_dist_barrage.py,
mais ce téléchargement échoue systématiquement (erreur DNS côté proxy
interne) — basculé en copie interne, même modèle que RiverATLAS/SRTM/Corine.

N'écrit rien en BDD — c'est uniquement la récupération des fichiers bruts.
Ne fait que réutiliser les fonctions déjà écrites dans chaque script
dédié, sans dupliquer leur logique.

Usage :
    python step0pt2.py
    python step0pt2.py --skip-step2-rasters   (que ce qui est public)
    python step0pt2.py --base-dir ./data/step2_bis   (tout rediriger pour un test isolé)
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from step0_fetch_hydrosheds import fetch_hydrosheds
from step0_fetch_river_atlas import fetch_river_atlas
from step0_fetch_soilgrids import fetch_soilgrids, DEFAULT_BBOX as SOILGRIDS_DEFAULT_BBOX
from step0_fetch_step2_rasters import (
    fetch_step2_rasters,
    SOURCE_SRTM,
    SOURCE_CORINE,
)
from step0_fetch_ROE import fetch_roe, SOURCE_DIR as ROE_SOURCE_DIR
from Pipeline_data.Step2_Bassin_Versant.config_step2 import (
    DIR_PATH as DEFAULT_DIR_PATH,
    ACC_PATH as DEFAULT_ACC_PATH,
    RIVER_ATLAS_PATH as DEFAULT_RIVER_ATLAS_PATH,
    SOILGRIDS_DIR as DEFAULT_SOILGRIDS_DIR,
    DEM_PATH as DEFAULT_DEM_PATH,
    CORINE_PATH as DEFAULT_CORINE_PATH,
    ROE_DIR as DEFAULT_ROE_DIR,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("step0pt2")

# Préfixe commun à tous les chemins par défaut de config_step2.py — sert
# de référence pour reconstruire les chemins sous --base-dir en gardant
# la même arborescence relative (Hydrosheds/, Strahler/HydroSHED/, ...).
STEP2_DATA_PREFIX = "./data/Step2/"


def _rebase(default_path: str, base_dir: str | None) -> str:
    """
    Si base_dir est fourni, reconstruit le chemin sous base_dir en
    conservant la structure relative après "./data/Step2/".
    Sinon, retourne le chemin par défaut tel quel.

    Exemple :
        _rebase("./data/Step2/Hydrosheds/hyd_eu_dir_15s.tif", "./data/step2_bis")
        → "data/step2_bis/Hydrosheds/hyd_eu_dir_15s.tif"
    """
    if base_dir is None:
        return default_path

    p = str(default_path)
    if p.startswith(STEP2_DATA_PREFIX):
        rel = p[len(STEP2_DATA_PREFIX):]
    else:
        rel = Path(p).name  # fallback si un chemin ne suit pas la convention

    return str(Path(base_dir) / rel)


def _run_source(label: str, enabled: bool, fn, results: dict, **kwargs):
    """Exécute une source si activée, capture le succès/échec dans results."""
    if not enabled:
        log.info(f"{label} ignoré (désactivé)")
        return

    print("\n" + "█" * 60)
    print(f"  ÉTAPE 0 — {label}")
    print("█" * 60)
    try:
        out = fn(**kwargs)
        results[label] = {"ok": True, "result": out, "error": None}
    except Exception as e:
        log.error(f"[{label}] échec : {e}")
        results[label] = {"ok": False, "result": None, "error": str(e)}


def run_step0pt2(
    base_dir: str | None = None,

    run_hydrosheds: bool = True,
    run_river_atlas: bool = True,
    run_soilgrids: bool = True,
    soilgrids_bbox: tuple = SOILGRIDS_DEFAULT_BBOX,

    run_step2_rasters: bool = True,
    step2_rasters_source_srtm: Path = SOURCE_SRTM,
    step2_rasters_source_corine: Path = SOURCE_CORINE,

    run_roe: bool = True,
    roe_source_dir: Path = ROE_SOURCE_DIR,
) -> dict:
    """
    Lance la récupération des données brutes pour ces 4 sources.

    Args:
        base_dir: si fourni, TOUTES les destinations sont rebasées sous
                  ce dossier (en gardant la même arborescence relative
                  que config_step2.py), pratique pour un test isolé sans
                  toucher aux vrais chemins du projet
                  (ex: base_dir="./data/step2_bis").
                  Si None (défaut), utilise les chemins de config_step2.py.

    Chaque source est indépendante : si l'une échoue, les autres sont
    quand même tentées. Le détail des erreurs est dans le résultat
    retourné.

    Returns:
        Dict {label: {"ok": bool, "result": ..., "error": str | None}}
    """
    results = {}

    dest_dir = _rebase(DEFAULT_DIR_PATH, base_dir)
    dest_acc = _rebase(DEFAULT_ACC_PATH, base_dir)
    dest_river_atlas = _rebase(DEFAULT_RIVER_ATLAS_PATH, base_dir)
    dest_soilgrids_dir = _rebase(DEFAULT_SOILGRIDS_DIR, base_dir)
    dest_dem = _rebase(DEFAULT_DEM_PATH, base_dir)
    dest_corine = _rebase(DEFAULT_CORINE_PATH, base_dir)
    dest_roe = _rebase(DEFAULT_ROE_DIR, base_dir)

    if base_dir:
        log.info(f"--base-dir actif : tout sera écrit sous {base_dir}")

    _run_source(
        "HydroSHEDS", run_hydrosheds, fetch_hydrosheds, results,
        dest_dir=dest_dir, dest_acc=dest_acc,
    )

    _run_source(
        "RiverATLAS", run_river_atlas, fetch_river_atlas, results,
        dest_path=dest_river_atlas,
    )

    _run_source(
        "SoilGrids", run_soilgrids, fetch_soilgrids, results,
        output_dir=dest_soilgrids_dir, bbox=soilgrids_bbox,
    )

    _run_source(
        "SRTM + Corine", run_step2_rasters, fetch_step2_rasters, results,
        dest_dem=dest_dem, dest_corine=dest_corine,
        source_srtm=step2_rasters_source_srtm,
        source_corine=step2_rasters_source_corine,
    )

    _run_source(
        "ROE (barrages)", run_roe, fetch_roe, results,
        dest_dir=dest_roe, source_dir=roe_source_dir,
    )

    # ── Rapport ──────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  RAPPORT ÉTAPE 0 (partie 2)")
    print("═" * 60)
    for source, res in results.items():
        status = "✅" if res["ok"] else "❌"
        print(f"  {status} {source}")
        if not res["ok"]:
            print(f"      → {res['error']}")
    print("═" * 60)
    print("  ℹ️  HydroWeb Next / in-situ : voir step0.py")
    print("═" * 60)

    return results


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Étape 0 (partie 2) — HydroSHEDS / RiverATLAS / SoilGrids / SRTM+Corine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python step0pt2.py
  python step0pt2.py --skip-step2-rasters
  python step0pt2.py --base-dir ./data/step2_bis   (test isolé, ne touche pas aux vrais chemins)
        """,
    )

    parser.add_argument("--base-dir", type=str, default=None,
                        help="Rebase TOUTES les destinations sous ce dossier "
                             "(garde la même arborescence relative que config_step2.py). "
                             "Défaut : utilise les chemins de config_step2.py tels quels.")

    parser.add_argument("--skip-hydrosheds", action="store_true")
    parser.add_argument("--skip-river-atlas", action="store_true")
    parser.add_argument("--skip-soilgrids", action="store_true")
    parser.add_argument("--soilgrids-bbox", type=float, nargs=4,
                        default=SOILGRIDS_DEFAULT_BBOX,
                        metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"))

    parser.add_argument("--skip-step2-rasters", action="store_true")
    parser.add_argument("--source-srtm", type=str, default=str(SOURCE_SRTM))
    parser.add_argument("--source-corine", type=str, default=str(SOURCE_CORINE))

    parser.add_argument("--skip-roe", action="store_true")
    parser.add_argument("--roe-source-dir", type=str, default=str(ROE_SOURCE_DIR))

    args = parser.parse_args()

    run_step0pt2(
        base_dir=args.base_dir,

        run_hydrosheds=not args.skip_hydrosheds,
        run_river_atlas=not args.skip_river_atlas,
        run_soilgrids=not args.skip_soilgrids,
        soilgrids_bbox=tuple(args.soilgrids_bbox),

        run_step2_rasters=not args.skip_step2_rasters,
        step2_rasters_source_srtm=Path(args.source_srtm),
        step2_rasters_source_corine=Path(args.source_corine),

        run_roe=not args.skip_roe,
        roe_source_dir=Path(args.roe_source_dir),
    )