# Run smc_hcs_base.sh case1 ../results/smc
CASE=$1
DEST=$2
DELTA_BASE=0.01
# --- Outer Loop for different file sizes ---
# This loop starts at 100 and doubles the value until it exceeds 12800.
for (( s=200; s<=1600; s*=2 )); do
	FACTOR=$((${s}/200))
	#DELTA="0.0${FACTOR}"
	DELTA="0.02"
    SIZE="${s}b"	
	FNAME=$DEST/hcs_base_${CASE}_${SIZE}.log 
	echo "========================================"
    echo "--- Running SMC for SIZE: $SIZE, output to $FNAME ---"
    echo "========================================"
	echo "Setting up log files"
	echo "" > $FNAME	
	echo "maude-hcs scheck --test=../use-cases/challenge-problem-1/${CASE}_sim_config_cp1_hcs_base_${SIZE}.maude --query=../smc/pktlatency.quatex --format json -j 0 -d${DELTA}"
	maude-hcs scheck --test=../use-cases/challenge-problem-1/${CASE}_sim_config_cp1_hcs_base_${SIZE}.maude --query=../smc/pktlatency.quatex --format json -j 0 -d${DELTA} > $FNAME
done 


