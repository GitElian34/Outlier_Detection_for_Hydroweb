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

# ── 1. Créer le venv ──────────────────────────────────────────────────
if [ -d "$VENV_DIR" ]; then
    echo "[1/4] venv déjà présent → $VENV_DIR (skip création)"
else
    echo "[1/4] Création du venv → $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "  venv activé : $(which python)"

# ── 2. Mettre à jour pip ──────────────────────────────────────────────
echo "[2/4] Mise à jour de pip..."
pip install --upgrade pip

# ── 3. Installer requirements.txt ─────────────────────────────────────
echo "[3/4] Installation des dépendances (requirements.txt)..."
pip install -r "$PROJECT_ROOT/requirements.txt"

# ── 4. Installer NeuralHydrology en mode éditable (copie locale modifiée) ──
if [ -d "$NEURALHYDRO_DIR" ]; then
    echo "[4/4] Installation de NeuralHydrology (copie locale, mode éditable)..."
    pip install -e "$NEURALHYDRO_DIR"
else
    echo "[4/4] ⚠️  Dossier NeuralHydrology introuvable : $NEURALHYDRO_DIR"
    echo "      Ajuste NEURALHYDRO_DIR dans ce script si ta copie est ailleurs,"
    echo "      ou installe-la manuellement avec :"
    echo "        pip install -e /chemin/vers/ta/copie/neuralhydrology"
fi

echo ""
echo "===== Setup terminé ====="
echo "Pour activer le venv dans une nouvelle session :"
echo "  source $VENV_DIR/bin/activate"
echo ""
echo "⚠️ Prérequis SYSTÈME à installer séparément si pas déjà fait :"
echo "  sudo apt install gdal-bin"