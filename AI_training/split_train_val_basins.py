#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
split_train_val_basins.py — Split train/val des stations in-situ (chaînon
manquant entre l'étape 4 in-situ et le masquage)
═══════════════════════════════════════════════════════════════════════════

L'étape 4 in-situ (step4_create_dataset_insitu.py) écrit toutes les stations
dans un seul fichier `stations_insitu.txt` (./data/IA/NeuralHydroDtoD0/) —
elle ne fait PAS de split train/val. Or create_dataset_masked.py a besoin
de trouver train_basins.txt / val_basins.txt déjà présents dans
./AI/LSTM/NeuralHydroDtoD0/ (DEFAULT_BASINS_SRC_DIR) pour les copier vers
chaque dataset masqué (NeuralHydroDtoD50/80/90/96/...).

Ce script fait ce split une fois pour toutes, avec une graine fixe pour
la reproductibilité.

Usage :
    python split_train_val_basins.py
    python split_train_val_basins.py --ratio 0.8 --seed 42
    python split_train_val_basins.py --src ./data/IA/NeuralHydroDtoD0/stations_insitu.txt \
                                      --dst-dir ./AI/LSTM/NeuralHydroDtoD0
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import random
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("split_train_val_basins")

DEFAULT_SRC = Path("./data/IA/NeuralHydroDtoD0/stations_insitu.txt")
DEFAULT_DST_DIR = Path("./AI/LSTM/NeuralHydroDtoD0")
DEFAULT_RATIO = 0.8   # 80% train / 20% val
DEFAULT_SEED = 42


def split_train_val(
    src: Path = DEFAULT_SRC,
    dst_dir: Path = DEFAULT_DST_DIR,
    ratio: float = DEFAULT_RATIO,
    seed: int = DEFAULT_SEED,
) -> dict:
    """
    Lit la liste de stations (une par ligne), la mélange (seed fixe) et
    écrit train_basins.txt / val_basins.txt dans dst_dir.

    Returns:
        {"n_train": int, "n_val": int}
    """
    src = Path(src)
    dst_dir = Path(dst_dir)

    if not src.exists():
        raise FileNotFoundError(
            f"Source introuvable : {src}\n"
            f"  → Relance l'étape 4 in-situ si ce fichier n'existe pas encore."
        )

    stations = [l.strip() for l in src.read_text().splitlines() if l.strip()]
    n_total = len(stations)
    if n_total == 0:
        raise ValueError(f"{src} est vide — rien à splitter")

    rng = random.Random(seed)
    stations_shuffled = stations[:]
    rng.shuffle(stations_shuffled)

    n_train = round(n_total * ratio)
    train_ids = sorted(stations_shuffled[:n_train])
    val_ids = sorted(stations_shuffled[n_train:])

    dst_dir.mkdir(parents=True, exist_ok=True)
    train_path = dst_dir / "train_basins.txt"
    val_path = dst_dir / "val_basins.txt"

    train_path.write_text("\n".join(train_ids))
    val_path.write_text("\n".join(val_ids))

    log.info(f"Source : {src} ({n_total} stations)")
    log.info(f"Split  : ratio={ratio} seed={seed}")
    log.info(f"  train_basins.txt → {train_path} ({len(train_ids)} stations)")
    log.info(f"  val_basins.txt   → {val_path} ({len(val_ids)} stations)")

    return {"n_train": len(train_ids), "n_val": len(val_ids)}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Split train/val des stations in-situ → train_basins.txt / val_basins.txt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python split_train_val_basins.py
  python split_train_val_basins.py --ratio 0.8 --seed 42
        """,
    )
    parser.add_argument("--src", type=str, default=str(DEFAULT_SRC),
                        help=f"Fichier source (défaut: {DEFAULT_SRC})")
    parser.add_argument("--dst-dir", type=str, default=str(DEFAULT_DST_DIR),
                        help=f"Dossier de sortie (défaut: {DEFAULT_DST_DIR})")
    parser.add_argument("--ratio", type=float, default=DEFAULT_RATIO,
                        help=f"Proportion train (défaut: {DEFAULT_RATIO})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Graine aléatoire (défaut: {DEFAULT_SEED})")
    args = parser.parse_args()

    split_train_val(
        src=Path(args.src),
        dst_dir=Path(args.dst_dir),
        ratio=args.ratio,
        seed=args.seed,
    )