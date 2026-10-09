# deploy/ — Edge stack (Docker Compose)

```bash
docker compose -f deploy/docker-compose.yml up -d                  # portable stack (Windows/Docker Desktop)
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.linux.yml up -d  # Linux webcam
docker compose -f deploy/docker-compose.yml --profile core up -d   # also ibvap-core in a container
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f frigate
docker compose -f deploy/docker-compose.yml down                   # stop (data volumes are kept)
```

| Service | Port (127.0.0.1 only) | Role |
|---|---|---|
| mosquitto | 1883 | MQTT broker: Frigate publishes events, ibvap-core subscribes |
| mediamtx | 8554 | Publishes configured RTSP/test sources; the Linux overlay adds the webcam |
| frigate | 5000 (internal API), 8971 (UI), 1984 + 8555 (live view: go2rtc, WebRTC) | Detection, tracking, snapshots, clips and the dashboard's live view |
| ibvap-core (profile `core`) | 8000 | Rules, alerts, API and dashboard |

Use the base Compose file on Windows/Docker Desktop. It mounts
`mediamtx.windows.yml`, which intentionally has no `/dev/video0` device.
Use `docker-compose.linux.yml` on Linux when a local webcam is available;
it adds the device and mounts the Linux MediaMTX configuration. Replayed
events and external RTSP cameras work on both platforms.

Optional overrides go in `deploy/.env` (copy from `.env.example`; git-ignored). Images are pinned: Frigate 0.18.0 by digest, MediaMTX 1.21.2, Mosquitto 2.0.20.

The dev broker allows anonymous connections on the local Docker network. Passwords and TLS between services come in Phase 9.

## Optional NVIDIA GPU setup

On Fedora hosts with an NVIDIA GPU, install the NVIDIA Container Toolkit
before adding GPU settings to a service:

```bash
curl -fsSL \
  https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
  | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo >/dev/null
sudo dnf -y install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify the Docker runtime and GPU access:

```bash
docker info --format '{{json .Runtimes}}'
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi
```

The runtime output must include `nvidia`, and the CUDA check must list the
expected GPU. Then start the stack with the GPU override, which gives Frigate the GPU
for hardware video decoding (NVDEC):

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.gpu.yml up -d
```

[`docker-compose.gpu.yml`](docker-compose.gpu.yml) only adds the GPU reservation;
Frigate picks NVDEC by itself. Object detection stays on the CPU (see
[frigate/README.md](../frigate/README.md#what-runs-on-the-gpu)).
