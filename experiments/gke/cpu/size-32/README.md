# GKE CPU Experiment Size 32

## Setup

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
kubectl get nodes -o json > nodes-32.json 
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

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm). You only need to run `helm dependency update ./<app>` if you make a change to the template.

### AMG2023

```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set minicluster.save_logs=true \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="16 16 11" \
  --set experiment.iterations=5 \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set minicluster.save_logs=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=5 \
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
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
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

And AllReduce

```bash
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set minicluster.save_logs=true \
  --set osu.binary=/opt/osu-benchmark/build.openmpi/mpi/collective/osu_allreduce \
  --set experiment.iterations=5 \
  osu osu-benchmarks/ 

time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/osu_allreduce.out
helm uninstall osuc
```

### Kripke

Note that each run takes 10 minutes - should be done only 2-3 iterations.

```bash
helm dependency update ./kripke/
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set experiment.iterations=5 \
  --set minicluster.save_logs=true \
  --set kripke.layout="DGZ" \
  --set kripke.dset=16 \
  --set kripke.gset=16 \
  --set kripke.groups=16 \
  --set kripke.niter=500 \
  --set kripke.procs="32\,8\,11" \
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
# 32 nodes
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

**Did not work**

This was the perforance study setup.

```bash
helm dependency update laghos
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
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
  laghos ./laghos

time kubectl wait --for=condition=ready pod -l job-name=laghos --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/laghos.out
helm uninstall laghos
```

### Laghos Redo

This was a simpler attempt

```
helm dependency update laghos
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set minicluster.save_logs=true \
  --set laghos.p=1 \
  --set laghos.rs=5 \
  --set laghos.fom=true \
  --set laghos.max_steps=500 \
  --set experiment.iterations=3 \
  laghos ./laghos

time kubectl wait --for=condition=ready pod -l job-name=laghos --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/laghos.out
helm uninstall laghos
```

### Minife

```bash
helm dependency update ./minife
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
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
  minife ./minife

time kubectl wait --for=condition=ready pod -l job-name=minife --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/minife.out
# Note that we need to copy over the output here! Minife generates yaml output
kubectl exec minife-0-xxx -- bash 
# mkdir -p /opt/minife/logs
# /opt/minife/*.yaml /opt/minife/logs
kubectl cp $pod:/opt/minife/logs logs/minife/
helm uninstall minife
```

### quicksilver

```bash
helm dependency update ./quicksilver
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=1344 \
  --set experiment.tasks=1344 \
  --set minicluster.save_logs=true \
  --set quicksilver.inputfile="/opt/quicksilver/Examples/CORAL2_Benchmark/Problem1/Coral2_P1.inp" \
  --set quicksilver.X=128 \
  --set quicksilver.Y=128 \
  --set quicksilver.Z=64 \
  --set quicksilver.x=128 \
  --set quicksilver.y=128 \
  --set quicksilver.z=64 \
  --set quicksilver.I=16 \
  --set quicksilver.J=14 \
  --set quicksilver.K=6 \
  --set quicksilver.n=335544320 \
  --set env.OMP_NUM_THREADS=2 \
  --set experiment.iterations=5 \
  qs ./quicksilver

time kubectl wait --for=condition=ready pod -l job-name=qs --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/quicksilver.out
helm uninstall quicksilver
```

### single node benchmark

```bash
helm dependency update ./single-node
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=1 \
  --set minicluster.save_logs=true \
  --set minicluster.show_logs=true \
  --set experiment.foreach=true \
  --set experiment.iterations=1 \
  single-node ./single-node

time kubectl wait --for=condition=ready pod -l job-name=single-node --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/single-node.out
helm uninstall single-node
```

### stream

```bash
helm dependency update ./stream
helm install \
  --set experiment.nodes=32 \
  --set minicluster.size=32 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=88 \
  --set minicluster.save_logs=true \
  --set minicluster.show_logs=true \
  --set experiment.foreach=true \
  --set experiment.iterations=1 \
  stream ./stream

time kubectl wait --for=condition=ready pod -l job-name=stream --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/stream.out
helm uninstall stream
```

### samurai

```console
helm dependency update ./samurai
helm install \
  --set experiment.nodes=8 \
  --set minicluster.size=8 \
  --set minicluster.tasks=2816 \
  --set experiment.tasks=2816 \
  --set minicluster.save_logs=true \
  --set experiment.iterations=3 \
  --set samurai.min_level=14 \
  --set samurai.max_level=14 \
  sam ./samurai

time kubectl wait --for=condition=ready pod -l job-name=sam --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/samurai.log
helm uninstall sam
```


## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
