# Outlier_Detection_DL

Pipeline complet de détection d'anomalies sur des séries de niveau d'eau, combinant :
- **Altimétrie satellite** (HydroWeb Next) et **mesures in-situ** (réseau SCHAPI),
- un enrichissement par **attributs de bassin versant** (BV, Strahler, sol, occupation des sols, distance aux barrages) et **météo ERA5-Land**,
- un modèle **LSTM auto-régressif** (via [NeuralHydrology](https://github.com/neuralhydrology/neuralhydrology), copie locale modifiée) entraîné à différents niveaux de masquage temporel pour simuler la rareté des observations satellite,
- une **évaluation croisée** des prédictions contre les mesures in-situ indépendantes (via connectivité hydrographique SWORD).

---

## Sommaire

1. [Prérequis & installation](#1-prérequis--installation)
2. [Structure du repo](#2-structure-du-repo)
3. [Vue d'ensemble du pipeline](#3-vue-densemble-du-pipeline)
4. [Étape 0 — Récupération des données brutes](#4-étape-0--récupération-des-données-brutes)
5. [Étape 1 — Import en base](#5-étape-1--import-en-base)
6. [Étape 2 — Attributs de bassin versant](#6-étape-2--attributs-de-bassin-versant)
7. [Étape 3 — Météo ERA5 + features](#7-étape-3--météo-era5--features)
8. [Étape 4 — Génération du dataset NeuralHydrology](#8-étape-4--génération-du-dataset-neuralhydrology)
9. [Pipelines complètes (scripts d'orchestration)](#9-pipelines-complètes-scripts-dorchestration)
10. [Masquage temporel (datasets DtoD)](#10-masquage-temporel-datasets-dtod)
11. [Entraînement](#11-entraînement)
12. [Évaluation](#12-évaluation)
13. [Exploration des résultats (Jupyter)](#13-exploration-des-résultats-jupyter)
14. [Lancement sur cluster (SLURM)](#14-lancement-sur-cluster-slurm)
15. [Fichiers de configuration — résumé](#15-fichiers-de-configuration--résumé)
16. [Points connus à vérifier / non finalisés](#16-points-connus-à-vérifier--non-finalisés)

---

## 1. Prérequis & installation

### Prérequis système
```bash
sudo apt install gdal-bin   # fournit gdaldem, utilisé par elevation_slope.py (étape 2c)
```

### Installation complète (venv + dépendances + NeuralHydrology)
```bash
chmod +x setup.sh
./setup.sh
```
`setup.sh` crée le venv (`.venv/`), installe `requirements.txt`, puis installe la copie locale modifiée de NeuralHydrology (`./neuralhydrology/`) en mode éditable (`pip install -e`). Cette dernière étape n'est à faire **qu'une seule fois** — voir le détail dans `requirements.txt`.

Pour réactiver le venv dans une nouvelle session :
```bash
source .venv/bin/activate
```

### Clés API
`HYDROWEB_API_KEY` (py_hydroweb) et `CDSAPI_KEY`/`CDSAPI_URL` (Copernicus CDS, pour ERA5) sont actuellement **codées en dur** dans les scripts concernés (`Step0_DownloadData/data_step1/`, `Step3_ERA5/getData_ERA5_Land.py` et `Get_Data_ERA5_Land_Snow.py`) — décision actée pour la simplicité, à garder en tête si le repo devient public.

### ⚠️ Réseau interne obligatoire pour plusieurs sources de données
Une partie des chemins sources sont **codés en dur vers le stockage interne de la boîte** (chemins `/home/sar_hydro/...`, `/data/sar_hydro/...`) — ces scripts ne fonctionnent **que depuis la ferme** (ou une machine avec accès à ce stockage). Hors de ce réseau, ils échouent avec une erreur claire (`FileNotFoundError`), pas un plantage silencieux.

Sources concernées (toutes dans l'étape 0, sauf SWORD) :
| Source | Script | Chemin interne |
|---|---|---|
| In-situ (CSV + GeoPackage) | `step0_fetch_insitu_raw.py` | `/data/sar_hydro/dad/insitu/FULL_SCHAPI/` |
| RiverATLAS | `step0_fetch_river_atlas.py` | `/home/sar_hydro/.../data/Step2/River_Atlas/` |
| SRTM + Corine | `step0_fetch_step2_rasters.py` | `/home/sar_hydro/.../data/Step2/{SRTM,Corine}/` |
| ROE (barrages) | `step0_fetch_roe.py` | `/home/sar_hydro/.../data/Step2/Barrage/` |
| ERA5 (copie, méthode V2) | `Step0_DownloadData/data_step3/` | `/home/sar_hydro/.../data/Step2/ERA_5/` |
| SWORD (connectivité) | `Sword_connectivity.py` | `/home/sar_hydro/.../data/Step2/Sword/` |

Les autres sources de l'étape 0 (HydroWeb Next, HydroSHEDS, SoilGrids) sont de vrais téléchargements publics — elles fonctionnent depuis n'importe où avec un accès internet normal.

---

## 2. Structure du repo

```
Outlier_Detection_DL/
├── AI_training/
│   ├── Yaml/                          # configs NeuralHydrology (.yml), un par run/modèle
│   ├── Create_dataset_masked.py       # crée UN dataset masqué à X% (NeuralHydroDtoD{X})
│   ├── create_all_dataset_masked.py   # orchestre plusieurs % de masquage d'un coup
│   └── Entrainement.py                # lance start_run() sur un yaml donné
│
├── data/                              # toutes les données (brutes + intermédiaires), non versionné
├── database/                          # BDD SQLite (hydroweb_next_France.db, insitu_data.db, ...)
│
├── Evaluation_Model/
│   ├── Build_metrics_quantile_DtoD.py # tableau comparant Quantile (Q50) à son homologue DtoD, par % de masquage
│   ├── Compare_to_insitu.py           # matching SWORD + métriques modèle vs in-situ (DtoD/Quantile)
│   ├── Eval_Models_DtoD.py            # éval zero-shot des modèles DtoD (10j/27j)
│   ├── Eval_quantile.py               # éval zero-shot des modèles Quantile (Q50 + métriques natives)
│   ├── find_best_epochs.py            # compare plusieurs runs, identifie la meilleure époque
│   ├── plot_outliers_quantile.py      # détection outlier hors [Q5,Q95] + plot bande d'incertitude (voir §16)
│   └── Sword_connectivity.py          # graphe de connectivité fluviale SWORD (copie/récup auto)
│
├── Exploring_results/
│   └── exploration_resultats_insitu.ipynb   # notebook : top stations, plot détaillé, métriques globales
│
├── neuralhydrology/                   # copie LOCALE MODIFIÉE du framework (installée en mode -e)
│
├── Pipeline_data/
│   ├── Database/
│   │   ├── DB_schema.py               # CREATE TABLE (stations, measurements, bv_data, era5_bv_jour, ...)
│   │   └── db_operations.py           # CRUD (insert_station, insert_measurements, ..._batch, ...)
│   │
│   ├── Step0_DownloadData/
│   │   ├── data_step1/                # fetchers HydroWeb Next + in-situ (copie/téléchargement)
│   │   ├── data_step2/                # fetchers HydroSHEDS, RiverATLAS, SoilGrids, SRTM+Corine, ROE
│   │   ├── data_step3/                # fetchers ERA5 (API ou copie interne)
│   │   └── Step0_final.py             # orchestrateur unique, toutes sources, rapport ✅/❌
│   │
│   ├── Step1_Niveau_deau/
│   │   ├── config_step1.py            # chemins/seuils centralisés (HW + in-situ)
│   │   ├── Parser.py                  # parseur .txt HydroWeb (format commun)
│   │   ├── step1_importWaterLvL.py    # import HydroWeb Next → BDD
│   │   ├── step1_stations_in_situ.py  # import in-situ (CSV + GeoPackage) → BDD
│   │   └── step1_imporWaterDahiti.py  # (legacy — voir §16)
│   │
│   ├── Step2_Bassin_Versant/
│   │   ├── config_step2.py            # chemins rasters/shapefiles, bbox, source unique
│   │   ├── config_step2_bis.py        # variante pointant vers data/Step2_bis (tests isolés)
│   │   ├── delineate_bv.py            # 2a — délinéation BV (pysheds + HydroSHEDS)
│   │   ├── strahler.py                # 2b — ordre de Strahler (RiverATLAS)
│   │   ├── elevation_slope.py         # 2c — élévation/pente (SRTM)
│   │   ├── corine_soilgrids.py        # 2d — occupation des sols + texture (Corine/SoilGrids)
│   │   ├── dist_barrage.py            # 2e — distance au barrage le plus proche (ROE)
│   │   ├── step2_data_Watershed.py    # orchestrateur 2a→2e
│   │   └── run_step2_bis.py           # lance l'étape 2 avec config_step2_bis (tests)
│   │
│   ├── Step3_ERA5/
│   │   ├── config_step3.py            # chemins, période, bbox CDS, grille pixels, source unique
│   │   ├── getData_ERA5_Land.py       # téléchargement brut CDS — precip/PET/temp (historique)
│   │   ├── Get_Data_ERA5_Land_Snow.py # téléchargement brut CDS — neige (historique)
│   │   ├── Pixels.py                  # 3a — pixels ERA5 dans chaque BV
│   │   ├── Meteo_Temp_Precip_ETP.py   # 3b — agrégation météo quotidienne sur BV
│   │   ├── Snow.py                    # 3c — agrégation neige quotidienne sur BV (batch)
│   │   ├── Compute_features.py        # 3d — moyennes glissantes + climatologie (optimisé batch+numpy)
│   │   └── Step3_ERA5_compute.py      # orchestrateur 3a→3d
│   │
│   ├── Step4_DB_to_NetCDF/
│   │   ├── step4_db_to_ncdf.py        # BDD HydroWeb Next → .nc (sous-dossiers 27j/10j/21j/autres)
│   │   └── step4_in_situ_to_ncdf.py   # BDD in-situ → .nc (dossier unique, pas de fréquence)
│   │
│   ├── Pipeline_2_3_4.py              # enchaîne 2→3→4 sur une BDD déjà remplie (étape 1 faite)
│   ├── pipeline_finale.py             # ancienne pipeline complète (historique, voir §16)
│   └── PipelineStep0to4.py            # pipeline principale : 0→1→2→3→4, --source hydroweb|insitu
│
├── requirements.txt
├── setup.sh
├── script_PNSSB.slurm                 # job SLURM (entraînement sur cluster)
└── .gitignore
```

---

## 3. Vue d'ensemble du pipeline

```
ÉTAPE 0 (données brutes)
   │  7 sources : HydroWeb Next (API), in-situ (copie interne), HydroSHEDS,
   │  RiverATLAS, SoilGrids, SRTM+Corine, ROE — chacune indépendante
   ▼
ÉTAPE 1 (import BDD)  ──►  database/hydroweb_next_France.db
   │  OU                   database/insitu_data.db
   ▼  (2 sources, 2 BDD séparées, même schéma)
ÉTAPE 2 (attributs station)
   │  BV, Strahler, élévation/pente, occupation des sols, distance barrage
   ▼
ÉTAPE 3 (météo + features)
   │  Pixels ERA5, agrégation météo/neige quotidienne, moyennes glissantes, climatologie
   ▼
ÉTAPE 4 (génération dataset)
   │  BDD → .nc (NeuralHydrology) + attributes.csv + listes de stations
   ▼
MASQUAGE (in-situ uniquement, pour l'instant)
   │  NeuralHydroDtoD0 (référence complète) → NeuralHydroDtoD{X} (X% masqué)
   ▼
ENTRAÎNEMENT (NeuralHydrology, LSTM auto-régressif)
   ▼
ÉVALUATION
      Zero-shot sur HydroWeb Next + comparaison croisée vs in-situ (SWORD)
```

Chaque étape peut être relancée indépendamment (chaque script a son propre CLI avec `--db`, `--reset`, etc.) ou via les pipelines d'orchestration (§9).

---

## 4. Étape 0 — Récupération des données brutes

```bash
python Pipeline_data/Step0_DownloadData/Step0_final.py
```

7 sources indépendantes (si l'une échoue, les autres continuent quand même) :

| Source | Méthode | Dossier destination |
|---|---|---|
| HydroWeb Next | Téléchargement API (py_hydroweb) | `data/Step1_bis/hydroweb_next/` |
| In-situ SCHAPI | Copie stockage interne | `data/Step1_bis/{shp,data}/` |
| HydroSHEDS | Téléchargement direct (data.hydrosheds.org) | `data/Step2/Hydrosheds/` |
| RiverATLAS | Copie stockage interne | `data/Step2/Strahler/HydroSHED/` |
| SoilGrids | Téléchargement WCS (ISRIC) | `data/Step2/Soilgrids/SoilGrids/` |
| SRTM + Corine | Copie stockage interne | `data/Step2/Elevation/`, `data/Step2/Soilgrids/` |
| ROE (barrages) | Copie stockage interne (ou auto-téléchargement si le dossier est vide) | `data/Step2/Barrage/dataset/` |

Chaque source peut être sautée individuellement (`--skip-hydroweb`, `--skip-insitu`, etc. — voir `--help`).

---

## 5. Étape 1 — Import en base

Deux sources, deux scripts, même schéma de BDD.

```bash
# HydroWeb Next
python Pipeline_data/Step1_Niveau_deau/step1_importWaterLvL.py --db ./database/hydroweb_next_France.db --reset

# In-situ
python Pipeline_data/Step1_Niveau_deau/step1_stations_in_situ.py --db ./database/insitu_data.db --reset
```

Points importants :
- **In-situ uniquement métropole** — les stations DOM-TOM (Guadeloupe, etc., présentes dans le GeoPackage SCHAPI) sont filtrées automatiquement (bbox France), car le reste du pipeline (HydroSHEDS, ERA5) ne couvre que la métropole.
- **`REFERENCE LONGITUDE`/`REFERENCE LATITUDE`** sont extraites depuis la géométrie du GeoPackage (avec reprojection auto en WGS84 si besoin) — indispensable pour que l'étape 2 fonctionne (elle filtre sur ces colonnes non NULL).
- Seuil `MIN_MEASUREMENTS` : **5** pour l'in-situ, **aucun** (0) pour HydroWeb Next (`config_step1.py`).

---

## 6. Étape 2 — Attributs de bassin versant

```bash
python Pipeline_data/Step2_Bassin_Versant/step2_data_Watershed.py --db ./database/hydroweb_next_France.db
```

5 sous-étapes (2a→2e), chacune peut aussi être lancée seule. Le **bbox** (pour 2a et 2b) est **auto-détecté** depuis les coordonnées des stations en base par défaut (marge de sécurité 0.5°) — un bbox explicite (`--bbox`) reste possible pour forcer une zone.

```bash
python Pipeline_data/Step2_Bassin_Versant/step2_data_Watershed.py --db ./ta_bdd.db --reset
# → vide bv_data + colonnes dérivées (élévation/Corine/etc.), sans relancer le calcul
```

Pour tester sur un jeu de données isolé sans toucher aux vrais fichiers (`config_step2.py`) :
```bash
python Pipeline_data/Step2_Bassin_Versant/run_step2_bis.py --db ./ta_bdd.db
# utilise config_step2_bis.py → data/Step2_bis/
```

---

## 7. Étape 3 — Météo ERA5 + features

```bash
python Pipeline_data/Step3_ERA5/Step3_ERA5_compute.py --db ./database/hydroweb_next_France.db --era5 <dossier_era5>
```

⚠️ `--era5` (le dossier `usable_data_LAND_*`) est **obligatoire**, sans défaut implicite — pour éviter de joindre silencieusement la mauvaise météo sur une BDD (bug déjà rencontré par le passé).

```bash
python Pipeline_data/Step3_ERA5/Step3_ERA5_compute.py --db ./ta_bdd.db --reset
# → vide era5_transfert / era5_bv_jour / measure_attributes
```

`Compute_features.py` (étape 3d) est optimisé pour les gros volumes (in-situ, mesures journalières sur 10 ans) : insertion en batch (`executemany`) + climatologie vectorisée numpy, au lieu d'un calcul/insert par mesure individuelle.

---

## 8. Étape 4 — Génération du dataset NeuralHydrology

```bash
# HydroWeb Next — sous-dossiers par fréquence satellite (27j/10j/21j/autres)
python Pipeline_data/Step4_DB_to_NetCDF/step4_db_to_ncdf.py --db ./database/hydroweb_next_France.db --output ./data/IA/Dataset

# In-situ — dossier unique (données journalières, pas de notion de fréquence)
python Pipeline_data/Step4_DB_to_NetCDF/step4_in_situ_to_ncdf.py --db ./database/insitu_data.db --output ./data/IA/NeuralHydroDtoD0
```

Sortie, par dossier :
```
<output>/[<subdir>/]
├── time_series/*.nc            # 1 fichier par station
├── attributes/attributes.csv   # attributs statiques (aire_km2, lon, lat, strahler, ...)
└── stations_hwnext_<freq>.txt  (racine de <output>, un par fréquence — HydroWeb Next uniquement)
```

---

## 9. Pipelines complètes (scripts d'orchestration)

### `PipelineStep0to4.py` — pipeline principale
```bash
python Pipeline_data/PipelineStep0to4.py --source hydroweb --db ./database/hydroweb_next_France.db
python Pipeline_data/PipelineStep0to4.py --source insitu --db ./database/insitu_data.db
```
Enchaîne étape 0 (optionnelle, `--skip-step0`) → 1 (source au choix) → 2 → 3 → 4 (dispatch automatique vers le bon script étape 4 selon `--source`). `--step N` pour reprendre à une étape donnée (hors étape 0). `--reset` recrée la BDD (étape 1) **et** régénère les `.nc` (étape 4).

### `Pipeline_2_3_4.py`
Enchaîne seulement 2→3→4, sur une BDD **déjà remplie** par l'étape 1 — utile pour retester sans réimporter :
```bash
python Pipeline_data/Pipeline_2_3_4.py --db ./ta_bdd.db --step 2
```

---

## 10. Masquage temporel (datasets DtoD)

Une fois `NeuralHydroDtoD0` généré (étape 4 in-situ — dataset de référence, 0% masqué), on crée des versions dégradées simulant un passage satellite moins fréquent :

```bash
# Un seul %
python AI_training/Create_dataset_masked.py --pct 96

# Plusieurs % d'un coup
python AI_training/create_all_dataset_masked.py --pcts 50 80 90 96

# Micro-test rapide (ne masque que 11 stations au lieu de tout le dataset)
python AI_training/Create_dataset_masked.py --pct 96 --n-train 10 --n-val 1
```
Crée automatiquement `data/IA/NeuralHydroDtoD{pct}/` + les `{train,val}_basins.txt` correspondants — noms de dossiers déduits du `%`, rien à préciser à la main.

---

## 11. Entraînement

```bash
python AI_training/Entrainement.py
```

⚠️ **Le yaml à utiliser est codé en dur en bas du script** — pas de `--config` en argument CLI. Avant chaque lancement, ouvre `Entrainement.py` et décommente/édite la ligne :
```python
start_run(config_file=Path("./AI_training/Yaml/ConfDtoD96.yaml"))
```
en remplaçant `ConfDtoD96.yaml` par le yaml voulu (une seule ligne `start_run(...)` active à la fois — commente les autres).

**6 yamls déjà prêts** dans `AI_training/Yaml/` :
| Yaml | Masquage | Tête de modèle |
|---|---|---|
| `ConfDtoD80.yaml` | 80% | régression standard |
| `ConfDtoD90.yaml` | 90% | régression standard |
| `ConfDtoD96.yaml` | 96% | régression standard |
| `ConfDtoD80_quantile.yaml` | 80% | quantile regression |
| `ConfDtoD90_quantile.yaml` | 90% | quantile regression |
| `ConfDtoD96_quantile.yaml` | 96% | quantile regression |

⚠️ **Chaque yaml pointe vers un dataset masqué qui doit exister AVANT de lancer l'entraînement** (`data_dir: ./data/IA/NeuralHydroDtoD{X}`) — génère-le d'abord avec le script de masquage (§10) :
```bash
python AI_training/Create_dataset_masked.py --pct 96   # avant de lancer ConfDtoD96.yaml (ou sa variante _quantile)
```
Le % dans le nom du yaml doit correspondre au `--pct` utilisé pour générer le dataset — sinon `data_dir` pointera vers un dossier vide/inexistant.

Charge un yaml de config et lance `neuralhydrology.nh_run.start_run()`. Seed fixée (42) pour la reproductibilité (torch/numpy/random + `cudnn.deterministic`).

Chaque yaml pointe vers un `data_dir` + `train_basin_file`/`validation_basin_file` — vérifier la cohérence avec la sortie des étapes 4/masquage (§8, §10) avant de lancer.

### Modèles déjà entraînés (fournis dans le repo)

Les 6 modèles utilisés pour les résultats du stage sont inclus directement dans `runs/` (poids + config, ~25-30 Mo au total — pas les logs d'entraînement complets) :

| Dossier (`runs/`) | Type | Masquage | Époque retenue |
|---|---|---|---|
| `arlstm_DtoD80_1506_150002` | DtoD | 80% | 12 |
| `arlstm_DtoD90_1606_111709` | DtoD | 90% | 14 |
| `arlstm_DtoD96_1606_164901` | DtoD | 96% | 13 |
| `arlstm_DtoD80_quantile_3006_155128` | Quantile | 80% | 19 |
| `arlstm_DtoD90_quantile_3006_154719` | Quantile | 90% | 16 |
| `arlstm_DtoD96_quantile_3006_155152` | Quantile | 96% | 19 |

Chaque dossier contient `model_epoch{N}.pt` (poids du modèle), `optimizer_state_epoch{N}.pt` (état de l'optimiseur, utile seulement pour reprendre l'entraînement) et `config.yml` (hyperparamètres/`dynamic_inputs` utilisés) — directement réutilisables par les scripts d'évaluation (§12) sans avoir à ré-entraîner.

---

## 12. Évaluation

Tous les résultats (CSV, graphiques, tableaux) rangés dans **`Evaluation_Model/`**. Modèles **Classic** abandonnés (plus utilisés) — seuls **DtoD** et **Quantile** restent d'actualité.

| Script | Rôle |
|---|---|
| `Eval_Models_DtoD.py` | Évaluation zero-shot des modèles DtoD (`predict_last_n>1`), 10j/27j — pas de logique quantile |
| `Eval_quantile.py` | Évaluation zero-shot des modèles Quantile — extrait Q50 + métriques natives (NSE/KGE), 10j/27j |
| `Compare_to_insitu.py` | Sélection in-situ par connectivité SWORD (pas juste distance) + calcul NSE/KGE/RMSE/R² modèle vs in-situ — DtoD et Quantile |
| `Build_metrics_quantile_DtoD.py` | Tableau comparant Quantile (Q50) à son homologue DtoD, par % de masquage |
| `find_best_epochs.py` | Compare plusieurs runs entraînés, identifie la meilleure époque par métrique composite |
| `plot_outliers_quantile.py` | Détection d'outliers (observation hors `[Q5,Q95]`) + plot avec bande d'incertitude — ⚠️ voir §16, dépendance manquante |
| `Sword_connectivity.py` | Graphe de connectivité fluviale SWORD — récupère automatiquement le fichier `.gpkg` depuis le stockage interne au premier appel (`ensure_sword_file()`), rien à faire manuellement |

**Ordre d'exécution typique** : `Eval_Models_DtoD.py` et/ou `Eval_quantile.py` → `Compare_to_insitu.py` → `Build_metrics_quantile_DtoD.py` (tableau) et/ou `plot_outliers_quantile.py` (graphiques par station).

`Sword_connectivity.py` doit être dans le **même dossier** que les scripts qui l'importent (import direct, pas de manipulation de `sys.path`).

---

## 13. Exploration des résultats (Jupyter)

```bash
jupyter notebook Exploring_results/exploration_resultats_insitu.ipynb
```
3 sections : top 10 stations par NSE, plot détaillé (in-situ/modèle/altimétrie) pour une station+année au choix, aperçu global des métriques (boxplots). Lit directement les CSV déjà produits par `Compare_to_insitu.py` — aucun recalcul SWORD dans le notebook.

---

## 14. Lancement sur cluster (SLURM)

```bash
sbatch script_PNSSB.slurm
```
Logs dans `runs_SLURM/sbatch_{error,output}_%x.log` — vérifier que ce dossier existe (`mkdir -p runs_SLURM`) avant le premier lancement.

---

## 15. Fichiers de configuration — résumé

| Fichier | Contenu |
|---|---|
| `Step1_Niveau_deau/config_step1.py` | Bbox HydroWeb Next, chemins bruts/BDD, seuils `MIN_MEASUREMENTS` |
| `Step2_Bassin_Versant/config_step2.py` | Chemins rasters/shapefiles, bbox France/Allemagne, grille |
| `Step2_Bassin_Versant/config_step2_bis.py` | Mêmes clés, chemins sous `data/Step2_bis/` (tests) |
| `Step3_ERA5/config_step3.py` | Chemins ERA5, période, bbox CDS, grille pixels, `year_months()` |

Principe commun : **une seule source de vérité par étape**, tous les sous-modules et scripts de récupération y font référence — évite les divergences de chemins/bbox rencontrées à plusieurs reprises pendant le développement.

---

## 16. Points connus à vérifier / non finalisés

- **`step4_db_to_ncdf.py`** — un renommage complet (`dahiti` → `hydroweb` dans les variables/chemins internes) avait été préparé mais son application effective sur ce fichier n'est pas confirmée. À vérifier avant de s'y fier pour un usage prolongé.
- **`step1_imporWaterDahiti.py`** — présent dans le repo, jamais discuté ; statut (legacy à supprimer, ou utilisé pour une vraie source DAHITI) à clarifier.
- **`pipeline_finale.py`** — ancienne pipeline complète (historique), probablement supplantée par `PipelineStep0to4.py` ; à confirmer avant suppression éventuelle.
- **Masquage pour HydroWeb Next** — `Create_dataset_masked.py` ne gère aujourd'hui que l'in-situ (`NeuralHydroDtoD0`). Un dataset équivalent pour HydroWeb Next (`NeuralHydrologyHWNextDtoD`, attendu par `Eval_Models_DtoD.py` et `Eval_quantile.py`) n'a pas encore été construit dans ce repo — **ces deux scripts ne fonctionneront pas tant que ce dataset n'existe pas**.
- **`plot_outliers_quantile.py` — dépendance manquante** : ce script lit des fichiers `residuals_*_bands.csv` (colonnes `pred_q05/q25/q50/q75/q95`) qu'**aucun script du dossier ne génère actuellement** — `Eval_quantile.py` n'extrait que Q50, pas les 5 quantiles. Sans ce fichier, le script tournera mais ne produira aucun graphique de bande d'incertitude (warning, pas de crash). Un script `eval_quantile_bands.py` (extraction des 5 quantiles) a été rédigé en discussion mais n'a pas été retenu dans la version finale du dossier — à ajouter si les bandes d'incertitude sont nécessaires.
- **Notebooks cartographie** (`Plot_Stations_on_Map.ipynb`, `Carte_verif_sword.ipynb`) — patchés en discussion (chemins + schéma BDD) mais pas encore déposés dans `Exploring_results/`.
- **Clés API en dur** (§1) — à sortir en variables d'environnement si le repo doit un jour être rendu public.
- **`requirements.txt`** — versions non pinnées ; à figer si une reproductibilité stricte est nécessaire.
