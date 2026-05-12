# GPU + Docker Runbook

How to run GPU-enabled containers for P1.AIVideo on a Linux host.

## 1. Host prerequisites

- Ubuntu 22.04 LTS or 24.04 LTS (other distros work but are not covered here).
- A supported NVIDIA GPU (compute capability ≥ 7.5 recommended).
- NVIDIA proprietary driver installed and loaded — verify with:

  ```bash
  nvidia-smi
  ```

  You should see your GPU listed. Driver version should be ≥ 550 for CUDA 12.4 base images.

## 2. Install the NVIDIA Container Toolkit

Adds the `nvidia` runtime to Docker so containers can access the GPU.

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Reference: <https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html>

## 3. Verify GPU access inside a container

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

If you see the same `nvidia-smi` table as on the host, you're done with setup.

## 4. Compose-file GPU declaration

GPU-using services in `docker/compose.gpu.yml` declare device reservations:

```yaml
services:
  agent-lipsync:
    image: aivideo/agent-lipsync:dev
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      NVIDIA_VISIBLE_DEVICES: ${NVIDIA_VISIBLE_DEVICES:-0}
      NVIDIA_DRIVER_CAPABILITIES: ${NVIDIA_DRIVER_CAPABILITIES:-compute,utility,video}
```

`NVIDIA_VISIBLE_DEVICES` controls which physical GPUs the container sees. Use `"0"` for a single GPU host, `"0,1"` for a dual-GPU host, etc.

## 5. Common problems

- **`could not select device driver "" with capabilities: [[gpu]]`** — the NVIDIA Container Toolkit isn't installed or `nvidia-ctk runtime configure` wasn't run. Re-run step 2.
- **CUDA version mismatch** — the container's CUDA runtime must be ≤ the host driver's supported runtime. `nvidia-smi` shows "CUDA Version: 12.x" — this is the **driver's max supported CUDA**, not the host's installed CUDA.
- **OOM during inference** — see `agents/lipsync/README.md` for VRAM expectations per backend. Lower input resolution or switch to a lighter provider (e.g., `LIPSYNC_BACKEND=wav2lip` once implemented).
- **Slow first run** — model load time on cold start is normal. Subsequent runs reuse the in-process model.
- **Two containers competing for the same GPU** — explicitly set `NVIDIA_VISIBLE_DEVICES` per service so jobs don't fight over VRAM.

## 6. Host hygiene

- Reboot after driver upgrades.
- Keep the host driver newer than every container CUDA runtime you use.
- Watch `nvidia-smi -l 1` while a job runs to catch silent fallbacks to CPU.
