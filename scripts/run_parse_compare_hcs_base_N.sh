# Run smc_hcs_base.sh case1 ../results/smc
CASE=$1

# --- Outer Loop for different file sizes ---
# This loop starts at 100 and doubles the value until it exceeds 12800.
for (( s=200; s<=1600; s*=2 )); do
    SIZE="${s}b"
	echo "========================================"
    echo "--- Running SMC for SIZE: $SIZE, case $CASE ---"
    echo "========================================"		
	echo "python parse_compare_hcs_base_N.py ../results/tests/${CASE}/iodine_hcs_base_${SIZE}yte.log-out.dat ../results/smc/hcs_base_${CASE}_${SIZE}.log"
	python parse_compare_hcs_base_N.py ../results/tests/${CASE}/iodine_hcs_base_${SIZE}yte.log-out.dat ../results/smc/hcs_base_${CASE}_${SIZE}.log
    python parse_compare_hcs_base_relative_N.py ${CASE}
done 


