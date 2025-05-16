# GKE CPU Experiment Size 4

```bash
GOOGLE_PROJECT=llnl-flux
NODES=4
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
kubectl get nodes -o json > ./nodes/nodes-4-batch-3.json 
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
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
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

### LAMMPS with Mpich Rocky

This run did not work.

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:rocky8-mpich \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=5 \
  lammps lammps-reax/

time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps-rocky8-mpich.out
helm uninstall lammps
```

### LAMMPS with OpenMPI Rocky

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
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

### LAMMPS with Intel MPI Rocky

This one for some reason doesn't work automated, but does to shell in. I suspect the MPI isn't ready.
Even interactively it starts to run and fails - we cannot run at larger sizes.

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/converged-computing/lammps-reax:rocky8-intel-mpi \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set minicluster.interactive=true \
  --set experiment.iterations=5 \
  lammps lammps-reax/

time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps-rocky8-intel-mpi.out
helm uninstall lammps
```

Instead of the above, I had to shell in.

```
kubectl exec -it $pod -- bash
flux proxy local:///mnt/flux/view/run/flux/local bash
```

And then look at the log and copy paste what was there.
And we've already run Ubuntu Mpich.

### AMG2023 Mpich Ubuntu

We already tested AMG2023 Ubuntu Openmpi. This one did not work (see log)

```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/converged-computing/amg2023:ubuntu2204-mpich \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="4 8 11" \
  --set experiment.iterations=5 \
  amg amg2023/

time kubectl wait --for=condition=ready pod -l job-name=amg --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg-ubuntu-mpich.out
helm uninstall amg
```

### AMG2023 Rocky Intel MPI

This one also failed.

```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/converged-computing/amg2023:rocky8-intel-mpi \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="4 8 11" \
  --set experiment.iterations=5 \
  amg amg2023/

time kubectl wait --for=condition=ready pod -l job-name=amg --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg-rocky-intel-mpi.out
helm uninstall amg
```

### t8code

```bash
helm dependency update t8code/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=5 \
  --set t8code.flow=3 \
  --set t8code.level=2 \
  --set t8code.rlevel=3 \
  --set t8code.elements=8 \
  --set t8code.cfl=0.7 \
  t8code ./t8code

time kubectl wait --for=condition=ready pod -l job-name=t8code --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/t8code.out
helm uninstall t8code
```

### Lulesh with Intel MPI

This had an error.

```bash
# This is 7*7*7
helm dependency update lulesh/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=343 \
  --set experiment.tasks=343 \
  --set experiment.iterations=5 \
  --set minicluster.image=ghcr.io/converged-computing/lulesh:rocky8-intel-mpi \
  --set minicluster.save_logs=true \
  --set lulesh.iterations=100 \
  --set lulesh.binary=lulesh2.0 \
  --set lulesh.size=100 \
  lulesh ./lulesh

time kubectl wait --for=condition=ready pod -l job-name=lulesh --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lulesh-rocky8-intel-mpi.out
helm uninstall lulesh
```

### Lulesh with Mpich

This also didn't work.

```bash
# This is 7*7*7
helm dependency update lulesh/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=343 \
  --set experiment.tasks=343 \
  --set experiment.iterations=5 \
  --set minicluster.image=ghcr.io/converged-computing/lulesh:ubuntu2204-mpich \
  --set minicluster.save_logs=true \
  --set lulesh.iterations=100 \
  --set lulesh.binary=lulesh2.0 \
  --set lulesh.size=100 \
  lulesh ./lulesh

time kubectl wait --for=condition=ready pod -l job-name=lulesh --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lulesh-ubuntu-mpich.out
helm uninstall lulesh
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
