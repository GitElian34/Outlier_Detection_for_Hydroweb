"""
Eval_dtod.py
════════════════════════════════════════════════════════════════════════
Évaluation zero-shot des modèles DtoD (predict_last_n > 1) UNIQUEMENT,
10j et 27j. Version simplifiée de eval_dtod_quantile.py — toute la
logique quantile (extraction Q50, détection d'index, dispatch
model_type) a été retirée : les modèles DtoD produisent une seule
valeur par pas de temps (pas de dimension quantile), donc l'extraction
nowcast se limite au cas 2D (date, time_step).

Pour évaluer les modèles Quantile (Q50 + métriques natives), voir
Eval_quantile.py. Pour les bandes d'incertitude complètes (Q05-Q95),
voir Eval_quantile_bands.py.

⚠️ Branche "dahiti" retirée (plus utilisée) — SOURCE fixé à "hwnext".

Sorties :
  Evaluation_Model/DtoD/residus/residuals_{label}_{SOURCE}_{freq}.csv
  Evaluation_Model/DtoD/residus/results_per_station_{label}_{SOURCE}_{freq}.csv (métriques natives)

Usage :
    python Eval_dtod.py
    (ajuster MODELS/FREQS ci-dessous avant de lancer)
════════════════════════════════════════════════════════════════════════
"""

import pickle
import numpy as np
import pandas as pd
import torch
import netCDF4 as nc
from pathlib import Path
from ruamel.yaml import YAML
from neuralhydrology.utils.config import Config
from neuralhydrology.evaluation.evaluate import start_evaluation

torch.set_num_threads(2)

TARGET_VAR = "water_level"
PERIOD = "validation"
SOURCE = "hwnext"

# Un seul dossier data_dir partagé entre 10j et 27j -- le tri se fait
# par gap médian directement sur les .nc
DATA_DIR = {
    "10j": Path("./data/IA/NeuralHydrologyHWNextDtoD"),
    "27j": Path("./data/IA/NeuralHydrologyHWNextDtoD"),
}

# ═══════════════════════════════════════════════════════════════
# MODÈLES DTOD À ÉVALUER
# ═══════════════════════════════════════════════════════════════
MODELS = [
    {"label": "DtoD80", "model_dir": "arlstm_DtoD80_1506_150002", "epoch": 12},
    {"label": "DtoD90", "model_dir": "arlstm_DtoD90_1606_111709", "epoch": 14},
    {"label": "DtoD96", "model_dir": "arlstm_DtoD96_1606_164901", "epoch": 13},
]

FREQS = ["10j", "27j"]
GAP_RANGES = {"10j": (7, 15), "27j": (22, 32)}

OUT_DIR = Path("./Evaluation_Model/DtoD/residus")


# ═══════════════════════════════════════════════════════════════
# LISTE DE STATIONS PAR FRÉQUENCE (filtrage par gap médian sur les .nc)
# ═══════════════════════════════════════════════════════════════
def build_stations_list(freq: str) -> list:
    nc_dir = DATA_DIR[freq] / "time_series"
    gap_min, gap_max = GAP_RANGES[freq]
    print(f"  Filtre par gap médian sur {nc_dir} : {gap_min}-{gap_max}j")
    stations_eval = []
    for f in sorted(nc_dir.glob("*.nc")):
        ds = nc.Dataset(f)
        dates = pd.to_datetime("2016-01-01") + pd.to_timedelta(ds.variables["date"][:], unit="D")
        wl = ds.variables["water_level"][:]
        ds.close()
        mask = ~np.isnan(wl)
        if mask.sum() < 10:
            continue
        dates_ok = pd.Series(dates[mask])
        gaps = dates_ok.diff().dt.days.dropna().astype(int)
        gap_med = gaps.median()
        if gap_min <= gap_med <= gap_max:
            stations_eval.append(f.stem)
    return stations_eval


# ═══════════════════════════════════════════════════════════════
# EXTRACTION — nowcast [:, -1] uniquement (pas de dimension quantile)
# ═══════════════════════════════════════════════════════════════
def extract_obs_pred(ds):
    obs_var, sim_var = f"{TARGET_VAR}_obs", f"{TARGET_VAR}_sim"
    if obs_var not in ds or sim_var not in ds:
        return None, None, None

    dates = pd.to_datetime(ds.date.values)
    obs_vals = ds[obs_var].values
    sim_vals = ds[sim_var].values

    # Nowcast : dernier time_step (axe 1) si la dimension existe
    obs_arr = obs_vals[:, -1] if obs_vals.ndim >= 2 else obs_vals.flatten()
    pred_arr = sim_vals[:, -1] if sim_vals.ndim >= 2 else sim_vals.flatten()

    if len(obs_arr) != len(dates) or len(pred_arr) != len(dates):
        return None, None, None

    return dates, obs_arr, pred_arr


def compute_score(residual_norm, obs_arr, pred_arr, i):
    if np.isnan(residual_norm) or i == 0:
        return abs(residual_norm) if not np.isnan(residual_norm) else np.nan
    j0_obs, j0_pred = obs_arr[i - 1], pred_arr[i - 1]
    j0_ref = j0_obs if not np.isnan(j0_obs) else j0_pred
    if np.isnan(j0_ref):
        return abs(residual_norm)
    j1_obs, j1_pred = obs_arr[i], pred_arr[i]
    if np.isnan(j1_obs) or np.isnan(j1_pred):
        return abs(residual_norm)
    delta_alti = j1_obs - j0_ref
    delta_model = j1_pred - j0_ref
    eps = 1e-8
    cos = (delta_alti * delta_model) / (
        np.sqrt(delta_alti ** 2 + eps) * np.sqrt(delta_model ** 2 + eps))
    cos_pen = (1 - cos) / 2
    amp = (abs(delta_alti) + abs(delta_model)) / 2
    penalite = cos_pen * np.tanh(amp)
    return abs(residual_norm) * (1 + penalite)


# ═══════════════════════════════════════════════════════════════
# ÉVALUATION D'UN MODÈLE POUR UNE FRÉQUENCE
# ═══════════════════════════════════════════════════════════════
def run_one(model_cfg: dict, freq: str, stations_eval: list, stations_out: Path):
    label = model_cfg["label"]
    run_dir = Path(f"./runs/{model_cfg['model_dir']}")
    epoch = model_cfg["epoch"]
    stations_eval_set = set(stations_eval)
    data_dir = DATA_DIR[freq]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print(f"  ÉVALUATION {label} [{freq}]  (DtoD)  source={SOURCE}")
    print(f"  Modèle : {model_cfg['model_dir']}  epoch {epoch}")
    print(f"  data_dir : {data_dir}")
    print("=" * 60)

    if not run_dir.exists():
        print(f"  ⚠ Run introuvable : {run_dir} -> skip")
        return None
    if not stations_eval:
        print(f"  ⚠ Aucune station pour {SOURCE} [{freq}] -> skip")
        return None
    if not data_dir.exists():
        print(f"  ⚠ data_dir introuvable : {data_dir} -> skip")
        return None

    ryaml = YAML()
    ryaml.preserve_quotes = True
    with open(run_dir / "config.yml") as f:
        cfg_dict = ryaml.load(f)

    cfg_dict["validation_basin_file"] = str(stations_out.resolve())
    cfg_dict["data_dir"] = str(data_dir.resolve())
    cfg_dict["validate_n_random_basins"] = len(stations_eval) + 10000

    config_eval = run_dir / f"config_eval_{SOURCE}_{freq}_{label}.yml"
    with open(config_eval, "w") as f:
        ryaml.dump(cfg_dict, f)

    cfg = Config(config_eval)
    start_evaluation(cfg=cfg, run_dir=run_dir, epoch=epoch, period=PERIOD)
    print("  Évaluation terminée")

    results_p = run_dir / PERIOD / f"model_epoch{epoch:03d}" / f"{PERIOD}_results.p"
    if not results_p.exists():
        print(f"  ⚠ Résultats introuvables : {results_p}")
        return None

    with open(results_p, "rb") as f:
        raw = pickle.load(f)
    print(f"  {len(raw)} stations chargées")

    rows = []
    raw_by_station = {}
    nse_vals, per_station = [], []

    for sid, sub in raw.items():
        if str(sid) not in stations_eval_set:
            continue
        try:
            freq_key = list(sub.keys())[0]
            ds = sub[freq_key]["xr"]

            # Métriques natives NeuralHydrology
            try:
                nse = float(np.squeeze(sub[freq_key]["NSE"]))
                kge = float(np.squeeze(sub[freq_key]["KGE"]))
                if not np.isnan(nse):
                    nse_vals.append(nse)
                    per_station.append({"station": str(sid), "model": label,
                                         "source": SOURCE, "freq": freq, "NSE": nse, "KGE": kge})
            except Exception:
                pass

            dates, obs_arr, pred_arr = extract_obs_pred(ds)
            if dates is None:
                continue

            raw_by_station[str(sid)] = {"obs": obs_arr, "pred": pred_arr}
            for i, (d, o, p) in enumerate(zip(dates, obs_arr, pred_arr)):
                rows.append({
                    "station": str(sid), "date": d,
                    "obs": float(o) if not np.isnan(o) else np.nan,
                    "pred": float(p) if not np.isnan(p) else np.nan,
                    "residual": float(o - p) if not (np.isnan(o) or np.isnan(p)) else np.nan,
                    "_i": i,
                })
        except Exception as e:
            print(f"  ⚠ {sid} : {e}")

    df_sta = pd.DataFrame(per_station)
    sta_csv = OUT_DIR / f"results_per_station_{label}_{SOURCE}_{freq}.csv"
    df_sta.to_csv(sta_csv, index=False)

    df = pd.DataFrame(rows)
    if df.empty:
        print(f"  ⚠ Aucune donnée extraite pour {label} [{freq}]")
        return None
    df["date"] = pd.to_datetime(df["date"])

    def norm_residuals(grp):
        std = np.nanstd(grp["residual"])
        grp["residual_norm"] = grp["residual"] / std if std > 0 else np.nan
        return grp
    df = df.groupby("station", group_keys=False).apply(norm_residuals)

    scores = []
    for _, row in df.iterrows():
        sid, i = row["station"], int(row["_i"])
        scores.append(compute_score(row["residual_norm"],
                                     raw_by_station[sid]["obs"],
                                     raw_by_station[sid]["pred"], i))
    df["score"] = scores
    df["is_outlier"] = df["score"] > 2.5
    df["year"] = df["date"].dt.year
    df = df.drop(columns=["_i"])

    out_csv = OUT_DIR / f"residuals_{label}_{SOURCE}_{freq}.csv"
    df.to_csv(out_csv, index=False)

    df_clean = df.dropna(subset=["obs", "pred"])
    print(f"  ✅ CSV -> {out_csv}")
    print(f"     Lignes : {len(df)} | OK : {len(df_clean)} | Stations : {df['station'].nunique()}")

    if nse_vals:
        nse_arr = np.array(nse_vals)
        print(f"     NSE médian (natif) : {np.median(nse_arr):.3f} "
              f"(n={len(nse_arr)}, > 0.5 : {(nse_arr > 0.5).mean():.0%})")

    return {"label": label, "freq": freq, "n": len(nse_vals),
            "nse_med": float(np.median(nse_vals)) if nse_vals else np.nan}


# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    stations_by_freq = {}
    stations_out_by_freq = {}
    for freq in FREQS:
        print(f"\n{'='*60}\n  LISTE STATIONS [{SOURCE} / {freq}]\n{'='*60}")
        stations_by_freq[freq] = build_stations_list(freq)
        print(f"  Stations retenues : {len(stations_by_freq[freq])}")

        data_dir = DATA_DIR[freq]
        stations_out = data_dir / f"stations_{SOURCE}_{freq}_eval.txt"
        if stations_by_freq[freq]:
            data_dir.mkdir(parents=True, exist_ok=True)
            stations_out.write_text("\n".join(stations_by_freq[freq]))
            print(f"  Fichier stations  : {stations_out}")
        stations_out_by_freq[freq] = stations_out

    summary = []
    for model_cfg in MODELS:
        for freq in FREQS:
            res = run_one(model_cfg, freq, stations_by_freq[freq], stations_out_by_freq[freq])
            if res:
                summary.append(res)

    print("\n" + "=" * 60)
    print("  RÉSUMÉ FINAL")
    print("=" * 60)
    for row in summary:
        print(f"  {row['label']:<15} [{row['freq']}]  n={row['n']:>4}  NSE médian={row['nse_med']:.3f}")

    print("\n✅ Terminé.")