# GKE CPU Experiment Size 4

We are improving upon our initial performance study by using helm charts to deploy and run our containers.
Note that while not all variables are required for each app (there are defaults) I am defining them below for transparency.

Need to run/ prototype:

- [ ] amg2023 with intel mpi
- [ ] ior  (sharefs)
- [ ] fio (single node
- [ ] nek5000  (sharefs)
- [ ] bdas

## Setup

```bash
GOOGLE_PROJECT=llnl-flux
NODES=4
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
kubectl get nodes -o json > nodes-4-2.json 
```

Install the Flux Operator

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

Make an output directory:

```bash
mkdir -p ./logs
```

## Storage / I/O Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### IOR

```bash
helm dependency update ior/
helm install \
  --set experiment.nodes=1 \
  --set minicluster.size=1 \
  --set minicluster.tasks=12 \
  --set experiment.tasks=12 \
  --set minicluster.save_logs=true \
  --set ior.summaryFormat=CSV \
  --set experiment.iterations=1 \
  ior ior/

time kubectl wait --for=condition=ready pod -l job-name=nekrs --timeout=600s
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
  --set experiment.nodes=1 \
  --set minicluster.size=1 \
  --set minicluster.tasks=12 \
  --set experiment.tasks=12 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=1 \
  ior nekrs/

time kubectl wait --for=condition=ready pod -l job-name=nekrs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/nekrs.out
helm uninstall nekrs
```

### FIO

This is run on single nodes

```bash
helm dependency update fio/
helm install \
  --set experiment.nodes=1 \
  --set minicluster.size=1 \
  --set minicluster.tasks=12 \
  --set experiment.tasks=12 \
  --set minicluster.save_logs=true \
  --set minicluster.show_logs=true \
  --set experiment.foreach=true \
  --set minicluster.save_logs=true \
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

For an amg build with intel MPI:

```console
 --set minicluster.image=ghcr.io/rse-ops/amg2023:intel-mpi
```
```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set minicluster.save_logs=true \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="4 8 11" \
  --set experiment.iterations=5 \
  --set experiment.tasks=352 \
  amg amg2023/

time kubectl wait --for=condition=ready pod -l job-name=amg --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg.out
helm uninstall amg
```

Note that in our performance study we did OMP_NUM_THREADS=2 and I didn't do that here (in testing performance was worse) but to do it, you would add: `--set env.OMP_NUM_THREADS=2`

### LAMMPS

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=5 \
  --set experiment.tasks=352 \
  lammps lammps-reax/

time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/lammps.out
helm uninstall lammps
```

### OSU

First let's do the two that require exact two processes. Note that we are asking for a cluster of 4 nodes but running the benchmark on 2, so we are sampling from the entire cluster.

```bash
helm dependency update osu-benchmarks

for app in osu_latency osu_bw
  do
  helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=2 \
  --set minicluster.save_logs=true \
  --set osu.binary=/opt/osu-benchmark/build.openmpi/mpi/pt2pt/$app \
  --set experiment.iterations=5 \
  --set experiment.pairs=8 \
  --set experiment.tasks=2 \
  osu osu-benchmarks/
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -f |& tee ./logs/$app-pairs.out
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
  --set experiment.nodes=4 \
  --set experiment.tasks=352 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set minicluster.size=4 \
  --set kripke.layout="DGZ" \
  --set kripke.dset=16 \
  --set kripke.gset=16 \
  --set kripke.groups=16 \
  --set kripke.niter=500 \
  --set kripke.procs="8\,4\,11" \
  --set kripke.quad=16 \
  --set kripke.legendre=2 \
  --set kripke.zones="448\,168\,264" \
  kripke kripke/

time kubectl wait --for=condition=ready pod -l job-name=kripke --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/kripke.out
helm uninstall kripke
```

Notes from discussion.

> We need to find the processes for each dimension (kripke.procs) each has to be a divisor of the corresponding zones.
> 6x14x16 has to divide the number of ranks. We need to find zones and processor decomposition such that the process decomp multiplied together is divisible by the number of procs per node. AND each one of the zones is divisible by procs decomps.

```
# 4 nodes
8x4x11
448,168,264

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

```
helm dependency update laghos
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
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
  --set experiment.iterations=5 \
  --set experiment.tasks=352 \
  laghos ./laghos

time kubectl wait --for=condition=ready pod -l job-name=laghos --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/laghos.out
helm uninstall laghos
```

Sometimes mesh tangling at different task numbers.

### Minife

```
helm dependency update ./minife
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
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
  --set experiment.tasks=352 \
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
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=168 \
  --set minicluster.save_logs=true \
  --set quicksilver.inputfile="/opt/quicksilver/Examples/CORAL2_Benchmark/Problem1/Coral2_P1.inp" \
  --set quicksilver.X=64 \
  --set quicksilver.Y=64 \
  --set quicksilver.Z=32 \
  --set quicksilver.x=64 \
  --set quicksilver.y=64 \
  --set quicksilver.z=32 \
  --set quicksilver.I=8 \
  --set quicksilver.J=7 \
  --set quicksilver.K=3 \
  --set env.OMP_NUM_THREADS=2 \
  --set quicksilver.n=41943040 \
  --set experiment.iterations=5 \
  --set experiment.tasks=168 \
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
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
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
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
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


## First Impressions (Testing)

Firstly, we only have 4 nodes (they are about $5/hour so I am being conservative) so we don't have a direct comparison. But the FOM should (I think) be comparable for AMG, and the OSU latency. Some quick impressions:

- The smallest size AMG CPU we had [FOM results](https://github.com/converged-computing/performance-study/tree/main/experiments/google/gke/cpu/size32/results/amg2023) in the order of 3.494748e+08. Here we have one exponential notation lower (e.g., ^7 and not ^8) however there are fewer cpu here (44 vs. 56) so I don't know if we can compare them.
- OSU the easiest to compare are the point to point. We definitely have better point to point latency - going from [~32](https://github.com/converged-computing/performance-study/blob/main/experiments/google/gke/cpu/size32/results/osu/osu-2-iter-4-3353547374592.out) down to ~19.
- I chose the smaller LAMMPS problem size we did for our performance study, albeit only 4 nodes. The CPU utilization was 9% better (see [previous](https://github.com/converged-computing/performance-study/tree/main/analysis/lammps-reax#cpu-utilization-for-cpu-64-x-32-x-32), the values now are ~89%) so we might guess the networking isn't as bad. I can't compare wall times because we didn't run this smaller size on CPU. For 64x65x32 the time is more than double (over 200) and for 64x32x32 here it is 64 seconds.
- I don't know if the zen4 build (container) is optimized for this, haven't thought about that yet.

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
