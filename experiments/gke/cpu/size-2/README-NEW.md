# GKE CPU Experiment Size 4

These are new applications to supplement those in the main [README](README.md). They are functionally equivalent, however the I/O benchmarks should be run on separate clusters with filesystems enabled / bound.

## Setup

For the applications cluster:

```bash
GOOGLE_PROJECT=llnl-flux
NODES=2
INSTANCE=h3-standard-88

# gcloud compute networks create mtu9k --mtu=8896 
# gcloud compute firewall-rules create mtu9k-firewall --network mtu9k --allow tcp,udp,icmp --source-ranges 0.0.0.0/0

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

For the I/O storage (shared FS) cluster:

```bash
GOOGLE_PROJECT=llnl-flux
NODES=2
INSTANCE=h3-standard-88

time gcloud container clusters create test-cluster \
    --threads-per-core=1 \
    --num-nodes=$NODES \
    --machine-type=$INSTANCE \
    --enable-gvnic \
    --placement-type=COMPACT \
    --addons=GcpFilestoreCsiDriver \
    --network=mtu9k \
    --system-config-from-file=./system-config.yaml \
    --region=us-central1-a \
    --project=${GOOGLE_PROJECT}
```

Save nodes:

```bash
kubectl get nodes -o json > nodes-2-sharedfs.json 
```

### 4. Prepare Filestore

Storage is neat because we can prepare several PVCs, and then have the operator test making a request to write to each one.
Create the PVC as follows:

```bash
kubectl apply -f pvc-filestore.yaml
```

The storage class we are testing is derived from this list:

```bash
kubectl get storageclass
```

And check on the status:

```bash
kubectl get pvc
NAME   STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
data   Pending                                      standard-rwx   6s
```

Note that (in my experience) the Filestore takes ~3 minutes to get working. You'll want to see that the volume was provisioned
via the same command above.

Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.

## Storage / I/O Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### IOR

```bash
helm dependency update ior/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=88 \
  --set experiment.tasks=88 \
  --set minicluster.sleep=true \
  --set minicluster.save_logs=true \
  --set minicluster.volumeName=data \
  --set minicluster.volumePath=/filestore \
  --set minicluster.volumeClaim=data \
  --set experiment.foreach=true \
  --set ior.summaryFormat=CSV \
  --set ior.filename=/filestore/testfile \
  --set experiment.iterations=1 \
  ior ior/

time kubectl wait --for=condition=ready pod -l job-name=ior --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/ior.out
helm uninstall ior
```

# Note that we need the mount point to be shared
# flux run -N$NODES --tasks-per-node=$PPN $IOR_EXEC -o=$DW_JOB_ior/test.bat -m -b=$BS -t=$TS -O summaryFormat=CSV -O summaryFile=$OUTPUT.csv -i 10 -w -r

### NekRS

```bash
helm dependency update nekrs/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set experiment.foreach=true \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  ior nekrs/

time kubectl wait --for=condition=ready pod -l job-name=nekrs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/nekrs.out
helm uninstall nekrs
```

### FIO


```bash
helm dependency update fio/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set minicluster.save_logs=true \
  --set fio.blockSize=256k \
  --set fio.size=4G \
  --set experiment.iterations=1 \
  ior nekrs/

time kubectl wait --for=condition=ready pod -l job-name=nekrs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg.out
helm uninstall nekrs
```

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### AMG2023

This uses a build with intel MPI.

```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set minicluster.save_logs=true \
  --set minicluster.image=ghcr.io/rse-ops/amg2023:intel-mpi \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="2 7 9" \
  --set experiment.iterations=1 \
  amg amg2023/

time kubectl wait --for=condition=ready pod -l job-name=amg --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg.out
helm uninstall amg
```

### BDAS

```bash
helm dependency update bdas/
for app in kmeans.r princomp.r svm.r
  do
  helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set minicluster.save_logs=true \
  --set bdas.benchmark=/opt/bdas/benchmarks/r/${app} \
  --set bdas.rows=1000 \
  --set bdas.rows=250 \
  --set experiment.iterations=1 \
  bdas ./bdas/  
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
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set minicluster.save_logs=true \
  --set chatterbug.binary="stencil3d" \
  --set chatterbug.args="2 7 9 10 10 10 4 10" \
  --set experiment.iterations=1 \
  bug ./chatterbug

# nx * ny * nz needs to equal number of ranks (the first three)
# the last number is the number of iterations (10)

time kubectl wait --for=condition=ready pod -l job-name=bug --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/chatterbug.out
helm uninstall bug
```

### Nekbone

# Note this seems to have different binary per example, AND compiled for specific numbers of processes.
# We will need to compile (again) at runtime.
# ./test/example2/nekbone
# ./test/nek_delay/nekbone
# ./test/nek_comm/nekbone
# ./test/example3/nekbone
# ./test/nek_mgrid/nekbone

```bash
helm dependency update nekbone/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set minicluster.workdir=/root/nekbone-3.0/test/example2 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  nekbone ./nekbone

time kubectl wait --for=condition=ready pod -l job-name=nekbone --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/nekbone.out
helm uninstall nekbone
```

Repository: https://github.com/AMDComputeLibraries/Nekbone

## ExamPM

```bash
helm dependency update exampm/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set exampm.binary="./DamBreak" \
  --set exampm.args="0.05 2 0 0.001 1.0 50 serial" \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  exampm ./exampm

time kubectl wait --for=condition=ready pod -l job-name=exampm --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/exampm
helm uninstall exampm
```

Note that the above doesn't do anything (just hangs)

## Pennant

```bash
helm dependency update pennant/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set pennant.app=/opt/pennant/test/sedovsmall/sedovsmall.pnt \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  pennant ./pennant

time kubectl wait --for=condition=ready pod -l job-name=pennant --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/pennant.out
helm uninstall exampm
```

## Qmcpack

```bash
helm dependency update qmcpack/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=126 \
  --set experiment.tasks=126 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  qmcpack ./qmcpack

time kubectl wait --for=condition=ready pod -l job-name=qmcpack --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/qmcpack.out
helm uninstall pennant
```

Should we build flux into container for mpi error?

Note that [gist is here](https://gist.github.com/vsoch/07050d478f7b0d566bd76a3e0f13202f)

## Netmark

```bash
helm dependency update netmark/
helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set experiment.tasks=2 \
  --set minicluster.tasks=126 \
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

TODO: how do we want the flux run to look?

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
