# Usernetes with GPU

## Usage

Bring up the cluster. Note that the initial development of this was done in the [flux-usernetes](https://github.com/converged-computing/flux-usernetes/tree/main/google/gpu) repository. The configs are edited here to have mtu maxed to 8896.

```bash
export GOOGLE_PROJECT=llnl-flux
cd ./tf
make
cd ../
```

Then you'll need to add an ephemeral IP address to flux-001, and ssh into it as ubuntu. This should work given you have built the machine with an ssh authorized key added.

```bash
ssh -o IdentitiesOnly=yes ubuntu@34.60.169.37
```

### Control Plane

Determine that nvidia is a runtime option, and rootless is supported:

```console
docker info | grep -i runtimes
 Runtimes: io.containerd.runc.v2 nvidia runc

docker info | grep root
  rootless
```

```bash
cd /opt/usernetes
make up
sleep 5
make nvidia
make kubeadm-init
make install-flannel
make kubeconfig
export KUBECONFIG=/opt/usernetes/kubeconfig
kubectl get pods
make join-command
```

Copy key to worker nodes and bring up the cluster. The f adds non blocking mode, and without the option you would have to enter "yes" to accept the host.

```bash
for i in $(seq 2 2); do
  scp -o "StrictHostKeyChecking no" ./join-command flux-00$i:/opt/usernetes/join-command
  ssh -o "StrictHostKeyChecking no" -f flux-00${i} make -C /opt/usernetes up 
done

for i in $(seq 2 2); do
  ssh -o "StrictHostKeyChecking no" -f flux-00${i} make -C /opt/usernetes nvidia
done

for i in $(seq 2 2); do
  ssh -o "StrictHostKeyChecking no" -f flux-00${i} make -C /opt/usernetes kubeadm-join
done
```

Then finish on the control plane:

```bash
make sync-external-ip
```

If you need to test the nvidia runtime:

```console
docker run --rm -ti --device=nvidia.com/gpu=all ubuntu nvidia-smi -L
GPU 0: Tesla V100-SXM2-16GB (UUID: GPU-798e9725-623d-ca7f-f15d-b1908ec8bb0d)
GPU 1: Tesla V100-SXM2-16GB (UUID: GPU-be5719da-cd52-8a40-09bb-0007224e9236)
```

Install the events monitor.

```bash
oras pull ghcr.io/converged-computing/usernetes-azure:kubernetes-event-monitor
kubectl create namespace monitoring
kubectl apply -f ./kubernetes-event-monitor

mkdir -p ./data/metadata
kubectl get nodes -o json > ./data/metadata/nodes-2-$(date +%s).json

# In another terminal
# NODES=2
# kubectl logs -n monitoring $(kubectl get pods -o json -n monitoring | jq -r .items[0].metadata.name) -f  |& tee ./data/metadata/events-size-$NODES-$(date +%s).json
```

Prepare the control plane:

```bash
kubectl taint nodes u7s-$(hostname) node-role.kubernetes.io/control-plane:NoSchedule-
source <(kubectl completion bash)
kubectl get nodes -o wide
```
```console
NAME                                STATUS   ROLES           AGE     VERSION   INTERNAL-IP   EXTERNAL-IP   OS-IMAGE                         KERNEL-VERSION   CONTAINER-RUNTIME
u7s-flux-001.c.llnl-flux.internal   Ready    control-plane   3m13s   v1.32.1   <none>        10.10.0.4     Debian GNU/Linux 12 (bookworm)   6.8.0-1021-gcp   containerd://2.0.2
u7s-flux-002.c.llnl-flux.internal   Ready    <none>          95s     v1.32.1   <none>        10.10.0.3     Debian GNU/Linux 12 (bookworm)   6.8.0-1021-gcp   containerd://2.0.2
```

And deploy the driver installers:

```bash
kubectl apply -f nvidia-device-plugin.yaml
```

See the nvidia device plugin pods, and check that GPU are found. You should see a line for each node, with one GPU each.

```bash
kubectl get pods -n kube-system
kubectl logs -n kube-system nvidia-device-plugin-daemonset-2vxcv 
```

See the original testing logs for what this looks like.

```bash
kubectl  get nodes -o json | jq -r .items[].status.capacity
```
```console
{
  "cpu": "8",
  "ephemeral-storage": "258932720Ki",
  "hugepages-1Gi": "0",
  "hugepages-2Mi": "0",
  "memory": "30799088Ki",
  "nvidia.com/gpu": "1",
  "pods": "110"
}
{
  "cpu": "8",
  "ephemeral-storage": "258932720Ki",
  "hugepages-1Gi": "0",
  "hugepages-2Mi": "0",
  "memory": "30799100Ki",
  "nvidia.com/gpu": "1",
  "pods": "110"
}
```

Install the pytorch operator.

```bash
kubectl apply --server-side -k "github.com/kubeflow/training-operator.git/manifests/overlays/standalone?ref=v1.8.1"
```
Note that we can't use an older pytorch (that we have to use on GKE) because:

```
  Type     Reason     Age               From               Message
  ----     ------     ----              ----               -------
  Normal   Scheduled  94s               default-scheduler  Successfully assigned default/pytorch-mnist-master-0 to u7s-flux-001.c.llnl-flux.internal
  Warning  Failed     21s               kubelet            Failed to pull image "ghcr.io/converged-computing/pytorch-mnist:fashion-gke": failed to pull and unpack image "ghcr.io/converged-computing/pytorch-mnist:fashion-gke": failed to extract layer sha256:b51c2b01ae19fd8eccd86ab9a8667a71f5ae4f739790cd8859935405bcceca93: mount callback failed on /var/lib/containerd/tmpmounts/containerd-mount2326758777: failed to Lchown "/var/lib/containerd/tmpmounts/containerd-mount2326758777/opt/conda/pkgs/pytorch-1.0.0-py3.6_cuda10.0.130_cudnn7.4.1_1/bin" for UID 1185200044, GID 1185200044: lchown /var/lib/containerd/tmpmounts/containerd-mount2326758777/opt/conda/pkgs/pytorch-1.0.0-py3.6_cuda10.0.130_cudnn7.4.1_1/bin: invalid argument (Hint: try increasing the number of subordinate IDs in /etc/subuid and /etc/subgid)
  Warning  Failed     21s               kubelet            Error: ErrImagePull
  Normal   BackOff    21s               kubelet            Back-off pulling image "ghcr.io/converged-computing/pytorch-mnist:fashion-gke"
  Warning  Failed     21s               kubelet            Error: ImagePullBackOff
  Normal   Pulling    9s (x2 over 93s)  kubelet            Pulling image "ghcr.io/converged-computing/pytorch-mnist:fashion-gke"
```

This means we need to use the latest version of [this image](https://docker.io/kubeflowkatib/pytorch-mnist) here, while for GKE we need to use one tag earlier. 

## Experiment

**IMPORTANT** edit simple.yaml to make the number of workers == size of cluster -1 (there should be one master and the rest are workers).

I usually run the first manually, setting i=1, so I can issue the log stream when I know it is running. This is a throwaway run anyway. Note that I am also running nvidia-smi in another terminal while this is running:

```
while true
  do
  nvidia-smi |& tee -a ./data/metadata/smi-2.txt
  sleep 20
done
```

What I notice subjectively is that it stays high (97-98% utilization) and drops to a few percentages between epochs. Note the above is rough in that it will capture points when nothing is using the GPU. I'm never seeing it get close to the memory max, but it's using a good amount (e.g., 15.4K out of 16k).

```bash
outdir=./data
size=2
mkdir -p $outdir

for i in $(seq 2 6); do     
  echo "Running iteration $i"
  kubectl apply -f ./simple.yaml
  sleep 20
  kubectl logs pytorch-mnist-master-0 -f |& tee ./$outdir/mnist-master-$size-iter-${i}.out
  kubectl wait --for=condition=succeeded --timeout=1200s pytorchjobs.kubeflow.org/pytorch-mnist
  kubectl delete -f simple.yaml --wait
done

lscpu  > data/metadata/lscpu.txt
lspci > data/metadata/lspci.txt
ip address > data/metadata/ip-address.txt
oras login ghcr.io
oras push ghcr.io/converged-computing/usernetes-compute-engine:size-2-mtu ./data
```

## Cleanup 

Exit and:

```bash
cd tf/
export GOOGLE_PROJECT=llnl-flux
make destroy
```

I've been pulling data as I generate it.

```bash
oras pull ghcr.io/converged-computing/usernetes-compute-engine:size-2-mtu
```

I don't see much of a difference between the low and high mtu. But arguably they should be the same between GKE and compute engine so I'll continue to bump it up.
