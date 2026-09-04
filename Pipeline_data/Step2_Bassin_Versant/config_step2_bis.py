#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
config_Step2_bis.py — Configuration centrale de l'étape 2
═══════════════════════════════════════════════════════════════════════════

SOURCE UNIQUE DE VÉRITÉ pour tous les chemins par défaut de l'étape 2
(sous-modules 2a-2e ET orchestrateur Step2_bis_run_all.py).

Avant ce fichier, chaque sous-module avait SON PROPRE défaut, et
l'orchestrateur en avait un autre → ils divergeaient silencieusement
(ex: HydroSHEDS pointait vers un chemin absolu perso dans Step2_bisa, mais
vers un chemin relatif différent dans l'orchestrateur). Résultat : lancer
un sous-module en standalone donnait un comportement différent que de le
lancer via la pipeline complète.

Pour changer un chemin (nouvelle zone, nouvel emplacement de fichier) :
    → modifie UNIQUEMENT ici. Tous les scripts suivent automatiquement.

Ces valeurs restent de simples DÉFAUTS : n'importe quel appel (CLI ou
Python) peut toujours les override explicitement (--dir, --atlas, etc.),
exactement comme avant.
═══════════════════════════════════════════════════════════════════════════
"""

# ─── 2a — HydroSHEDS (délinéation des bassins versants) ───────────────
DIR_PATH = "./data/Step2_bis/Hydrosheds/hyd_eu_dir_15s.tif"
ACC_PATH = "./data/Step2_bis/Hydrosheds/hyd_eu_acc_15s.tif"

# ─── 2b — RiverATLAS (ordre de Strahler) ───────────────────────────────
# Version pré-découpée sur l'Europe (RiverATLAS_v10_eu.shp) — plus légère
# à manipuler que le fichier global (2.55 Go). Step2_bisb filtre quand même
# par bbox à la LECTURE (gpd.read_file(..., bbox=...)), donc ce fichier
# EU convient pour toute zone incluse dans l'Europe (France, Allemagne...).
RIVER_ATLAS_PATH = "./data/Step2_bis/Strahler/HydroSHED/RiverATLAS_v10_eu.shp"

# ─── 2c — SRTM (élévation / pente) ─────────────────────────────────────
DEM_PATH = "./data/Step2_bis/Elevation/srtm_france.tif"
SLOPE_PATH = "./data/Step2_bis/Elevation/slope_france.tif"

# ─── 2d — Corine Land Cover + SoilGrids ────────────────────────────────
CORINE_PATH = "./data/Step2_bis/Soilgrids/U2018_CLC2018_V2020_20u1.tif"
SOILGRIDS_DIR = "./data/Step2_bis/Soilgrids/SoilGrids/"

# ─── 2e — ROE (barrages) ───────────────────────────────────────────────
ROE_DIR = "./data/Step2_bis/Barrage/dataset/"

# ─── Bbox par défaut (auto-détection) ──────────────────────────────────
# Marge de sécurité (en degrés) appliquée autour des stations quand le
# bbox est auto-détecté depuis leurs coordonnées, pour 2a comme pour 2b.
BBOX_MARGIN_DEG = 0.5

# Bbox manuels de secours (format dict, commun à 2a et 2b — converti en
# tuple pour 2b via bbox_dict_to_tuple si besoin). Non utilisés comme
# défaut implicite : l'auto-détection est le comportement par défaut.
# Utile pour forcer une zone précise sans dépendre des stations en base
# (ex: retrouver l'ancien comportement "toujours France" de Step2_bisb, ou
# clipper une zone plus large que les stations actuellement en BDD).
BBOX_FRANCE  = {"left": -6.0, "right": 10.0, "bottom": 41.0, "top": 52.0}
BBOX_GERMANY = {"left": 5.5, "right": 15.5, "bottom": 47.0, "top": 55.5}


def bbox_dict_to_tuple(bbox: dict) -> tuple[float, float, float, float]:
    """
    Convertit un bbox {"left","bottom","right","top"} (format utilisé par
    2a / run_Step2_bis) vers le tuple (left, bottom, right, top) attendu par
    geopandas.read_file(bbox=...) (utilisé par 2b).
    """
    return (bbox["left"], bbox["bottom"], bbox["right"], bbox["top"])