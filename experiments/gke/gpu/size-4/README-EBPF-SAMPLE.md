# GKE GPU Experiment Size 4

Round 2, one container and 3 samples, and running with and without eBPF for a fair comparison without the "latest" GPU driver. Starting credits 1K (rounding down). Hourly cost is $2.48/GPU and about 20 cents for n1-standard-4, so ~2.70.

- staring credits: 1050
- START TIME: 12:32
- END TIME: 12:49
- COST/HOUR: $10.8
- ESTIMATED COST: 11*(17/60) == ~$4
- credits after: ~1045


```bash
GOOGLE_PROJECT=llnl-flux
NODES=4
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

Note that we can't use compact or ask for the latest driver. It's not clear what driver we get without specifying - we will see!

```console
Note: Starting in GKE 1.30.1-gke.115600, if you don't specify a driver version, GKE installs the default GPU driver for your node's GKE version.
ERROR: (gcloud.container.clusters.create) ResponseError: code=400, message=
        - LATEST GPU driver is only supported with the COS_CONTAINERD node image
        - NodePool's machine type "n1-standard-4" is not supported with compact placement policy.

real    0m3.556s
user    0m0.543s
sys     0m0.078s
```

In the above, we remove gvnic because it's not supported for ubuntu. We need that base OS so we can write. Container optimized OS is read only. Install the Flux Operator and GPU device plugin.

```bash
kubectl apply -f nvidia-device-plugin.yaml
```
```bash
kubectl apply -f https://raw.githubusercontent.com/flux-framework/flux-operator/refs/heads/main/examples/dist/flux-operator.yaml
```

The output directory should already exist.
Note that you'll need to clone [converged-computing/flux-apps-helm](https://github.com/converged-computing/flux-apps-helm).

### LAMMPS Ubuntu OpenMPI GPU

This is ubuntu OpenMPI (default image) with ebpf.

```bash
helm dependency update lammps-reax-gpu/
app=lammps-ubuntu-openmpi-gpu
mkdir -p ./logs/$app
helm install \
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.gpus=1 \
  --set minicluster.tasks=8 \
  --set experiment.tasks=4 \
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
  --set experiment.nodes=4 \
  --set minicluster.size=4 \
  --set minicluster.gpus=1 \
  --set minicluster.tasks=8 \
  --set experiment.tasks=4 \
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
