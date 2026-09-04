#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
create_all_masked_datasets.py — Génère plusieurs datasets masqués d'un coup
═══════════════════════════════════════════════════════════════════════════

Orchestre create_dataset_masked.py pour une LISTE de pourcentages, plutôt
que de lancer --pct un par un. Chaque % est indépendant (si l'un échoue,
les autres sont quand même tentés).

Usage :
    python create_all_masked_datasets.py
    python create_all_masked_datasets.py --pcts 50 80 90 96
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
from pathlib import Path

from create_dataset_masked import (
    create_masked_dataset,
    DEFAULT_SRC_DIR,
    DEFAULT_DST_ROOT,
    DEFAULT_BASINS_SRC_DIR,
    DEFAULT_BASINS_DST_ROOT,
    DEFAULT_SEED,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("create_all_masked_datasets")

# Pourcentages par défaut si --pcts n'est pas précisé — ajuste à ta guise
DEFAULT_PCTS = [50, 80, 90, 96]


def create_all_masked_datasets(
    pcts: list[int] = DEFAULT_PCTS,
    src_dir: Path = DEFAULT_SRC_DIR,
    dst_root: Path = DEFAULT_DST_ROOT,
    basins_src_dir: Path = DEFAULT_BASINS_SRC_DIR,
    basins_dst_root: Path = DEFAULT_BASINS_DST_ROOT,
    seed: int = DEFAULT_SEED,
) -> dict:
    """
    Génère un dataset masqué pour chaque % de la liste.

    Returns:
        {pct: {"ok": bool, "result": ..., "error": str | None}}
    """
    results = {}

    for pct in pcts:
        print("\n" + "█" * 60)
        print(f"  MASQUAGE {pct}%")
        print("█" * 60)
        try:
            out = create_masked_dataset(
                pct=pct, src_dir=src_dir, dst_root=dst_root,
                basins_src_dir=basins_src_dir, basins_dst_root=basins_dst_root,
                seed=seed,
            )
            results[pct] = {"ok": True, "result": out, "error": None}
        except Exception as e:
            log.error(f"[{pct}%] échec : {e}")
            results[pct] = {"ok": False, "result": None, "error": str(e)}

    # ── Rapport ──────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  RAPPORT — DATASETS MASQUÉS")
    print("═" * 60)
    for pct, res in results.items():
        status = "✅" if res["ok"] else "❌"
        detail = f"{res['result']['n_ok']} .nc" if res["ok"] else res["error"]
        print(f"  {status} {pct:>3d}% — {detail}")
    print("═" * 60)

    return results


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Génère plusieurs datasets NeuralHydroDtoD{pct} masqués d'un coup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python create_all_masked_datasets.py
  python create_all_masked_datasets.py --pcts 50 80 90 96
        """,
    )
    parser.add_argument("--pcts", type=int, nargs="+", default=DEFAULT_PCTS,
                        help=f"Liste des pourcentages à générer (défaut: {DEFAULT_PCTS})")
    parser.add_argument("--src-dir", type=str, default=str(DEFAULT_SRC_DIR))
    parser.add_argument("--dst-root", type=str, default=str(DEFAULT_DST_ROOT))
    parser.add_argument("--basins-src-dir", type=str, default=str(DEFAULT_BASINS_SRC_DIR))
    parser.add_argument("--basins-dst-root", type=str, default=str(DEFAULT_BASINS_DST_ROOT))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    create_all_masked_datasets(
        pcts=args.pcts,
        src_dir=Path(args.src_dir),
        dst_root=Path(args.dst_root),
        basins_src_dir=Path(args.basins_src_dir),
        basins_dst_root=Path(args.basins_dst_root),
        seed=args.seed,
    )