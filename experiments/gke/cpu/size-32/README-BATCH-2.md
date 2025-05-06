# GKE CPU Experiment Size 32

```bash
GOOGLE_PROJECT=llnl-flux
NODES=32
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
kubectl get nodes -o json > nodes/nodes-32-batch-2.json 
```

Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### smilei

Stopped working at this size:

```
 --------------------------------------------------------------------------------
 [ERROR](0) src/Params/Params.cpp:1215 (compute) 
 A probem was found in the namelist:
 > ERROR in dimension 1. Patches length = 4 cells must be at least 6 cells long. Increase number of cells or reduce number of patches in this direction. 

 Find out more: https://smileipic.github.io/Smilei/namelist.html#main-variables
 --------------------------------------------------------------------------------
```
```bash
helm dependency update smilei/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2048 \
  --set experiment.tasks=2048 \
  --set experiment.iterations=3 \
  --set minicluster.save_logs=true \
  --set smilei.example=benchmarks/tst2d_v_o2_multiphoton_Breit_Wheeler.py \
  --set smilei.number_of_patches="[32\,64]" \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=32 \
  --set experiment.tasks=2816 \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=32 \
  --set experiment.iterations=3 \
  --set phloem.ndim=2 \
  --set phloem.size=2816 \
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

Froze on third run.

```bash
helm dependency update gpcnet/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set experiment.iterations=1 \
  --set minicluster.save_logs=true \
  gpcnet ./gpcnet

time kubectl wait --for=condition=ready pod -l job-name=gpcnet --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/gpcnet-0.out
helm uninstall gpcnet
```

### hpl

```bash
helm dependency update hpl/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=32  \
  --set experiment.tasks=2816 \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  gromacs ./gromacs

time kubectl wait --for=condition=ready pod -l job-name=gromacs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/gromacs.out
helm uninstall gromacs
```

### qmcpack

**IMPORTANT** The command pre init needs to change total walks to equal number of procs. This is in values.yaml.

```
--------------------------------------------------------------------------
Fatal Error. Aborting at Running on 352 MPI ranks.  The request of 128 global walkers cannot be satisfied! Need at least one walker per MPI rank.
```

```bash
helm dependency update qmcpack/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
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

```bash
# This is 14^3
helm dependency update lulesh/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2744 \
  --set experiment.tasks=2744 \
  --set experiment.iterations=3 \
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
