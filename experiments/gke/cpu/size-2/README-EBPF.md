# GKE CPU Experiment Size 2

```bash
GOOGLE_PROJECT=llnl-flux
NODES=2
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

In the above, we remove gvnic because it's not supported for ubuntu. We need that base OS so we can write. Container optimized OS is read only.
Install the Flux Operator

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
for prog in tcp-model cpu-model open-close futex-model shmem
  do
  helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=176 \
  --set experiment.tasks=176 \
  --set minicluster.save_logs=true \
  --set lammps.x=16 \
  --set lammps.y=8 \
  --set lammps.z=8 \
  --set experiment.monitor_program=prog1,prog2 \
  --set experiment.monitor=true \
  --set experiment.iterations=1 \
  lammps ./lammps-reax
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  mkdir -p ./logs/${prog}
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$prog/lammps-ubuntu-openmpi.out
  for pod in $(kubectl get pod -o json | jq -r .items[].metadata.name)
    do
    kubectl logs ${pod} -f |& tee ./logs/$prog/lammps-ubuntu-openmpi-${pod}.out    
  done
  helm uninstall lammps
done
```

### LAMMPS with Mpich Ubuntu


```bash
helm dependency update lammps-reax/
for prog in tcp-model cpu-model open-close futex-model shmem
  do
  helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=176 \
  --set experiment.tasks=176 \
  --set minicluster.save_logs=true \
  --set lammps.x=16 \
  --set lammps.y=8 \
  --set lammps.z=8 \
  --set experiment.iterations=1 \
  --set experiment.monitor_program=$prog \
  --set experiment.monitor=true \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:ubuntu2204-mpich \
  lammps lammps-reax/
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  mkdir -p ./logs/${prog}
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$prog/lammps-ubuntu-mpich.out
  for pod in $(kubectl get pod -o json | jq -r .items[].metadata.name)
    do
    kubectl logs ${pod} -f |& tee ./logs/$prog/lammps-ubuntu-mpich-${pod}.out    
  done
  helm uninstall lammps
done
```


### LAMMPS with OpenMPI Rocky

```bash
helm dependency update lammps-reax/
for prog in tcp-model cpu-model open-close futex-model shmem
  do
  helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=176 \
  --set experiment.tasks=176 \
  --set minicluster.save_logs=true \
  --set lammps.x=16 \
  --set lammps.y=8 \
  --set lammps.z=8 \
  --set experiment.iterations=1 \
  --set experiment.monitor_program=$prog \
  --set experiment.monitor=true \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:rocky8 \
  lammps lammps-reax/
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  mkdir -p ./logs/${prog}
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$prog/lammps-rocky9-openmpi.out
  for pod in $(kubectl get pod -o json | jq -r .items[].metadata.name)
    do
    kubectl logs ${pod} -f |& tee ./logs/$prog/lammps-rocky9-openmpi-${pod}.out    
  done
  helm uninstall lammps
done
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
