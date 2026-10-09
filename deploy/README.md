# deploy/ — Edge stack (Docker Compose)

```bash
docker compose -f deploy/docker-compose.yml up -d                  # Mosquitto, MediaMTX (webcam as RTSP), Frigate
docker compose -f deploy/docker-compose.yml --profile core up -d   # also ibvap-core in a container
docker compose -f deploy/docker-compose.yml ps
docker compose -f deploy/docker-compose.yml logs -f frigate
docker compose -f deploy/docker-compose.yml down                   # stop (data volumes are kept)
```

| Service | Port (127.0.0.1 only) | Role |
|---|---|---|
| mosquitto | 1883 | MQTT broker: Frigate publishes events, ibvap-core subscribes |
| mediamtx | 8554 | Publishes the webcam (and optional looped test clips) as RTSP camera streams |
| frigate | 5000 (internal API), 8971 (UI) | Detection, tracking, snapshots and clips |
| ibvap-core (profile `core`) | 8000 | Rules, alerts, API and dashboard |

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
expected GPU. Do not enable GPU settings in Compose or switch Frigate
detectors until both checks pass and a compatible Frigate GPU detector image
and model have been selected.
