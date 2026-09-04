#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
config_step1.py — Configuration centrale de l'étape 1
═══════════════════════════════════════════════════════════════════════════

Même principe que config_step2.py / config_step3.py : source unique de
vérité pour les chemins utilisés à la fois par les scripts de
récupération brute (step0_fetch_hydroweb_next_raw.py,
step0_fetch_insitu_raw.py) ET par les scripts d'import (
step1_importWaterLvL.py, step1_stations_in_situ.py) — pour que les deux
bouts de la chaîne (étape 0 qui dépose les fichiers, étape 1 qui les lit)
pointent toujours vers le même endroit sans avoir à le répéter.

Décisions actées :
    - Pas de seuil MIN_MEASUREMENTS (une station avec ≥1 mesure est
      gardée — comportement actuel de step1_importWaterLvL.py, on ne
      réintroduit pas le filtre à 5 mesures de l'ancien script).
    - Nom du GeoPackage in-situ figé en config (pas de détection
      automatique dans le dossier).
═══════════════════════════════════════════════════════════════════════════
"""

# ─── HydroWeb Next ──────────────────────────────────────────────────────
# Bbox au format py_hydroweb : [lon_min, lat_min, lon_max, lat_max]
# (différent du format CDS utilisé en étape 3 — [Nord, Ouest, Sud, Est] —
# et du format {"left","bottom","right","top"} de l'étape 2. Trois formats
# différents à travers le projet, attention en cas de copier-coller.)
HW_BBOX_FRANCE = [-5.5, 41.0, 9.5, 51.5]
HW_BBOX_GERMANY = [5.5, 47.0, 15.5, 55.5]

HW_COLLECTION_ID = "HYDROWEB_RIVERS_OPE"

# Dossier où step0_fetch_hydroweb_next_raw.py extrait les .txt bruts —
# c'est aussi le dossier que step1_importWaterLvL.py doit lire ensuite
# (argument positionnel "dossier" de son CLI).
HW_RAW_OUTPUT_DIR = "./data/Step1/hydroweb_next"

# BDD par défaut pour cette source (utilisé si tu ne précises pas --db)
HW_DB_PATH = "./database/hydroweb_next_France.db"

# ─── In-situ SCHAPI ─────────────────────────────────────────────────────
# Dossier où step0_fetch_insitu_raw.py copie les fichiers bruts depuis le
# stockage interne — structure : {INSITU_RAW_DIR}/shp/ et {INSITU_RAW_DIR}/data/
INSITU_RAW_DIR = "./data/Step1"
INSITU_CSV_SUBDIR = "data"
INSITU_SHP_SUBDIR = "shp"

# Nom exact du GeoPackage attendu dans {INSITU_RAW_DIR}/{INSITU_SHP_SUBDIR}/
# (figé, pas de détection automatique — décision actée)
INSITU_GPKG_NAME = "station_schapi_alti_ref_2025_river.gpkg"

# Chemins complets dérivés (pratiques à importer directement)
INSITU_CSV_DIR = f"{INSITU_RAW_DIR}/{INSITU_CSV_SUBDIR}"
INSITU_GPKG_PATH = f"{INSITU_RAW_DIR}/{INSITU_SHP_SUBDIR}/{INSITU_GPKG_NAME}"

# BDD par défaut pour cette source
INSITU_DB_PATH = "./database/insitu_data.db"

# Seuil minimal de mesures pour garder une station in-situ (déjà présent
# dans step1_import_insitu.py — centralisé ici, valeur inchangée).
# Différent de HydroWeb (aucun seuil, décision actée ci-dessus).
INSITU_MIN_MEASUREMENTS = 5