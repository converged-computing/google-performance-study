# GKE CPU Experiment Size 4

Round 2 (for one additional sample), starting credits 1160.

- START TIME: 10:10
- END TIME: 10:21
- COST/HOUR: $20
- ESTIMATED COST: 20*(11/60) == ~$4
- credits after: ~1156


```bash
GOOGLE_PROJECT=llnl-flux
NODES=4
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
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
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
done
helm uninstall lammps
```


### LAMMPS with Mpich Ubuntu

```bash
helm dependency update lammps-reax/
app=lammps-mpich-ubuntu
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
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
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
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


## CPU Applications without eBPF

The above was Sunday morning, this is sunday evening. eBPF with containerd requires removing gvnic, so we want to check that performance differences aren't due to that.

- Starting credits 1059
- START TIME: 9:39
- END TIME: 10:04
- COST/HOUR: $20
- ESTIMATED COST: 20*(25/60) == ~$9
- credits after: ~1050


### LAMMPS with OpenMPI Ubuntu

```bash
helm dependency update lammps-reax/
app=lammps-ubuntu-openmpi
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=3 \
  lammps ./lammps-reax
sleep 5
time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/$app/lammps.out
helm uninstall lammps
```


### LAMMPS with Mpich Ubuntu

```bash
helm dependency update lammps-reax/
app=lammps-mpich-ubuntu
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:ubuntu2204-mpich \
  --set experiment.iterations=3 \
  lammps ./lammps-reax
sleep 5
time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -c lammps -f |& tee ./logs/$app/lammps.out
helm uninstall lammps
```


### LAMMPS with OpenMPI Rocky

```bash
app=lammps-rocky8-openmpi
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:rocky8 \
  --set experiment.iterations=3 \
lammps ./lammps-reax
sleep 5
time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -c lammps -f |& tee ./logs/$app/lammps.out
helm uninstall lammps
```


## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
