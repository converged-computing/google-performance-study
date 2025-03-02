# GKE CPU Experiment Size 4

This is primarily for testing.
We are improving upon our initial performance study by using helm charts to deploy and run our containers! 

```bash
kind create cluster --config ./kind-config.yaml
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

We will want to either run this on a GKE instance (we all have access to) OR create the cluster and share the kubeconfig with multiple people, in case someone's computer crashes. We also need a means to programatically monitor the container creation times, etc.

## Experiments

### 1. Setup

Bring up the cluster (with some number of nodes) and install the drivers. Have your GitHub packages (or other registry credential / token) ready. This does not work.

# Testing node types

NC24rs_v3

- *O* c4a-standard-72 (ARM) - we got them! 🎉
- *O* c4-standard-192 (~$10/hour) - we are limited to 500 core, so I tested 2 - we got them! 🎉
- *X* h3-standard-88 (could never get 4 instances, always GCE_STOCKOUT) - tested mid february and twice 2/18/2025
- *X* n4-standard-80 (not supported with compact) GCE_STOCKOUT
- c3 (note we already have quota for 3k, likely for the kubecon experiments)
  - *O* c3-standard-176 - got em! 🎉
  - *X* c3-standard-192-metal (not supported for GKE):
- *O* Z3 (no support for compact, and we somehow already have 3,520 quota?) There is only the option for "highmem" z3-highmem-176 got em! 🎉

```bash
GOOGLE_PROJECT=llnl-flux
NODES=4
INSTANCE=z3-highmem-176

# gcloud compute networks create mtu9k --mtu=8896 
# gcloud compute firewall-rules create mtu9k-firewall --network mtu9k --allow tcp,udp,icmp --source-ranges 0.0.0.0/0

time gcloud container clusters create test-cluster \
    --threads-per-core=1 \
    --num-nodes=$NODES \
    --machine-type=$INSTANCE \
    --network-performance-configs=total-egress-bandwidth-tier=TIER_1 \
    --enable-gvnic \
    --network=mtu9k \
    --system-config-from-file=./system-config.yaml \
    --region=us-central1-a \
    --project=${GOOGLE_PROJECT}

    --placement-type=COMPACT \

```

Save nodes:

```bash
kubectl get nodes -o json > nodes-4.json 
```

### 2. Applications

#### AMG2023

```bash
helm install 
time kubectl wait --for=condition=ready pod -l job-name=flux-sample --timeout=600s
```

This one requires sourcing spack:

```bash
. /etc/profile.d/z10_spack_environment.sh
flux proxy local:///mnt/flux/view/run/flux/local bash
```

Testing

```bash
flux run --env OMP_NUM_THREADS=2 -N 4 -n 112 -o cpu-affinity=per-task amg -n 256 256 128 -P 28 2 2 -problem 2


flux run --env OMP_NUM_THREADS=2 -N 4 -n 112 -o cpu-affinity=per-task amg -n 256 256 128 -P 112 1 1 -problem 2
```

- Total cores: 4 * 56 == 224
- With 2 threads: 224 / 2 == 112
- Different topologies to test for two threads
  - 28 2 2
  - 7 4 4
  - 112 1 1 

```console
oras login ghcr.io --username vsoch
export app=amg2023-size4
output=./results/$app

mkdir -p $output
for i in $(seq 6 10); do     
  echo "Running iteration $i"
  time flux run --env OMP_NUM_THREADS=2 --setattr=user.study_id=$app-iter-$i-28-2-2 -N 4 -n 112 -o cpu-affinity=per-task amg -n 128 128 64 -P 28 2 2 -problem 2
  time flux run --env OMP_NUM_THREADS=2 --setattr=user.study_id=$app-iter-$i-2-28-2 -N 4 -n 112 -o cpu-affinity=per-task amg -n 128 128 64 -P 2 28 2 -problem 2
  time flux run --env OMP_NUM_THREADS=2 --setattr=user.study_id=$app-iter-$i-7-4-4 -N 4 -n 112 -o cpu-affinity=per-task amg -n 128 128 64 -P 7 4 4 -problem 2
  time flux run --env OMP_NUM_THREADS=2 --setattr=user.study_id=$app-iter-$i-2-4-14 -N 4 -n 112 -o cpu-affinity=per-task amg -n 128 128 64 -P 2 4 14 -problem 2
  time flux run --env OMP_NUM_THREADS=2 --setattr=user.study_id=$app-iter-$i-2-4-14 -N 4 -n 112 -o cpu-affinity=per-task amg -n 128 128 64 -P 14 4 2 -problem 2
  time flux run --env OMP_NUM_THREADS=2 --setattr=user.study_id=$app-iter-$i-112-1-1 -N 4 -n 112 -o cpu-affinity=per-task amg -n 128 128 64 -P 112 1 1 -problem 2
done

apt-get update && apt-get install -y jq
# When they are done:
for jobid in $(flux jobs -a --json | jq -r .jobs[].id)
  do
    # Get the job study id
    study_id=$(flux job info $jobid jobspec | jq -r ".attributes.user.study_id")    
    echo "Parsing jobid ${jobid} and study id ${study_id}"
    flux job attach $jobid &> $output/${study_id}-${jobid}.out 
    echo "START OF JOBSPEC" >> $output/${study_id}-${jobid}.out 
    flux job info $jobid jobspec >> $output/${study_id}-${jobid}.out 
    echo "START OF EVENTLOG" >> $output/${study_id}-${jobid}.out 
    flux job info $jobid guest.exec.eventlog >> $output/${study_id}-${jobid}.out
done

oras push ghcr.io/converged-computing/metrics-operator-experiments/performance:gke-cpu-test-$app $output
```
```bash
kubectl delete -f ./crd/amg2023.yaml
```


### Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```

### Results

```console
oras pull ghcr.io/converged-computing/metrics-operator-experiments/performance:gke-cpu-test-amg2023-size4
```
