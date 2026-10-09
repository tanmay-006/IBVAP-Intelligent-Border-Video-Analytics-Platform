# IBVAP setup guide

How to install, start and check the IBVAP edge stack on a development laptop, from a fresh clone to a live alert in the dashboard.

What you will have running at the end:

| Component | Runs in | Port (127.0.0.1 only) | Role |
|---|---|---|---|
| Mosquitto | Docker | 1883 | MQTT broker: Frigate publishes events, ibvap-core subscribes |
| MediaMTX | Docker | 8554 | Publishes your webcam as an RTSP camera stream |
| Frigate 0.18 | Docker | 5000 (API), 8971 (UI) | Detects and tracks people and vehicles; keeps snapshots and clips |
| ibvap-core | Your terminal (or Docker) | 8000 | Border rules, alerts, API, and the operator dashboard at `/ui/` |

---

## 1. Prerequisites

| Need | Version | Check with |
|---|---|---|
| Linux (tested on Fedora 44) | — | — |
| Python | 3.12 | `python3 --version` |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | 0.11+ | `uv --version` |
| Node.js + npm | 22 | `node --version` |
| Docker Engine | 24+ | `docker --version` |
| Docker Compose plugin | v2+ | `docker compose version` |
| Free disk space | about 12 GB (the Frigate image alone is 8.6 GB) | `df -h /` |
| Webcam at `/dev/video0` | optional | `ls /dev/video0` |

**Docker without sudo:** your user must be in the `docker` group. Check with `groups`. If it isn't:
1. Run `sudo usermod -aG docker $USER`.
2. Log out and back in.

**Docker Compose plugin missing** (`docker: unknown command: docker compose`):
- **With admin rights:** install your distribution's `docker-compose-plugin` package.
- **Without admin rights:** install it for your user only.

  ```bash
  mkdir -p ~/.docker/cli-plugins
  curl -SL https://github.com/docker/compose/releases/download/v5.6.0/docker-compose-linux-x86_64 \
    -o ~/.docker/cli-plugins/docker-compose
  chmod +x ~/.docker/cli-plugins/docker-compose
  docker compose version
  ```

  Optionally verify the download against `checksums.txt` from the same release page.

**Optional NVIDIA GPU support (Fedora):**

The NVIDIA Container Toolkit must be installed and Docker must be restarted
before a container can access the GPU. The installation requires `sudo`:

```bash
curl -fsSL \
  https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
  | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo >/dev/null
sudo dnf -y install nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify the runtime before changing Frigate's detector configuration:

```bash
docker info --format '{{json .Runtimes}}'
docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu24.04 nvidia-smi
```

The first command must include an `nvidia` runtime, and the second must list
the expected GPU. Installing the toolkit does not automatically move Frigate
inference to the GPU. A compatible Frigate GPU image/model and detector
configuration are still required; the tested default remains the OpenVINO CPU
detector.

---

## 2. Get the code

```bash
git clone https://github.com/tanmay-006/IBVAP-Intelligent-Border-Video-Analytics-Platform.git
cd IBVAP-Intelligent-Border-Video-Analytics-Platform
```

Every command below starts from this repository folder unless it says otherwise.

---

## 3. One-time setup

**Backend dependencies:**

```bash
cd ibvap-core
uv sync
cd ..
```

**Build the dashboard** (ibvap-core serves the built files at `/ui/`):

```bash
cd dashboard
npm install
npm run build
cd ..
```

**Download the container images** (several GB; takes a while on the first run):

```bash
docker compose -f deploy/docker-compose.yml pull
```

**Optional settings:** the defaults work as they are. To change anything, such as the site ID, ports or thresholds:
1. Copy the template: `cp deploy/.env.example deploy/.env`.
2. Edit `deploy/.env`.

`deploy/.env` is ignored by git, so never commit real passwords.

**No webcam?** Open [`deploy/docker-compose.yml`](deploy/docker-compose.yml) and delete these two lines under `mediamtx`. Otherwise Docker refuses to start the stack.

```yaml
    devices:
      - /dev/video0:/dev/video0
```

You can still run the full demo with replayed events (step 5B).

---

## 4. Start the project

### Step 1: start the edge stack

```bash
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml ps
```

All three services (`mosquitto`, `mediamtx`, `frigate`) should show **running**. Frigate takes about 30 seconds before it reports `(healthy)`.

### Step 2: start ibvap-core

Use a separate terminal; it keeps running in the foreground.

```bash
cd ibvap-core
uv run uvicorn ibvap_core.api:create_app --factory --port 8000
```

Wait for these two lines:

```text
INFO ibvap_core.api: loaded 3 camera rule sets from .../ibvap-core/config/rules.yaml (version ...)
INFO ibvap_core.mqtt_consumer: subscribed to frigate/events on localhost
```

ibvap-core finds its config, database and dashboard relative to its own folder, so you can start it from any directory.

### Step 3: open the dashboard

http://127.0.0.1:8000/ui/

The header should show **Live** and **Camera feed connected**.

---

## 5. See it work

### A. Live, with the webcam

The webcam is camera `cam-gate-west`. A virtual gate line runs down the middle of the frame, and the right half counts as the Indian side.

1. Stand left of centre, in the webcam's view.
2. Walk across to the right.
3. The dashboard shows a **gate crossing (inbound)** alert, with Frigate's snapshot and clip:
   - **Critical** between 18:30 and 06:00 IST
   - **High** in the daytime

Staying in the right half for over 30 s also raises a **Loitering** alert. Walking right to left raises an **outbound** crossing.

### B. Without a camera: replayed events

```bash
cd ibvap-core
uv run python scripts/publish_sample_events.py
```

This replays scripted Frigate events for the two demo cameras, `cam-fence-east` and `cam-bop-road`:
- a fence crossing
- a night-movement alert
- a car with a fictional low-confidence number plate
- after about 30 s, a "vehicle stopped" alert

These events have no real snapshots, so the dashboard says *"Snapshot could not be loaded"* for them. That is expected.

### Useful pages

| URL | What it is |
|---|---|
| http://127.0.0.1:8000/ui/ | Operator dashboard |
| http://127.0.0.1:8000/ui/#search | Event search |
| http://127.0.0.1:8000/docs | Interactive API (try every endpoint) |
| http://127.0.0.1:8000/health | Rules version, MQTT connection, connected consoles |
| http://127.0.0.1:8000/metrics/latency | Processing latency per stage |
| http://127.0.0.1:8971 | Frigate's own UI: live view and detections |

**Frigate UI login:** user `admin`. Frigate generates the password on its first start; read it with:

```bash
docker compose -f deploy/docker-compose.yml logs frigate | grep Password
```

Change it in the Frigate UI after the first login. Never put it in the repo.

---

## 6. Stop and restart

Closing the terminal does **not** stop IBVAP: the containers keep running and come back after a reboot. To stop everything, or to find something that is still running, see **[STOPPING.md](STOPPING.md)**.

| To | Run |
|---|---|
| Stop ibvap-core | Ctrl+C in its terminal |
| Stop the edge stack (keeps data) | `docker compose -f deploy/docker-compose.yml down` |
| Start again later | Step 1 and Step 2 of section 4; no setup needed |
| Run ibvap-core in Docker too | `docker compose -f deploy/docker-compose.yml --profile core up -d --build` (skip Step 2) |

After changing **rules or camera settings**, restart only the component that reads them:

| You changed | Restart |
|---|---|
| `ibvap-core/config/rules.yaml` or `site.yaml` | ibvap-core (Ctrl+C, then start it again) |
| `frigate/config.yml` | `docker compose -f deploy/docker-compose.yml restart frigate` |
| `deploy/mediamtx/mediamtx.yml` | `docker compose -f deploy/docker-compose.yml restart mediamtx` |
| Dashboard source (`dashboard/src`) | `cd dashboard && npm run build`, then reload the browser |

---

## 7. Check that everything is healthy

```bash
docker compose -f deploy/docker-compose.yml ps                 # 3 services running, frigate (healthy)
curl -s 127.0.0.1:5000/api/version                             # Frigate answers, e.g. 0.18.0-...
curl -s 127.0.0.1:8000/health                                  # "mqtt_connected": true, rules_version set
curl -s 127.0.0.1:5000/api/stats | python3 -m json.tool | grep -E '"inference_speed"|"camera_fps"'
```

`inference_speed` should be in the tens of milliseconds or less; about 10 ms on a Ryzen 5 laptop CPU. `camera_fps` should be about 5.

**Run the tests:**

```bash
cd ibvap-core && uv run pytest && cd ..
cd dashboard && npm test && cd ..
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Cannot reach MQTT broker at localhost:1883` / `MQTT broker localhost:1883 unavailable` | The broker isn't running | Start the edge stack (section 4, Step 1). ibvap-core reconnects on its own within 30 s |
| `The container name "/ibvap-mqtt" is already in use` | A broker started earlier with plain `docker run` (older instructions) | It's already running. To switch to the Compose stack: `docker stop ibvap-mqtt`, then Step 1 |
| `Bind for 127.0.0.1:1883 failed: port is already allocated` | Another broker holds port 1883 | `docker ps`, stop the other container (often `ibvap-mqtt`), run Step 1 again |
| `address already in use` on port 8000 | ibvap-core is already running in another terminal | Use that one, or stop it with Ctrl+C there |
| `/` opens the API docs, not the dashboard | The dashboard isn't built | `cd dashboard && npm install && npm run build`, then restart ibvap-core |
| Dashboard says *"Snapshot could not be loaded"* | Event has no Frigate media (replayed sample events), or Frigate isn't running | For live events: `docker compose -f deploy/docker-compose.yml ps`; Frigate must be running |
| No alerts when sitting in front of the webcam | Frigate detects only when something **moves**, and rules fire on movement (crossing the line) | Walk across the frame left → right |
| Alerts show only as "Detection", no gate crossing | ibvap-core was started before the webcam camera was added to `rules.yaml` | Restart ibvap-core; `/health` should show the new `rules_version` |
| `error gathering device information while adding custom device "/dev/video0"` | No webcam on this machine | Remove the `devices:` lines under `mediamtx` (section 3) |
| MediaMTX logs show ffmpeg errors for `/dev/video0` | Webcam is busy in another app (video call, browser tab) | Close that app; `docker compose -f deploy/docker-compose.yml restart mediamtx` |
| Frigate keeps restarting / `no space left on device` | Disk full | `df -h /`; free space, or `docker system prune` to remove unused images |
| Frigate UI password lost | — | `docker compose -f deploy/docker-compose.yml logs frigate \| grep Password` (first start only), or reset it from the Frigate UI as another admin |
| Map shows markers but no background | No internet (OpenStreetMap tiles) | Expected offline; markers and alerts still work |

**Logs:**

```bash
docker compose -f deploy/docker-compose.yml logs -f frigate      # or mediamtx, mosquitto
```

ibvap-core logs print in its own terminal.

---

## 9. Reset demo data

Stop ibvap-core first.

```bash
rm -f ibvap-core/data/ibvap.db*                                       # IBVAP events and audit trail
docker compose -f deploy/docker-compose.yml down -v                   # also deletes Frigate's clips, snapshots, its database and the generated admin password
```

After `down -v`, Frigate generates a new admin password on its next start.

---

## Where to change things

| What | File |
|---|---|
| Cameras, detector, recording retention | [`frigate/config.yml`](frigate/config.yml) |
| Camera streams (webcam, looped test videos) | [`deploy/mediamtx/mediamtx.yml`](deploy/mediamtx/mediamtx.yml) |
| Zones, tripwires and border rules per camera | [`ibvap-core/config/rules.yaml`](ibvap-core/config/rules.yaml) |
| Camera names and map positions | [`ibvap-core/config/site.yaml`](ibvap-core/config/site.yaml) |
| Environment settings | `deploy/.env` (from [`deploy/.env.example`](deploy/.env.example)) |

To add a camera, follow the steps in [frigate/README.md](frigate/README.md#cameras).
