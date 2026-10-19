#!/usr/bin/env bash

# Exit on error, unset variables, or failed pipe commands
set -euo pipefail

# -----------------------------------------------------------------------------
# Path & Directory Configuration
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Overridable parameters via environment variables
SMC_FILE="${SMC_FILE:-${REPO_ROOT}/maude_hcs/lib/smc/smc_cp3.maude}"
SCENARIO_DIR="${SCENARIO_DIR:-${REPO_ROOT}/use-cases/challenge-problem-3/cp3_scenarios/scenario2_isolated_plus_tgen}"
OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-${SCENARIO_DIR}/results}"
NSIMS="${NSIMS:-10-10}"
JOBS="${JOBS:-0}"
VERBOSE_FLAG="${VERBOSE_FLAG:---verbose}"
QUERY_FILE_OVERRIDE="${QUERY_FILE:-}"

echo "========================================================================"
echo " Running SMC for CP3 Scenario 2 Isolated Protocols + TGEN"
echo "========================================================================"
echo " Repository Root:    ${REPO_ROOT}"
echo " Scenario Directory: ${SCENARIO_DIR}"
echo " SMC Model File:     ${SMC_FILE}"
echo " Number of Sims:     ${NSIMS}"
echo " Parallel Jobs:      ${JOBS}"
echo " Output Directory:   ${OUTPUT_BASE_DIR}"
echo "========================================================================"

# Validate paths
if [[ ! -d "${SCENARIO_DIR}" ]]; then
    echo "Error: Scenario directory '${SCENARIO_DIR}' not found." >&2
    exit 1
fi

if [[ ! -f "${SMC_FILE}" ]]; then
    echo "Error: SMC file '${SMC_FILE}' not found." >&2
    exit 1
fi

mkdir -p "${OUTPUT_BASE_DIR}"

# Change to the scenario directory so relative 'sload' paths in .maude files resolve properly
cd "${SCENARIO_DIR}"

# Find all only_*-run.maude test files
TEST_FILES=( only_*-run.maude )

if [[ ${#TEST_FILES[@]} -eq 0 || ! -f "${TEST_FILES[0]}" ]]; then
    echo "Error: No 'only_*-run.maude' files found in ${SCENARIO_DIR}." >&2
    exit 1
fi

TOTAL=${#TEST_FILES[@]}
CURRENT=0
FAILED_TESTS=()

for test_file in "${TEST_FILES[@]}"; do
    ((CURRENT++))
    raw_name="$(basename "${test_file}" .maude)"
    # Strip '-run' suffix if present for clean directory and file output names (e.g. only_mastodon)
    test_name="${raw_name%-run}"

    # Determine QuaTEx query file to use
    if [[ -n "${QUERY_FILE_OVERRIDE}" ]]; then
        query_file="${QUERY_FILE_OVERRIDE}"
    else
        query_file="${SCENARIO_DIR}/${test_name}-quatex.maude"
    fi

    if [[ ! -f "${query_file}" ]]; then
        echo "Error: QuaTEx query file '${query_file}' not found." >&2
        exit 1
    fi

    test_out_dir="${OUTPUT_BASE_DIR}/${test_name}"
    mkdir -p "${test_out_dir}"
    rm -f "${test_out_dir}"/dump.log* "${test_out_dir}"/*.json "${test_out_dir}"/*.log

    # Copy the QuaTEx query file into the protocol directory
    cp "${query_file}" "${test_out_dir}/"

    dump_log="${test_out_dir}/dump.log"
    json_out="${test_out_dir}/${test_name}.json"
    run_log="${test_out_dir}/run.log"
    quatex_copy="${test_out_dir}/$(basename "${query_file}")"

    echo ""
    echo "[${CURRENT}/${TOTAL}] Starting test: ${test_name} (${test_file})"
    echo "  -> Target Test File:  ${SCENARIO_DIR}/${test_file}"
    echo "  -> QuaTEx File:       ${quatex_copy}"
    echo "  -> Formatted JSON:    ${json_out}"
    echo "  -> Dump Results:      ${dump_log}"
    SEED=$((RANDOM * 32768 + RANDOM))
    echo "  -> Random Seed:       ${SEED}"
    echo "  -> Execution Log:     ${run_log}"
    echo "------------------------------------------------------------------------"

    START_TIME=$(date +%s)

    # Execute maude-hcs scheck with time measurement
    # - stdout (formatted JSON and logs) goes to json_out / run_log
    # - stderr (timing & errors) goes to run_log
    set +e
    (
        time maude-hcs ${VERBOSE_FLAG} scheck \
            --module=HCS_TEST \
            --seed="${SEED}" \
            --query="${query_file}" \
            --test="${SCENARIO_DIR}/${test_file}" \
            --file="${SMC_FILE}" \
            -n "${NSIMS}" \
            -j "${JOBS}" \
            --dump="${dump_log}" \
            --format=json
    ) > "${json_out}" 2> "${run_log}"
    EXIT_CODE=$?
    set -e

    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))

    if [[ ${EXIT_CODE} -eq 0 ]]; then
        echo "✓ [${test_name}] Completed successfully in ${ELAPSED}s."
    else
        echo "✗ [${test_name}] Failed with exit code ${EXIT_CODE} after ${ELAPSED}s. (See ${run_log})"
        FAILED_TESTS+=( "${test_name}" )
    fi
done

echo ""
echo "========================================================================"
echo " All tests finished!"
echo " Results directory: ${OUTPUT_BASE_DIR}"
if [[ ${#FAILED_TESTS[@]} -gt 0 ]]; then
    echo " Failed tests: ${FAILED_TESTS[*]}"
    exit 1
else
    echo " Status: All ${TOTAL} tests completed successfully."
fi
echo "========================================================================"
