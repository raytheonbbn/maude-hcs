# Run run_cp1_experiment.sh maude cmerlin fast_random_sc2_case2 10
EXP_NAME=$1
USER_NAME=$2
APP_PROFILE=$3
NUM_FILES=$4
CLIENT_CONTAINER="${EXP_NAME}_${USER_NAME}_application_client"
for (( i=1; i<=$NUM_FILES; i++ )); do
        FILE_ID=$i
        SEED=$((41 + FILE_ID))
        echo "Transferring file $FILE_ID with seed $SEED"
        docker exec -it $CLIENT_CONTAINER python3 src/cp1_client.py -f data/input/large.dat -l data/logs/ -a application_profiles/$APP_PROFILE.yaml -m 1024 -s $SEED -c $FILE_ID
        echo "Sleep to complete transfer"
        sleep 60
done

echo "Get latencies"
echo "Repatriate logs for experiment $EXP_NAME $USER_NAME"
con_ctrl collect -c "${EXP_NAME}_${USER_NAME}_application_client" -s "${EXP_NAME}_${USER_NAME}_application_server"

echo "Compute $NUM_FILES latencies"
for (( i=1; i<=$NUM_FILES; i++ )); do
        con_ctrl latency -f $i -c /artifacts/tests/client.log -s /artifacts/tests/server.log
done

