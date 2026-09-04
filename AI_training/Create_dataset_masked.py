#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
create_dataset_masked.py — Crée un dataset NeuralHydroDtoD{pct} masqué
═══════════════════════════════════════════════════════════════════════════

Version générique de create_dataset_DtoD96.py : copie les .nc du dataset
source (référence 100% complète, ex: NeuralHydroDtoD0) et masque un
pourcentage CONFIGURABLE des valeurs non-NaN du water_level.

Le nom du dossier de sortie est déduit automatiquement du pourcentage
choisi (NeuralHydroDtoD{pct}), donc pas besoin de le préciser à la main.

Ne modifie JAMAIS le dataset source.

Usage :
    python create_dataset_masked.py --pct 96
    python create_dataset_masked.py --pct 50 --seed 123
    python create_dataset_masked.py --pct 80 --src-dir ./data/IA/NeuralHydroDtoD0
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import shutil
from pathlib import Path

import numpy as np
import xarray as xr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("create_dataset_masked")

# ═══════════════════════════════════════════════════════════════
# PARAMÈTRES PAR DÉFAUT
# ═══════════════════════════════════════════════════════════════
DEFAULT_SRC_DIR = Path("./data/IA/NeuralHydroDtoD0")
DEFAULT_DST_ROOT = Path("./data/IA")
DEFAULT_BASINS_SRC_DIR = Path("./AI/LSTM/NeuralHydroDtoD0")
DEFAULT_BASINS_DST_ROOT = Path("./AI/LSTM")
DEFAULT_SEED = 42


def create_masked_dataset(
    pct: int,
    src_dir: Path = DEFAULT_SRC_DIR,
    dst_root: Path = DEFAULT_DST_ROOT,
    basins_src_dir: Path = DEFAULT_BASINS_SRC_DIR,
    basins_dst_root: Path = DEFAULT_BASINS_DST_ROOT,
    seed: int = DEFAULT_SEED,
) -> dict:
    """
    Crée un dataset masqué à `pct`% depuis un dataset source complet.

    Args:
        pct: pourcentage de valeurs non-NaN à masquer (0-100). Le nom du
             dossier de sortie est déduit automatiquement : NeuralHydroDtoD{pct}
        src_dir: dataset source (complet, référence)
        dst_root: dossier racine où créer NeuralHydroDtoD{pct}/
        basins_src_dir: dossier source des train/val_basins.txt
        basins_dst_root: dossier racine où créer les basins du dataset masqué
        seed: graine aléatoire (reproductibilité du masquage)

    Returns:
        {"dst_dir": Path, "n_ok": int, "n_skip": int}
    """
    if not 0 <= pct <= 100:
        raise ValueError(f"pct doit être entre 0 et 100 (reçu: {pct})")

    nan_rate = pct / 100.0

    # ── Noms de dossiers déduits automatiquement du %  ──────────────
    dst_dir = dst_root / f"NeuralHydroDtoD{pct}"
    dst_basins_dir = basins_dst_root / f"NeuralHydroDtoD{pct}"

    src_ts, dst_ts = src_dir / "time_series", dst_dir / "time_series"
    src_att, dst_att = src_dir / "attributes", dst_dir / "attributes"

    dst_ts.mkdir(parents=True, exist_ok=True)
    dst_att.mkdir(parents=True, exist_ok=True)

    # ── Copie attributes + basins (identiques à la source) ─────────
    log.info("Copie attributes...")
    for f in src_att.glob("*"):
        shutil.copy2(f, dst_att / f.name)
        log.info(f"  {f.name}")

    dst_basins_dir.mkdir(parents=True, exist_ok=True)
    for f in Path(basins_src_dir).glob("*.txt"):
        shutil.copy2(f, dst_basins_dir / f.name)
        log.info(f"  basins : {f.name}")

    # ── Masquage ──────────────────────────────────────────────────
    nc_files = sorted(src_ts.glob("*.nc"))
    log.info(f"{len(nc_files)} fichiers .nc à traiter (masquage {pct}%)")

    rng = np.random.default_rng(seed)
    n_ok = n_skip = 0

    for i, src_path in enumerate(nc_files):
        dst_path = dst_ts / src_path.name

        if dst_path.exists():
            n_ok += 1
            continue

        try:
            ds = xr.open_dataset(src_path, engine="scipy")
            ds_new = ds.copy(deep=True)

            if "water_level" in ds_new:
                wl = ds_new["water_level"].values.copy().astype(float)
                valid_idx = np.where(~np.isnan(wl))[0]
                n_mask = int(len(valid_idx) * nan_rate)

                if n_mask > 0:
                    mask_idx = rng.choice(valid_idx, size=n_mask, replace=False)
                    wl[mask_idx] = np.nan
                    ds_new["water_level"].values[:] = wl

            ds_new.attrs["nan_rate"] = nan_rate
            ds.close()

            ds_new.to_netcdf(dst_path, engine="scipy", format="NETCDF3_CLASSIC")
            ds_new.close()
            n_ok += 1

        except Exception as e:
            log.warning(f"  ⚠ {src_path.name} : {e}")
            n_skip += 1

        if (i + 1) % 200 == 0:
            log.info(f"  {i+1}/{len(nc_files)} traités...")

    log.info("=" * 55)
    log.info(f"  Dataset     : {dst_dir}")
    log.info(f"  Masquage    : {pct}% des valeurs non-NaN")
    log.info(f"  .nc générés : {n_ok}")
    log.info(f"  .nc skippés : {n_skip}")
    log.info("=" * 55)
    log.info(f"""
Config NeuralHydrology à créer : config_DtoD{pct}.yml
  experiment_name: arlstm_DtoD{pct}
  data_dir: {dst_dir}
  train_basin_file: {dst_basins_dir / 'train_basins.txt'}
  validation_basin_file: {dst_basins_dir / 'val_basins.txt'}
  (reste identique aux autres configs DtoD)
""")

    return {"dst_dir": dst_dir, "n_ok": n_ok, "n_skip": n_skip}


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crée un dataset NeuralHydroDtoD{pct} masqué depuis un dataset source complet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python create_dataset_masked.py --pct 96
  python create_dataset_masked.py --pct 50 --seed 123
  python create_dataset_masked.py --pct 80 --src-dir ./data/IA/NeuralHydroDtoD0
        """,
    )
    parser.add_argument("--pct", type=int, required=True,
                        help="Pourcentage de valeurs à masquer (0-100)")
    parser.add_argument("--src-dir", type=str, default=str(DEFAULT_SRC_DIR),
                        help=f"Dataset source complet (défaut: {DEFAULT_SRC_DIR})")
    parser.add_argument("--dst-root", type=str, default=str(DEFAULT_DST_ROOT),
                        help=f"Dossier racine de sortie (défaut: {DEFAULT_DST_ROOT})")
    parser.add_argument("--basins-src-dir", type=str, default=str(DEFAULT_BASINS_SRC_DIR),
                        help=f"Dossier source des basins (défaut: {DEFAULT_BASINS_SRC_DIR})")
    parser.add_argument("--basins-dst-root", type=str, default=str(DEFAULT_BASINS_DST_ROOT),
                        help=f"Dossier racine de sortie des basins (défaut: {DEFAULT_BASINS_DST_ROOT})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                        help=f"Graine aléatoire (défaut: {DEFAULT_SEED})")
    args = parser.parse_args()

    create_masked_dataset(
        pct=args.pct,
        src_dir=Path(args.src_dir),
        dst_root=Path(args.dst_root),
        basins_src_dir=Path(args.basins_src_dir),
        basins_dst_root=Path(args.basins_dst_root),
        seed=args.seed,
    )