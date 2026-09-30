#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════
# setup.sh — Crée le venv et installe tout pour Outlier_Detection_DL
# ═══════════════════════════════════════════════════════════════════════
#
# Usage :
#   chmod +x setup.sh
#   ./setup.sh
#
# À lancer depuis la racine du projet (Outlier_Detection_DL/).
# ═══════════════════════════════════════════════════════════════════════

set -e  # arrête le script à la première erreur

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
NEURALHYDRO_DIR="$PROJECT_ROOT/neuralhydrology"

echo "===== Setup Outlier_Detection_DL ====="
echo "Racine projet : $PROJECT_ROOT"

# ── 0. Vérifier / installer gdaldem (requis par elevation_slope.py, étape 2c) ──
echo "[0/5] Vérification de gdaldem (GDAL)..."
if command -v gdaldem >/dev/null 2>&1; then
    echo "  gdaldem déjà présent : $(command -v gdaldem)"
elif command -v conda >/dev/null 2>&1; then
    echo "  gdaldem absent → installation via conda-forge (pas besoin de root)..."
    conda install -y -c conda-forge gdal || {
        echo "  ⚠️  L'installation via conda a échoué. Installe gdal manuellement :"
        echo "        sudo apt install gdal-bin   (si tu as les droits root)"
        echo "        ou demande à l'administrateur du cluster."
    }
elif command -v module >/dev/null 2>&1 && module avail gdal 2>&1 | grep -qi gdal; then
    echo "  gdaldem absent → module d'environnement 'gdal' détecté, chargement..."
    module load gdal
    echo "  ⚠️  'module load gdal' n'est actif que dans ce shell : pense à le refaire"
    echo "      (ou à l'ajouter à ton .bashrc / ton script SLURM) pour les prochaines sessions."
else
    echo "  ⚠️  gdaldem introuvable et ni conda ni module d'environnement disponibles."
    echo "      Installe-le manuellement avant de lancer l'étape 2c :"
    echo "        - avec les droits root      : sudo apt install gdal-bin"
    echo "        - sans root (conda ailleurs): conda install -c conda-forge gdal"
    echo "        - sinon                     : demande à l'administrateur du cluster"
    echo "      (le reste du setup continue, ce n'est bloquant que pour l'étape 2c)"
fi

# ── 1. Créer le venv ──────────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
    echo "[1/5] venv déjà présent → $VENV_DIR (skip création)"
else
    echo "[1/5] Création du venv → $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "  venv activé : $(which python)"

# ── 2. Mettre à jour pip ──────────────────────────────────────────────
echo "[2/5] Mise à jour de pip..."
pip install --upgrade pip

# ── 3. Installer requirements.txt ─────────────────────────────────────
echo "[3/5] Installation des dépendances (requirements.txt)..."
pip install -r "$PROJECT_ROOT/requirements.txt"

# ── 4. Installer NeuralHydrology en mode éditable (copie locale modifiée) ──
if [ -d "$NEURALHYDRO_DIR" ]; then
    echo "[4/5] Installation de NeuralHydrology (copie locale, mode éditable)..."
    pip install -e "$NEURALHYDRO_DIR"
else
    echo "[4/5] ⚠️  Dossier NeuralHydrology introuvable : $NEURALHYDRO_DIR"
    echo "      Ajuste NEURALHYDRO_DIR dans ce script si ta copie est ailleurs,"
    echo "      ou installe-la manuellement avec :"
    echo "        pip install -e /chemin/vers/ta/copie/neuralhydrology"
fi

echo "[5/5] Vérification finale de gdaldem..."
if command -v gdaldem >/dev/null 2>&1; then
    echo "  ✅ gdaldem OK : $(command -v gdaldem)"
else
    echo "  ⚠️  gdaldem toujours absent — l'étape 2c (elevation_slope.py) échouera"
    echo "      tant qu'il n'est pas installé (voir message [0/5] ci-dessus)."
fi

echo ""
echo "===== Setup terminé ====="
echo "Pour activer le venv dans une nouvelle session :"
echo "  source $VENV_DIR/bin/activate"