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

⚠️ AJOUT — micro-test (--n-train / --n-val) :
    Si précisés, tronque train_basins.txt/val_basins.txt aux N premières
    stations, et ne masque QUE les .nc de ces stations (au lieu de tout
    le dataset) — pratique pour vérifier rapidement que toute la chaîne
    fonctionne (ex: --n-train 10 --n-val 1) avant un run complet. Sans
    ces paramètres (défaut), comportement inchangé : tout le dataset.

⚠️ AJOUT — génération automatique du split train/val :
    L'étape 4 in-situ ne fait aucun split train/val, elle écrit juste
    une liste unique de stations (stations_insitu.txt). Si
    train_basins.txt/val_basins.txt n'existent pas encore dans
    basins_src_dir (ex: ./AI/LSTM/NeuralHydroDtoD0/), ce script les
    génère maintenant lui-même (split aléatoire, seed fixe) à partir de
    stations_insitu.txt trouvé dans src_dir — plus besoin de lancer un
    script séparé avant le premier masquage. Voir --train-val-ratio /
    --stations-txt pour ajuster.

Usage :
    python create_dataset_masked.py --pct 96
    python create_dataset_masked.py --pct 50 --seed 123
    python create_dataset_masked.py --pct 80 --src-dir ./data/IA/NeuralHydroDtoD0
    python create_dataset_masked.py --pct 96 --n-train 10 --n-val 1   (micro-test)
═══════════════════════════════════════════════════════════════════════════
"""

import argparse
import logging
import random
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
DEFAULT_TRAIN_VAL_RATIO = 0.8   # 80% train / 20% val
DEFAULT_STATIONS_TXT_NAME = "stations_insitu.txt"


def _ensure_basins_exist(
    basins_src_dir: Path,
    stations_txt: Path,
    ratio: float,
    seed: int,
) -> None:
    """
    Génère train_basins.txt/val_basins.txt dans basins_src_dir s'ils
    n'existent pas déjà, en splittant aléatoirement (seed fixe, tirage
    reproductible) la liste de stations trouvée dans stations_txt
    (ex: stations_insitu.txt écrit par l'étape 4 in-situ).

    Ne fait rien si les deux fichiers existent déjà (pas d'écrasement
    d'un split existant).
    """
    train_path = basins_src_dir / "train_basins.txt"
    val_path = basins_src_dir / "val_basins.txt"

    if train_path.exists() and val_path.exists():
        return

    if not stations_txt.exists():
        log.warning(
            f"  ⚠ train_basins.txt/val_basins.txt absents de {basins_src_dir} "
            f"et impossible de les générer : {stations_txt} introuvable. "
            f"Le dataset masqué n'aura pas de basins tant que l'un des deux "
            f"n'existe pas."
        )
        return

    log.info(
        f"  train_basins.txt/val_basins.txt absents de {basins_src_dir} "
        f"→ génération automatique depuis {stations_txt} "
        f"(ratio train={ratio}, seed={seed})"
    )

    stations = [l.strip() for l in stations_txt.read_text().splitlines() if l.strip()]
    if not stations:
        log.warning(f"  ⚠ {stations_txt} est vide — rien à splitter")
        return

    rng = random.Random(seed)
    shuffled = stations[:]
    rng.shuffle(shuffled)

    n_train = round(len(shuffled) * ratio)
    train_ids = sorted(shuffled[:n_train])
    val_ids = sorted(shuffled[n_train:])

    basins_src_dir.mkdir(parents=True, exist_ok=True)
    train_path.write_text("\n".join(train_ids))
    val_path.write_text("\n".join(val_ids))

    log.info(
        f"  → train_basins.txt ({len(train_ids)} stations) / "
        f"val_basins.txt ({len(val_ids)} stations) créés dans {basins_src_dir}"
    )


def _copy_basins_file(src_path: Path, dst_path: Path, n_limit: int | None) -> list[str]:
    """
    Copie un fichier basins (train ou val), tronqué aux n_limit premières
    lignes si précisé. Retourne la liste des station_id effectivement
    écrites (utile pour filtrer les .nc à masquer en mode micro-test).
    """
    lines = [l.strip() for l in src_path.read_text().splitlines() if l.strip()]
    if n_limit is not None:
        lines = lines[:n_limit]
    dst_path.write_text("\n".join(lines))
    return lines


def create_masked_dataset(
    pct: int,
    src_dir: Path = DEFAULT_SRC_DIR,
    dst_root: Path = DEFAULT_DST_ROOT,
    basins_src_dir: Path = DEFAULT_BASINS_SRC_DIR,
    basins_dst_root: Path = DEFAULT_BASINS_DST_ROOT,
    seed: int = DEFAULT_SEED,
    n_train: int | None = None,
    n_val: int | None = None,
    train_val_ratio: float = DEFAULT_TRAIN_VAL_RATIO,
    stations_txt: Path | None = None,
) -> dict:
    """
    Crée un dataset masqué à `pct`% depuis un dataset source complet.

    Args:
        pct: pourcentage de valeurs non-NaN à masquer (0-100). Le nom du
             dossier de sortie est déduit automatiquement : NeuralHydroDtoD{pct}
        src_dir: dataset source (complet, référence)
        dst_root: dossier racine où créer NeuralHydroDtoD{pct}/
        basins_src_dir: dossier source des train/val_basins.txt — généré
             automatiquement s'il n'existe pas encore (voir stations_txt)
        basins_dst_root: dossier racine où créer les basins du dataset masqué
        seed: graine aléatoire (reproductibilité du masquage ET du split
              train/val si celui-ci doit être généré)
        n_train: si précisé, ne garde que les n_train premières stations
                 de train_basins.txt (micro-test). None = toutes.
        n_val: idem pour val_basins.txt. None = toutes.
        train_val_ratio: proportion train du split auto-généré si
             train_basins.txt/val_basins.txt n'existent pas encore
             (défaut: 0.8, soit 80% train / 20% val)
        stations_txt: fichier listant toutes les stations, utilisé pour
             générer le split train/val si besoin (défaut:
             src_dir / "stations_insitu.txt")

    Returns:
        {"dst_dir": Path, "n_ok": int, "n_skip": int}
    """
    if not 0 <= pct <= 100:
        raise ValueError(f"pct doit être entre 0 et 100 (reçu: {pct})")

    nan_rate = pct / 100.0
    micro_test = n_train is not None or n_val is not None

    # ── Noms de dossiers déduits automatiquement du %  ──────────────
    dst_dir = dst_root / f"NeuralHydroDtoD{pct}"
    dst_basins_dir = basins_dst_root / f"NeuralHydroDtoD{pct}"

    src_ts, dst_ts = src_dir / "time_series", dst_dir / "time_series"
    src_att, dst_att = src_dir / "attributes", dst_dir / "attributes"

    dst_ts.mkdir(parents=True, exist_ok=True)
    dst_att.mkdir(parents=True, exist_ok=True)

    if micro_test:
        log.info(f"⚠️  MODE MICRO-TEST : n_train={n_train}, n_val={n_val}")

    # ── Copie attributes (inchangé, fichier unique attributes.csv — reste
    # complet même en micro-test, NeuralHydrology ignore les stations
    # absentes des basins files, pas besoin de le filtrer) ─────────
    log.info("Copie attributes...")
    for f in src_att.glob("*"):
        shutil.copy2(f, dst_att / f.name)
        log.info(f"  {f.name}")

    # ── Génère train/val_basins.txt dans basins_src_dir s'ils n'existent
    # pas encore (split auto depuis stations_txt, ex: stations_insitu.txt
    # écrit par l'étape 4 in-situ) — ne fait rien si déjà présents ──────
    _ensure_basins_exist(
        basins_src_dir=Path(basins_src_dir),
        stations_txt=Path(stations_txt) if stations_txt is not None
                     else Path(src_dir) / DEFAULT_STATIONS_TXT_NAME,
        ratio=train_val_ratio,
        seed=seed,
    )

    # ── Copie basins (tronquée si micro-test) ───────────────────────
    dst_basins_dir.mkdir(parents=True, exist_ok=True)
    selected_stations: set[str] = set()

    train_src = Path(basins_src_dir) / "train_basins.txt"
    val_src = Path(basins_src_dir) / "val_basins.txt"

    if train_src.exists():
        ids = _copy_basins_file(train_src, dst_basins_dir / "train_basins.txt", n_train)
        selected_stations.update(ids)
        log.info(f"  basins : train_basins.txt ({len(ids)} stations"
                 f"{' — tronqué' if n_train is not None else ''})")

    if val_src.exists():
        ids = _copy_basins_file(val_src, dst_basins_dir / "val_basins.txt", n_val)
        selected_stations.update(ids)
        log.info(f"  basins : val_basins.txt ({len(ids)} stations"
                 f"{' — tronqué' if n_val is not None else ''})")

    # Autres fichiers basins éventuels (copiés tels quels, non concernés
    # par le micro-test — seuls train/val sont utilisés par NeuralHydrology
    # pour sélectionner les stations)
    for f in Path(basins_src_dir).glob("*.txt"):
        if f.name in ("train_basins.txt", "val_basins.txt"):
            continue
        shutil.copy2(f, dst_basins_dir / f.name)
        log.info(f"  basins : {f.name}")

    # ── Masquage ──────────────────────────────────────────────────
    nc_files = sorted(src_ts.glob("*.nc"))

    if micro_test:
        # Ne masquer QUE les .nc des stations retenues (gain de temps
        # en plus, pas juste une histoire de train/val) — pas la peine
        # de scanner tout le dataset pour un micro-test.
        nc_files = [f for f in nc_files if f.stem in selected_stations]
        log.info(f"{len(nc_files)} fichiers .nc à traiter (micro-test, "
                 f"masquage {pct}%)")
    else:
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
    if micro_test:
        log.info(f"  Micro-test  : {len(selected_stations)} stations "
                 f"(train={n_train}, val={n_val})")
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
  python create_dataset_masked.py --pct 96 --n-train 10 --n-val 1   (micro-test)
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
    parser.add_argument("--n-train", type=int, default=None,
                        help="Micro-test : limite le nombre de stations train (défaut: toutes)")
    parser.add_argument("--n-val", type=int, default=None,
                        help="Micro-test : limite le nombre de stations val (défaut: toutes)")
    parser.add_argument("--train-val-ratio", type=float, default=DEFAULT_TRAIN_VAL_RATIO,
                        help=f"Proportion train du split auto-généré si train/val_basins.txt "
                             f"n'existent pas encore (défaut: {DEFAULT_TRAIN_VAL_RATIO})")
    parser.add_argument("--stations-txt", type=str, default=None,
                        help=f"Fichier liste de stations pour le split auto (défaut: "
                             f"<src-dir>/{DEFAULT_STATIONS_TXT_NAME})")
    args = parser.parse_args()

    create_masked_dataset(
        pct=args.pct,
        src_dir=Path(args.src_dir),
        dst_root=Path(args.dst_root),
        basins_src_dir=Path(args.basins_src_dir),
        basins_dst_root=Path(args.basins_dst_root),
        seed=args.seed,
        n_train=args.n_train,
        n_val=args.n_val,
        train_val_ratio=args.train_val_ratio,
        stations_txt=Path(args.stations_txt) if args.stations_txt else None,
    )