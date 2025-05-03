# GKE GPU Experiment Size 2

## GPU Setup

```bash
GOOGLE_PROJECT=llnl-flux
NODES=4
GPUS=1

time gcloud container clusters create test-cluster \
    --threads-per-core=1 \
    --accelerator type=nvidia-tesla-v100,count=$GPUS,gpu-driver-version=latest \
    --num-nodes=$NODES \
    --machine-type=n1-standard-4 \
    --enable-gvnic \
    --network=mtu9k \
    --system-config-from-file=./system-config.yaml \
    --region=us-central1-a \
    --project=${GOOGLE_PROJECT} 
```

Save nodes:

```bash
kubectl get nodes -o json > nodes-4.json 
```

Install the nvidia device plugin (note that this likely isn't needed, Google Cloud works and does it for you)!

```bash
kubectl apply -f nvidia-device-plugin.yaml
```

Install the Pytorch Operator

```bash
kubectl apply --server-side -k "github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.8.1"
```

And the flux operator:

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## GPU Applications

### Multi-GPU Models

```bash
helm dependency update multi-gpu-models/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.gpus=1 \
  --set minicluster.size=4 \
  --set minicluster.tasks=4 \
  --set experiment.tasks=4 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set mgm.niter=10000 \
  --set mgm.nx=16384 \
  --set mgm.ny=16384 \
  mgm ./multi-gpu-models

time kubectl wait --for=condition=ready pod -l job-name=mgm --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/multi-gpu-models.out
helm uninstall mgm
```

### Kubeflow MNIST Fashion

Note that the master defaults to 1.

```bash
helm dependency update pytorch-mnist-fashion/
for i in 0 1 2 3 4
for i in 3 4
  do
  helm install \
  --set worker.replicas=3 \
  --set master.gpus=1 \
  --set worker.gpus=1 \
  mnist ./pytorch-mnist-fashion
  time kubectl wait --for=condition=ready pod -l training.kubeflow.org/job-name=mnist --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f |& tee ./logs/mnist-${i}.out
  helm uninstall mnist
done
```

### NCCL Tests

Needs test with flux-gpu container

```bash
helm dependency update nccl-tests/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.gpus=1 \
  --set minicluster.size=4 \
  --set minicluster.tasks=4 \
  --set experiment.tasks=4 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set nccl.begin=8 \
  --set nccl.end=1G \
  --set nccl.f=2 \
  --set nccl.g=1 \
  nccl ./nccl-tests

time kubectl wait --for=condition=ready pod -l job-name=nccl --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/nccl-tests.out
helm uninstall nccl
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
