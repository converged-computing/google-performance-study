# GKE CPU Experiment Size 16

We are counting from the point of asking to create to over-estimate and not overshoot.

credits starting at 1588

- START TIME: 8:29am
- END TIME: 8:43am
- COST/HOUR: $80
- ESTIMATED COST: 80*(14/60) == ~$19 (round up to 20)
- credits after: ~1568

Round 2 (for one additional sample), starting credits 1146.

- START TIME: 10:46
- END TIME: 10:59
- COST/HOUR: $80
- ESTIMATED COST: 80*(13/60) == ~$18
- credits after: ~1128

```bash
GOOGLE_PROJECT=llnl-flux
NODES=16
INSTANCE=h3-standard-88

time gcloud container clusters create test-cluster \
    --threads-per-core=1 \
    --num-nodes=$NODES \
    --image-type=UBUNTU_CONTAINERD \
    --machine-type=$INSTANCE \
    --placement-type=COMPACT \
    --network=mtu9k \
    --system-config-from-file=./system-config.yaml \
    --region=us-central1-a \
    --project=${GOOGLE_PROJECT}
```

In the above, we remove gvnic because it's not supported for ubuntu. We need that base OS so we can write. Container optimized OS is read only. Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

## CPU Applications

### LAMMPS with OpenMPI Ubuntu

```bash
helm dependency update lammps-reax/
app=lammps-ubuntu-openmpi
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=16 \
  --set minicluster.size=16 \
  --set minicluster.tasks=1408 \
  --set experiment.tasks=1408 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.monitor="tcp|cpu|open_close|futex|shmem" \
  --set experiment.iterations=3 \
  lammps ./lammps-reax
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$app/lammps.out
  # Now each pod will run a different app
  for pod in $(kubectl get pod -o json | jq -r .items[].metadata.name)
    do
     kubectl logs ${pod} -c bcc-monitor -f > ./logs/$app/${pod}.out    
  done
helm uninstall lammps
```


### LAMMPS with Mpich Ubuntu

```bash
helm dependency update lammps-reax/
app=lammps-mpich-ubuntu
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=16 \
  --set minicluster.size=16 \
  --set minicluster.tasks=1408 \
  --set experiment.tasks=1408 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:ubuntu2204-mpich \
  --set experiment.monitor="tcp|cpu|open_close|futex|shmem" \
  --set experiment.iterations=3 \
  lammps ./lammps-reax
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$app/lammps.out
  for pod in $(kubectl get pod -o json | jq -r .items[].metadata.name)
    do
     kubectl logs ${pod} -c bcc-monitor -f > ./logs/$app/${pod}.out    
  done
helm uninstall lammps
```


### LAMMPS with OpenMPI Rocky

```bash
app=lammps-rocky8-openmpi
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=16 \
  --set minicluster.size=16 \
  --set minicluster.tasks=1408 \
  --set experiment.tasks=1408 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:rocky8 \
  --set experiment.monitor="tcp|cpu|open_close|futex|shmem" \
  --set experiment.iterations=3 \
  lammps ./lammps-reax
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$app/lammps.out
  for pod in $(kubectl get pod -o json | jq -r .items[].metadata.name)
    do
     kubectl logs ${pod} -c bcc-monitor -f > ./logs/$app/${pod}.out    
  done
helm uninstall lammps
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
