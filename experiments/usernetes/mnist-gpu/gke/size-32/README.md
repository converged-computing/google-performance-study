# GKE GPU Experiment Size 32

## Experiment

### 1. Setup

```bash
GOOGLE_PROJECT=llnl-flux
GPUS=1
NODES=32
INSTANCE=n1-standard-8

time gcloud container clusters create gpu-cluster \
    --threads-per-core=1 \
    --accelerator type=nvidia-tesla-v100,count=$GPUS,gpu-driver-version=latest \
    --num-nodes=$NODES \
    --machine-type=$INSTANCE \
    --enable-gvnic \
    --network=mtu9k \
    --system-config-from-file=./system-config.yaml \
    --region=us-central1-a \
    --project=${GOOGLE_PROJECT} 
```
```console
kubeconfig entry generated for gpu-cluster.
NAME         LOCATION       MASTER_VERSION      MASTER_IP     MACHINE_TYPE   NODE_VERSION        NUM_NODES  STATUS
gpu-cluster  us-central1-a  1.31.5-gke.1068000  34.173.81.50  n1-standard-8  1.31.5-gke.1068000  32         RUNNING

real	5m3.019s
user	0m1.611s
sys	0m0.239s
```

Sanity check installed on all nodes

```bash
kubectl get nodes -o json | jq .items[].status.allocatable
kubectl get nodes -o json | jq .items[].status.allocatable | grep nvidia | wc -l
```
```
32
```

Install the kubernetes events exporter:

```bash
kubectl create namespace monitoring
kubectl apply -f ../kubernetes-event-monitor
mkdir -p ./data/metadata
kubectl get nodes -o json > ./data/metadata/nodes-$NODES-$(date +%s).json

# In another terminal
NODES=32
kubectl logs -n monitoring $(kubectl get pods -o json -n monitoring | jq -r .items[0].metadata.name) -f  |& tee ./data/metadata/events-size-$NODES-$(date +%s).json
```

Install the PytorchJob (Kubeflow) operator:

```bash
# Install version 1 of the pytorch training-operator
kubectl apply --server-side -k "github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.8.1"
```

The data is already pulled to the image.  Note for the first, you might want to run the command manually until the container is pulled on all nodes.

```bash
outdir=./data
size=32
mkdir -p $outdir
i=1
# Run the first i=1 manually, copy pasting lines

# Note - the first run takes longer and should be thrown out.
# Instead I will run 6 iterations
for i in $(seq 2 6); do
  echo "Running iteration $i"
  kubectl apply -f ./simple.yaml
  sleep 20
  kubectl logs pytorch-mnist-master-0 -f |& tee ./$outdir/mnist-master-$size-iter-${i}.out
  kubectl wait --for=condition=succeeded --timeout=1200s pytorchjobs.kubeflow.org/pytorch-mnist
  kubectl delete -f simple.yaml --wait
done
```

## Cleanup 

```bash
time gcloud container clusters delete gpu-cluster --region us-central1-a
```
```console
Deleted [https://container.googleapis.com/v1/projects/llnl-flux/zones/us-central1-a/clusters/gpu-cluster].

real	3m35.588s
user	0m1.374s
sys	0m0.228s
```
