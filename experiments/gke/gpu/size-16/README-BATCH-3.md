# GKE GPU Experiment Size 16

## GPU Setup

```bash
GOOGLE_PROJECT=llnl-flux
NODES=16
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
kubectl get nodes -o json > nodes/nodes-16-batch-3.json 
```

Install the nvidia device plugin (note that this likely isn't needed, Google Cloud works and does it for you)!

```bash
kubectl apply -f nvidia-device-plugin.yaml
```

Install the flux operator:

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## GPU Applications

### LAMMPS GPU

This is ubuntu OpenMPI (default image) WORKS!

```bash
helm dependency update lammps-reax-gpu/
helm install \
  --set experiment.nodes=16 \
  --set minicluster.gpus=1 \
  --set minicluster.size=16 \
  --set minicluster.tasks=32 \
  --set experiment.tasks=16 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set lammps.kokkos=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  lammps-gpu ./lammps-reax-gpu

time kubectl wait --for=condition=ready pod -l job-name=lammps-gpu --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps-ubuntu-mpi-gpu.out
helm uninstall lammps-gpu
```

### LAMMPS GPU MPich

```bash
helm dependency update lammps-reax-gpu/
helm install \
  --set experiment.nodes=16 \
  --set minicluster.gpus=1 \
  --set minicluster.size=16 \
  --set minicluster.tasks=32 \
  --set experiment.tasks=16 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set lammps.kokkos=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax-gpu:ubuntu2204-mpich \
  lammps-gpu ./lammps-reax-gpu

time kubectl wait --for=condition=ready pod -l job-name=lammps-gpu --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps-gpu-mpich.out
helm uninstall lammps-gpu
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
