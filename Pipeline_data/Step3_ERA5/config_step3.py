#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════
config_step3.py — Configuration centrale de l'étape 3 (ERA5-Land)
═══════════════════════════════════════════════════════════════════════════

Même principe que config_step2.py : source unique de vérité pour les
scripts de téléchargement ERA5 (precip/PET/temp + snow) ET pour
step3b_era5_meteo.py / step3c_era5_snow.py qui lisent ensuite ces
fichiers pour les agréger sur les bassins versants en BDD.

⚠️ USABLE_DATA_DIR doit rester cohérent avec DEFAULT_ERA5_BASE dans
step3b_era5_meteo.py et step3c_era5_snow.py (actuellement
"./data/Step3_ERA5/usable_data_LAND_France") — sinon les fichiers
téléchargés ici ne seront jamais retrouvés par ces scripts.
═══════════════════════════════════════════════════════════════════════════
"""

# ─── CDS API (Copernicus Climate Data Store) ───────────────────────────
# Mis en dur pour l'instant (comme convenu) — à sortir en variable
# d'environnement plus tard, sur le même modèle que HYDROWEB_API_KEY.
CDSAPI_URL = "https://cds.climate.copernicus.eu/api"
CDSAPI_KEY = "68ee5c49-20f5-4bf8-865d-5c0c270376a7"

# ─── Période temporelle ─────────────────────────────────────────────────
START_DATE = "2016-01-01"
END_DATE = "2025-12-31"

# ─── Bbox (format CDS natif : [Nord, Ouest, Sud, Est] — ordre différent
# du format {"left","bottom","right","top"} utilisé en étape 2, attention
# en cas de copier-coller entre les deux configs) ──────────────────────
BBOX_FRANCE = [52, -6, 40, 10]
BBOX_GERMANY = [55.5, 5.5, 47.0, 15.5]

# Marge de sécurité (en degrés) appliquée autour de l'enveloppe des BV
# quand le bbox est auto-détecté (voir get_bbox_from_bv ci-dessous).
BBOX_MARGIN_DEG = 0.5


def get_bbox_from_bv(conn, margin_deg: float = BBOX_MARGIN_DEG) -> list[float]:
    """
    Calcule un bbox englobant TOUS les polygones de bassins versants
    (table bv_data) déjà calculés à l'étape 2, avec une marge de sécurité.

    ⚠️ Contrairement à l'étape 2 (bbox depuis les points des stations),
    l'étape 3 a besoin de couvrir toute la SURFACE des bassins versants
    (pour moyenner la météo dessus), pas juste les points de station —
    un grand bassin versant peut s'étendre loin en amont du point de
    mesure. D'où l'utilisation de bv_data.polygone_wkt plutôt que des
    coordonnées ponctuelles.

    Nécessite que l'étape 2a (délinéation des BV) ait déjà tourné sur
    cette BDD — sinon bv_data est vide et une erreur claire est levée.

    Args:
        conn: connexion SQLite à la BDD pipeline
        margin_deg: marge de sécurité en degrés autour de l'enveloppe

    Returns:
        Bbox au format CDS [Nord, Ouest, Sud, Est]
    """
    from shapely import wkt as shapely_wkt
    from shapely.ops import unary_union

    rows = conn.execute(
        "SELECT polygone_wkt FROM bv_data WHERE polygone_wkt IS NOT NULL"
    ).fetchall()

    if not rows:
        raise ValueError(
            "Impossible de déduire un bbox : aucun polygone dans bv_data. "
            "L'étape 2a (délinéation des bassins versants) doit avoir "
            "tourné sur cette BDD avant l'étape 3."
        )

    polygons = [shapely_wkt.loads(r[0]) for r in rows]
    union = unary_union(polygons)
    lon_min, lat_min, lon_max, lat_max = union.bounds

    bbox = [
        lat_max + margin_deg,  # Nord
        lon_min - margin_deg,  # Ouest
        lat_min - margin_deg,  # Sud
        lon_max + margin_deg,  # Est
    ]
    return bbox

# ─── Chemins ────────────────────────────────────────────────────────────
RAW_DATA_DIR = "./data/Step3T/raw_data/"
USABLE_DATA_DIR = "./data/Step3T/usable_data_LAND_France/"

# ─── Nettoyage ──────────────────────────────────────────────────────────
KEEP_RAW_PIECES = False  # supprimer les fichiers intermédiaires après fusion

# ─── Grille Step3_ERA5-Land (étape 3a — pixels par BV) ─────────────────
# Dérivée de BBOX_FRANCE plutôt que redéfinie séparément (l'ancien
# step3a_era5_pixels.py avait sa propre étendue France codée en dur,
# légèrement différente : sud=41.0 au lieu de 40 ici — à vérifier de ton
# côté si ce degré de différence est voulu ou juste un résidu ancien).
GRID_RES = 0.1
GRID_LON_MIN = BBOX_FRANCE[1]  # Ouest
GRID_LON_MAX = BBOX_FRANCE[3]  # Est
GRID_LAT_MIN = BBOX_FRANCE[2]  # Sud
GRID_LAT_MAX = BBOX_FRANCE[0]  # Nord


def year_months(start_date: str = START_DATE, end_date: str = END_DATE) -> list[tuple[str, str]]:
    """
    Liste des (année, mois) couvrant [start_date, end_date] (granularité
    mensuelle) — source unique utilisée à la fois par les scripts de
    téléchargement (step0_fetch_era5_*.py) et par step3b/step3c pour
    savoir quels mois de données chercher/lire.
    """
    import pandas as pd
    months = pd.period_range(start=start_date, end=end_date, freq="M")
    return [(str(p.year), f"{p.month:02d}") for p in months]