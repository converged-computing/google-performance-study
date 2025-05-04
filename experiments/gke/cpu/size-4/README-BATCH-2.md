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
mkdir -p nodes/
kubectl get nodes -o json > nodes/nodes-4-batch-2.json 
```

Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### smilei

This is immensely arduous to get params right for.

```bash
helm dependency update smilei/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=256 \
  --set experiment.tasks=256 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set smilei.example=benchmarks/tst2d_v_o2_multiphoton_Breit_Wheeler.py \
  --set smilei.number_of_patches="[16\,16]" \
  --set smilei.simulation_time=10000 \
  smilei ./smilei

time kubectl wait --for=condition=ready pod -l job-name=smilei --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/smilei.out
helm uninstall smilei
```

### pennant

```bash
helm dependency update pennant/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=4 \
  --set experiment.tasks=352 \
  --set minicluster.cores_per_task=88 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  pennant ./pennant

time kubectl wait --for=condition=ready pod -l job-name=pennant --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/pennant.out
helm uninstall pennant
```

### phloem

"d" should be 2, and p (size) should be the total procs.

```bash
helm dependency update phloem
for app in mpiGraph mpiBench
  do
  helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=4 \
  --set experiment.iterations=5 \
  --set phloem.ndim=2 \
  --set phloem.size=352 \
  --set phloem.binary=$app \
  --set minicluster.save_logs=true \
  phloem ./phloem
  time kubectl wait --for=condition=ready pod -l job-name=phloem --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f |& tee ./logs/phloem-$app-d2.out
  helm uninstall phloem
done
```

### gpcnet

```bash
helm dependency update gpcnet/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  gpcnet ./gpcnet

time kubectl wait --for=condition=ready pod -l job-name=gpcnet --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/gpcnet.out
helm uninstall gpcnet
```

### hpl

```bash
helm dependency update hpl/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352  \
  --set experiment.tasks=352 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  hpl ./hpl

time kubectl wait --for=condition=ready pod -l job-name=hpl --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/hpl.out
helm uninstall hpl
```

### hpcg

```bash
helm dependency update hpcg/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=4  \
  --set experiment.tasks=352 \
  --set experiment.iterations=3 \
  --set minicluster.save_logs=true \
  hpcg ./hpcg

time kubectl wait --for=condition=ready pod -l job-name=hpcg --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/hpcg.out
helm uninstall hpcg
```

### rajaperf

```bash
helm dependency update rajaperf/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set experiment.iterations=5 \
  --set rajaperf.kernels="COPY DAXPY REDUCE_SUM" \
  --set minicluster.save_logs=true \
  rajaperf ./rajaperf

time kubectl wait --for=condition=ready pod -l job-name=rajaperf --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/rajaperf.out
helm uninstall rajaperf
```

### gromacs

```bash
helm dependency update gromacs/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  gromacs ./gromacs

time kubectl wait --for=condition=ready pod -l job-name=gromacs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/gromacs.out
helm uninstall gromacs
```

### qmcpack

**IMPORTANT** The command pre init needs to change total walks to equal number of procs.

```
--------------------------------------------------------------------------
Fatal Error. Aborting at Running on 352 MPI ranks.  The request of 128 global walkers cannot be satisfied! Need at least one walker per MPI rank.
```

```bash
helm dependency update qmcpack/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set experiment.iterations=5 \
  --set qmcpack.xml=NiO-fcc-S8-dmc-strongscale.xml \
  --set minicluster.save_logs=true \
  qmcpack ./qmcpack

time kubectl wait --for=condition=ready pod -l job-name=qmcpack --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/qmcpack.out
helm uninstall qmcpack
```


### remhos

```bash
helm dependency update remhos/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set experiment.tasks=352 \
  --set experiment.iterations=5 \
  --set remhos.mesh=data/periodic-cube.mesh \
  --set minicluster.save_logs=true \
  remhos ./remhos

time kubectl wait --for=condition=ready pod -l job-name=remhos --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/remhos.out
helm uninstall remhos
```

### lulesh

Note that "Num processors must be a cube of an integer (1, 8, 27, ...)".

TODO: try size 100 on 4 nodes, decrease if takes too long.

```bash
# This is 7*7*7
helm dependency update lulesh/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=343 \
  --set experiment.tasks=343 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set lulesh.iterations=100 \
  --set lulesh.size=100 \
  lulesh ./lulesh

time kubectl wait --for=condition=ready pod -l job-name=lulesh --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lulesh.out
helm uninstall lulesh
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
