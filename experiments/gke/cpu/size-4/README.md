# GKE CPU Experiment Size 4

We are improving upon our initial performance study by using helm charts to deploy and run our containers.

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
kubectl get nodes -o json > nodes-4.json 
```

Install the Flux Operator

```
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

Make an output directory:

```bash
mkdir -p ./logs
```

## Applications

Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm)

### AMG2023

```bash
helm dependency update amg2023/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
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

Note that in our performance study we did OMP_NUM_THREADS=2 and I didn't do that here. Let me try that.

```bash
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set env.OMP_NUM_THREADS=2 \
  --set minicluster.tasks=176 \
  --set amg.problem_size="256 256 128" \
  --set amg.processor_topology="4 4 11" \
  --set experiment.iterations=3 \
  --set experiment.tasks=176 \
  amg amg2023/

time kubectl wait --for=condition=ready pod -l job-name=amg --timeout=600s
sleep 5
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/amg-with-threads.out
helm uninstall amg
```

### LAMMPS

```bash
helm dependency update lammps-reax/
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.tasks=352 \
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

First let's do the two that require exact two processes.

```bash
helm dependency update osu-benchmarks

for app in osu_latency osu_bw
  do
  helm install \
  --set experiment.nodes=2 \
  --set minicluster.size=2 \
  --set minicluster.tasks=2 \
  --set osu.binary=/opt/osu-benchmark/build.openmpi/mpi/pt2pt/$app \
  --set experiment.iterations=5 \
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
  --set osu.binary=/opt/osu-benchmark/build.openmpi/mpi/collective/osu_allreduce \
  --set experiment.iterations=5 \
  --set experiment.tasks=352 \
  osu osu-benchmarks/

time kubectl wait --for=condition=ready pod -l job-name=osu --timeout=600s
pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
kubectl logs ${pod} -f |& tee ./logs/osu_allreduce.out
helm uninstall osu
```

## First Impressions

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
