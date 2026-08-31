#!/usr/bin/env bash

# =============================================================================
# Full Pipeline Execution Script for CP3 Scenario 2 Isolated Protocols + TGEN
#
# Steps:
#   1. Regenerate Maude scenario models & QuaTEx queries from YAML configs
#   2. Regenerate parallel baselines (without HCS traffic) & extract CUSUM statistics
#   3. Run SMC simulation experiments across all isolated protocols
#   4. Parse JSON results, generate CSV summary table, and produce plot dashboards
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

SCENARIO_DIR="${REPO_ROOT}/use-cases/challenge-problem-3/cp3_scenarios/scenario2_isolated_plus_tgen"
RESULTS_DIR="${SCENARIO_DIR}/results"

echo "========================================================================"
echo " Starting Full End-to-End Pipeline for Scenario 2 Isolated Protocols"
echo "========================================================================"
echo " Repository Root:    ${REPO_ROOT}"
echo " Scenario Directory: ${SCENARIO_DIR}"
echo " Results Directory:  ${RESULTS_DIR}"
echo " Start Time:         $(date)"
echo "========================================================================"

# -----------------------------------------------------------------------------
# STEP 1: Regenerate Scenario Models & QuaTEx Files from YAML
# -----------------------------------------------------------------------------
echo ""
echo "------------------------------------------------------------------------"
echo " [1/4] Regenerating Maude Scenario Models & QuaTEx Query Files..."
echo "------------------------------------------------------------------------"
cd "${REPO_ROOT}"

SCENARIO_YAMLS=(
    "only_mastodon.yaml"
    "only_obfs.yaml"
    "only_skyhook.yaml"
    "only_webtunnel.yaml"
)

for yaml in "${SCENARIO_YAMLS[@]}"; do
    yaml_path="${SCENARIO_DIR}/${yaml}"
    echo "  -> Processing ${yaml}..."
    python3 "${REPO_ROOT}/scripts/generate_cp3_v3.py" \
        "${yaml_path}" \
        --outDir "${SCENARIO_DIR}" \
        --quatex \
        --filterVpFeatCombos
done
echo "✓ Step 1 Complete: Model files and QuaTEx queries updated."

# -----------------------------------------------------------------------------
# STEP 2: Regenerate Parallel Baselines & Extract CUSUM Distributions
# -----------------------------------------------------------------------------
echo ""
echo "------------------------------------------------------------------------"
echo " [2/4] Regenerating Parallel Baseline Distributions..."
echo "------------------------------------------------------------------------"
cd "${REPO_ROOT}"
python3 "${REPO_ROOT}/scripts/run_cp3_scenario2_isolated_plus_tgen_baselines.py"
echo "✓ Step 2 Complete: Baseline equation files updated."

# -----------------------------------------------------------------------------
# STEP 3: Execute SMC Simulation Suite Across Protocols
# -----------------------------------------------------------------------------
echo ""
echo "------------------------------------------------------------------------"
echo " [3/4] Executing SMC Simulations for Isolated Protocols..."
echo "------------------------------------------------------------------------"
bash "${REPO_ROOT}/scripts/run_cp3_scenario2_isolated_plus_tgen.sh"
echo "✓ Step 3 Complete: SMC simulations finished."

# -----------------------------------------------------------------------------
# STEP 4: Parse Results, Produce CSV Summary, and Generate Plot Dashboards
# -----------------------------------------------------------------------------
echo ""
echo "------------------------------------------------------------------------"
echo " [4/4] Parsing Results & Generating Plot Dashboards..."
echo "------------------------------------------------------------------------"
QUATEX_FILE="${RESULTS_DIR}/only_webtunnel/only_webtunnel-quatex.maude"

if [[ ! -f "${QUATEX_FILE}" ]]; then
    # Fallback to any available quatex file in results
    QUATEX_FILE=$(find "${RESULTS_DIR}" -name "*-quatex.maude" | head -n 1)
fi

python3 "${REPO_ROOT}/scripts/parse_and_plot_cp3_results.py" \
    --results-dir "${RESULTS_DIR}" \
    --quatex-file "${QUATEX_FILE}" \
    --csv

echo ""
echo "========================================================================"
echo " Pipeline Complete Successfully!"
echo " Results & Plots Location: ${RESULTS_DIR}/analysis"
echo " End Time:                  $(date)"
echo "========================================================================"
