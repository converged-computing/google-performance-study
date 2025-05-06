# GKE CPU Experiment Size 8

## Setup

```bash
GOOGLE_PROJECT=llnl-flux
NODES=8
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

    # h3 doesn't support this
    --network-performance-configs=total-egress-bandwidth-tier=TIER_1 \
```

Save nodes:

```bash
kubectl get nodes -o json > nodes-8-2.json 
```

Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

Make an output directory:

```bash
mkdir -p ./logs/minife
```

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm)

### AMG2023

```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=704 \
  --set minicluster.save_logs=true \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="8 8 11" \
  --set experiment.iterations=5 \
  --set experiment.tasks=704 \
  amg amg2023/

time kubectl wait --for=condition=ready pod -l job-name=amg --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg.out
helm uninstall amg
```

### LAMMPS

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=704 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=5 \
  --set experiment.tasks=704 \
  lammps lammps-reax/

time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps.out
helm uninstall lammps
```

### OSU

Note that adding "pairs" allows for 28 combinations, 8 nodes 2 at a time.

```bash
helm dependency update osu-benchmarks

for app in osu_latency osu_bw
  do
  helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=2 \
  --set minicluster.save_logs=true \
  --set experiment.pairs=8 \
  --set osu.binary=/opt/osu-benchmark/build.openmpi/mpi/pt2pt/$app \
  --set experiment.tasks=2 \
  osu osu-benchmarks/
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f |& tee ./logs/$app.out
  helm uninstall osu
done
```

And reduce

```bash
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set minicluster.save_logs=true \
  --set osu.binary=/opt/osu-benchmark/build.openmpi/mpi/collective/osu_allreduce \
  --set experiment.iterations=5 \
  --set experiment.tasks=352 \
  osu osu-benchmarks/ 

time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/osu_allreduce.out
helm uninstall osu
```

### Kripke

Note that each run takes 10 minutes - should be done only 2-3 iterations.

```
helm dependency update ./kripke/
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set experiment.tasks=704 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set kripke.layout="DGZ" \
  --set kripke.dset=16 \
  --set kripke.gset=16 \
  --set kripke.groups=16 \
  --set kripke.niter=500 \
  --set kripke.procs="8\,8\,11" \
  --set kripke.quad=16 \
  --set kripke.legendre=2 \
  --set kripke.zones="448\,168\,264" \
  kripke kripke/

time kubectl wait --for=condition=ready pod -l job-name=kripke --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/kripke.out
helm uninstall kripke
```

```
# 8 nodes
8x8x11
448,168,264

# 16 nodes
16x8x11
448,168,264

# 32 nodes
16x8x11
448,168,264

# 64 nodes
32x8x11
448,168,264

# 128 nodes
64x8x11
448,168,264

64x8x11
448,168,264
```

- kripke.zones has to be divisible by kripke.procs
- as we double size, one of the procs will need to double

### Laghos

This was the original performance study.

```
helm dependency update laghos
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=704 \
  --set minicluster.save_logs=true \
  --set laghos.p=1 \
  --set laghos.pt=311 \
  --set laghos.dim=2 \
  --set laghos.rs=3 \
  --set laghos.tf=0.8 \
  --set laghos.pa=true \
  --set laghos.fom=true \
  --set laghos.ode_solve=7 \
  --set laghos.max_steps=400 \
  --set laghos.cg_tol=0 \
  --set laghos.cgm=50 \
  --set laghos.ok=3 \
  --set laghos.rp=2 \
  --set laghos.ot=2 \
  --set laghos.mesh=/opt/laghos/data/cube_311_hex.mesh \
  --set experiment.iterations=2 \
  --set experiment.tasks=704 \
  laghos ./laghos

time kubectl wait --for=condition=ready pod -l job-name=laghos --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/laghos-0.out
helm uninstall laghos
```

### Laghos Redo

This was a simpler attempt

```
helm dependency update laghos
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set experiment.tasks=704 \
  --set minicluster.tasks=704 \
  --set minicluster.save_logs=true \
  --set laghos.p=1 \
  --set laghos.rs=5 \
  --set laghos.fom=true \
  --set laghos.max_steps=500 \
  --set experiment.iterations=5 \
  laghos ./laghos

time kubectl wait --for=condition=ready pod -l job-name=laghos --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/laghos.out
helm uninstall laghos
```

### Minife

```
helm dependency update ./minife
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=704 \
  --set minicluster.sleep=true \
  --set minicluster.save_logs=true \
  --set minife.nx=230 \
  --set minife.ny=230 \
  --set minife.nz=230 \
  --set minife.use_locking=1 \
  --set minife.elem_group_size=10 \
  --set minife.use_elem_mat_fields=300 \
  --set minife.verify_solution=0 \
  --set experiment.iterations=5 \
  --set experiment.tasks=704 \
  minife ./minife

time kubectl wait --for=condition=ready pod -l job-name=minife --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/minife.out
# Note that we need to copy over the output here! Minife generates yaml output
kubectl exec minife-0-xxx -- mkdir -p /opt/minife/logs
kubectl exec minife-0-xxx -- cp /opt/minife/*.yaml /opt/minife/logs
kubectl cp minife-0-vbk74:/opt/minife/logs logs/minife/
helm uninstall minife
```

### quicksilver

```console
helm dependency update ./quicksilver
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=336 \
  --set minicluster.save_logs=true \
  --set quicksilver.inputfile="/opt/quicksilver/Examples/CORAL2_Benchmark/Problem1/Coral2_P1.inp" \
  --set quicksilver.X=64 \
  --set quicksilver.Y=64 \
  --set quicksilver.Z=64 \
  --set quicksilver.x=64 \
  --set quicksilver.y=64 \
  --set quicksilver.z=64 \
  --set quicksilver.I=8 \
  --set quicksilver.J=7 \
  --set quicksilver.K=6 \
  --set quicksilver.n=83886080 \
  --set experiment.iterations=5 \
  --set env.OMP_NUM_THREADS=2 \
  --set experiment.tasks=336 \
  qs ./quicksilver

time kubectl wait --for=condition=ready pod -l job-name=qs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/quicksilver.out
helm uninstall quicksilver
```

### single node benchmark

```console
helm dependency update ./single-node
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=8 \
  --set minicluster.save_logs=true \
  --set minicluster.show_logs=true \
  --set experiment.foreach=true \
  --set experiment.iterations=1 \
  --set experiment.tasks=1 \
  single-node ./single-node

time kubectl wait --for=condition=ready pod -l job-name=single-node --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/single-node.out
helm uninstall single-node
```

### stream

```console
helm dependency update ./stream
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=704 \
  --set minicluster.save_logs=true \
  --set minicluster.show_logs=true \
  --set experiment.foreach=true \
  --set experiment.iterations=1 \
  --set experiment.tasks=88 \
  stream ./stream

time kubectl wait --for=condition=ready pod -l job-name=stream --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/stream.out
helm uninstall stream
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
