#!/bin/bash


echo "CLUSTER_NAME is $CLUSTER_NAME"
echo "PROJECT_NAME is $PROJECT_NAME"
echo "ZONE_NAME is $ZONE_NAME"
echo "EXPIRATION_TIME is $EXPIRATION_TIME"


gcloud beta container --project "boneseye" clusters create $CLUSTER_NAME --zone $ZONE_NAME --no-enable-basic-auth --cluster-version $CLUSTER_VERSION --release-channel "regular" --machine-type "e2-medium" --image-type $IMAGE_TYPE --disk-type "pd-standard" --disk-size "100" --metadata disable-legacy-endpoints=true --scopes "https://www.googleapis.com/auth/devstorage.read_only","https://www.googleapis.com/auth/logging.write","https://www.googleapis.com/auth/monitoring","https://www.googleapis.com/auth/servicecontrol","https://www.googleapis.com/auth/service.management.readonly","https://www.googleapis.com/auth/trace.append" --max-pods-per-node "110" --num-nodes $NUM_NODES --logging=SYSTEM,WORKLOAD --monitoring=SYSTEM --enable-ip-alias --network "projects/trolley/global/networks/default" --subnetwork "projects/trolley/regions/us-central1/subnetworks/default" --no-enable-intra-node-visibility --default-max-pods-per-node "110" --no-enable-master-authorized-networks --addons HorizontalPodAutoscaling,HttpLoadBalancing,GcePersistentDiskCsiDriver --enable-autoupgrade --enable-autorepair --max-surge-upgrade 1 --max-unavailable-upgrade 0 --enable-shielded-nodes --node-locations "us-central1-c"
whoami

echo "Adding a PYTHONPATH"
root_path=$WORKSPACE
export PYTHONPATH=${root_path}
echo $PYTHONPATH
echo "WORKSPACE is $WORKSPACE"



# Generating a temp venv
echo "Generating a temp venv"
export RANDOM_VENV=venv_$(shuf -i 1-100000 -n 1)

# Creating a new Python3 virtual environment
echo "Creating a random venv"
python3 -m venv $RANDOM_VENV

# Activating the temp venv
echo "Activating the temp venv"
source $WORKSPACE/$RANDOM_VENV/bin/activate

# Installing project's requirements
echo "Installing project's requirements"
pip3 install -r $WORKSPACE/requirements.txt

# Running post deployment Kubernetes script
echo "Running python3 $WORKSPACE/deployment_utils/kubernetes_post_deployment.py --cluster_type gke --project_id trolley --cluster_name $CLUSTER_NAME --zone_name $ZONE_NAME --expiration_time $EXPIRATION_TIME"
python3 $WORKSPACE/deployment_utils/kubernetes_post_deployment.py --cluster_type gke --project_id trolley --cluster_name $CLUSTER_NAME --zone_name $ZONE_NAME --expiration_time $EXPIRATION_TIME

# Removing a temp venv
rm -R $WORKSPACE/$RANDOM_VENV