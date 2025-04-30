# GKE CPU Experiment Size 32

> Batch 1

These are new applications to supplement those in the main [README](README.md). They are functionally equivalent, however the I/O benchmarks should be run on separate clusters with filesystems enabled / bound.

## Setup

For the applications cluster:

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
kubectl get nodes -o json > nodes-32-batch1.json 
```

Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### IOR

Note that the blocksize must break evenly into transfer size.

https://wiki.lustre.org/IOR

```bash
helm dependency update ior/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=88 \
  --set minicluster.save_logs=true \
  --set minicluster.show_logs=true \
  --set experiment.foreach=true \
  --set ior.transferSize=1M \
  --set ior.blocksize=100M \
  --set ior.summaryFormat=CSV \
  --set experiment.iterations=1 \
  ior ior/

# see https://wiki.lustre.org/IOR
time kubectl wait --for=condition=ready pod -l job-name=ior --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/ior.out
helm uninstall ior
```

### FIO

```bash
helm dependency update fio/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=88 \
  --set minicluster.save_logs=true \
  --set minicluster.show_logs=true \
  --set experiment.foreach=true \
  --set fio.blocksize=256k \
  --set fio.size=100M \
  --set experiment.iterations=1 \
  fio ./fio/

time kubectl wait --for=condition=ready pod -l job-name=nekrs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/fio.out
helm uninstall fio
```

### ES3M Kernels

```bash
helm dependency update e3sm-kernels/

helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=2816 \
  --set minicluster.tasks=2816 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=5 \
  atm ./e3sm-kernels
time kubectl wait --for=condition=ready pod -l job-name=atm --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/atm.out
helm uninstall atm
```

### Miniamr

For this app, npx, npy, npz need to multiply out to procs.

**16 was the first size that didn't segfault!**

```bash
helm dependency update miniamr
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=2816 \
  --set minicluster.tasks=2816 \
  --set miniamr.npx=16 \
  --set miniamr.npy=16 \
  --set miniamr.npz=11 \
  --set miniamr.nx=20 \
  --set miniamr.ny=20 \
  --set miniamr.nz=20 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=5 \
  miniamr ./miniamr
time kubectl wait --for=condition=ready pod -l job-name=miniamr --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/miniamr.out
helm uninstall miniamr
```

### AMG2023

This uses a build with intel MPI.

```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=2816 \
  --set minicluster.tasks=2816 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/rse-ops/amg2023:intel-mpi \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="16 16 11" \
  --set experiment.iterations=5 \
  amg amg2023/

time kubectl wait --for=condition=ready pod -l job-name=amg --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg-intel.out
helm uninstall amg
```

### BDAS

```bash
helm dependency update bdas/
for app in kmeans.r princomp.r svm.r
  do
  helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=2816 \
  --set minicluster.tasks=2816 \
  --set minicluster.save_logs=true \
  --set bdas.benchmark=/opt/bdas/benchmarks/r/${app} \
  --set bdas.rows=1000 \
  --set bdas.rows=250 \
  --set experiment.iterations=5 \
  bdas ./bdas/  
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=bdas --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f |& tee ./logs/bdas-${app}.out
  helm uninstall bdas
done
```

### Chatterbug

```bash
helm dependency update chatterbug/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=2816 \
  --set minicluster.tasks=2816 \
  --set minicluster.save_logs=true \
  --set chatterbug.args="16 16 11 1024 1024 1024 4 100" \
  --set chatterbug.binary="stencil3d" \
  --set experiment.iterations=4 \
  bug ./chatterbug
  time kubectl wait --for=condition=ready pod -l job-name=bug --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/chatterbug.out
helm uninstall bug

  # This was too big (it killed the node)
  # --set chatterbug.args="4 4 11 10000 10000 10000 4 2" \
  # nx * ny * nz needs to equal number of ranks (the first three)
  # the last number is the number of iterations (10)
```

## Qmcpack

**both OOM**

```bash
helm dependency update qmcpack/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=2816 \
  --set minicluster.tasks=2816 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=5 \
  qmcpack ./qmcpack

time kubectl wait --for=condition=ready pod -l job-name=qmcpack --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/qmcpack.out
helm uninstall qmcpack
```

## Netmark

```bash
helm dependency update netmark/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=32 \
  --set minicluster.pullAlways=true \
  --set minicluster.sleep=true \
  --set netmark.warmups=10 \
  --set netmark.trials=20 \
  --set netmark.sendReceiveCycles=100 \
  --set minicluster.sleep=true \
  --set netmark.messageSizeBytes=0 \
  --set netmark.storeTrials=true \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  netmark ./netmark

time kubectl wait --for=condition=ready pod -l job-name=netmark --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/netmark.out
# kubectl exec -it $pod -- bash
kubectl cp $pod:/results/netmark ./logs/netmark
helm uninstall netmark
```

## gamess-r1-mp2-miniapp

**segfault at 2,4,8,16 nodes**

```bash
helm dependency update gamess-r1-mp2-miniapp/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set experiment.tasks=2816 \
  --set minicluster.tasks=2816 \
  --set minicluster.pullAlways=true \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  gamess ./gamess-r1-mp2-miniapp

time kubectl wait --for=condition=ready pod -l job-name=gamess --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/gamess.out
helm uninstall gamess
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
