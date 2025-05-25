# GKE GPU Experiment Size 16

Round 2, one container and 3 samples, and running with and without eBPF for a fair comparison without the "latest" GPU driver.  
Hourly cost is $2.48/GPU and about 20 cents for n1-standard-4, so ~2.70.

- staring credits: 1039
- START TIME: 1:15pm
- END TIME: 13:29pm
- COST/HOUR: $44
- ESTIMATED COST: 44*(14/60) == ~$11
- credits after: 1028



```bash
GOOGLE_PROJECT=llnl-flux
NODES=16
GPUS=1

time gcloud container clusters create test-cluster \
    --threads-per-core=1 \
    --accelerator type=nvidia-tesla-v100,count=$GPUS \
    --num-nodes=$NODES \
    --image-type=UBUNTU_CONTAINERD \
    --machine-type=n1-standard-4 \
    --network=mtu9k \
    --system-config-from-file=./system-config.yaml \
    --region=us-central1-a \
    --project=${GOOGLE_PROJECT}
```

In the above, we remove gvnic because it's not supported for ubuntu. We need that base OS so we can write. Container optimized OS is read only. Install the Flux Operator:

```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.
Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### LAMMPS Ubuntu OpenMPI GPU

This is ubuntu OpenMPI (default image) with ebpf.

```bash
# helm dependency update lammps-reax-gpu/
app=lammps-ubuntu-openmpi-gpu
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=16 \
  --set minicluster.size=16 \
  --set minicluster.gpus=1 \
  --set minicluster.tasks=32 \
  --set experiment.tasks=16 \
  --set minicluster.save_logs=true \
  --set lammps.kokkos=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.monitor="tcp|cpu|open_close|futex|shmem" \
  --set experiment.iterations=3 \
  lammps ./lammps-reax-gpu
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$app/lammps.out
  for pod in $(kubectl get pod -o json | jq -r .items[].metadata.name)
    do
     kubectl logs ${pod} -c bcc-monitor -f > ./logs/$app/${pod}.out    
  done
helm uninstall lammps
```


### LAMMPS Ubuntu OpenMPI GPu without eBPF

```bash
app=lammps-ubuntu-openmpi-gpu-noebpf
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=16 \
  --set minicluster.size=16 \
  --set minicluster.gpus=1 \
  --set minicluster.tasks=32 \
  --set experiment.tasks=16 \
  --set minicluster.save_logs=true \
  --set lammps.kokkos=true \
  --set lammps.x=32 \
  --set lammps.y=16 \
  --set lammps.z=16 \
  --set experiment.iterations=3 \
  lammps ./lammps-reax-gpu
  sleep 5
  time kubectl wait --for=condition=ready pod -l job-name=lammps --timeout=600s
  pod=$(kubectl get pods -o json | jq  -r .items[0].metadata.name)
  kubectl logs ${pod} -c lammps -f |& tee ./logs/$app/lammps.out
helm uninstall lammps
```

## Clean Up

When you are done:

```bash
gcloud container clusters delete test-cluster --region=us-central1-a
```
