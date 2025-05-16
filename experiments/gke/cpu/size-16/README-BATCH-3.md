# GKE CPU Experiment Size 16

```bash
GOOGLE_PROJECT=llnl-flux
NODES=16
INSTANCE=h3-standard-88

time gcloud container clusters create test-cluster \
    --threads-per-core=1 \
    --num-nodes=$NODES \
    --machine-type=$INSTANCE \
    --enable-gvnic \
    --placement-type=COMPACT \
    --network=mtu9k \
    --system-config-from-file=./system-config.yaml \
    --region=us-central1-a \
    --project=${GOOGLE_PROJECT}
```

Save nodes:

```bash
kubectl get nodes -o json > ./nodes/nodes-16-batch-3.json 
```

Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

## CPU Applications

### LAMMPS with Mpich Ubuntu

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=16 \
  --set minicluster.size=16 \
  --set minicluster.tasks=1408 \
  --set experiment.tasks=1408 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:ubuntu2204-mpich \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=5 \
  lammps lammps-reax/

time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps-ubuntu-mpich.out
helm uninstall lammps
```

### LAMMPS with OpenMPI Rocky

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=16 \
  --set minicluster.size=16 \
  --set minicluster.tasks=1408 \
  --set experiment.tasks=1408 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:rocky8 \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=5 \
  lammps lammps-reax/

time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps-rocky8-openmpi.out
helm uninstall lammps
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
