# frigate/ — Zone B: stream gateway and detection

[`config.yml`](config.yml) configures Frigate 0.18 (MIT). We run the official Docker image unmodified, and ibvap-core consumes Frigate's MQTT events (`frigate/events`) and HTTP API (snapshots and clips). No Frigate source code is copied into this repo.

| Setting | Value | Why |
|---|---|---|
| Detector | OpenVINO on CPU, SSDLite MobileNet v2 (bundled in the image) | Works on any x86 laptop or mini PC; measured 10 ms per frame on a Ryzen 5 7535HS |
| Objects | person, car, motorcycle, bus, truck, bicycle, dog, cow | People and vehicles for the rules; animals so they can be told apart (fewer false alarms) |
| Recording | Only around detections, kept 2 days; no continuous recording | Evidence for review with minimal retention |
| Snapshots | On, kept 2 days | Shown in the operator dashboard |
| Face recognition, LPR | Off | Privacy by default; ANPR is switched on in Phase 8 |

## Cameras

| Camera | Source | Notes |
|---|---|---|
| `cam-gate-west` | Laptop webcam → MediaMTX → `rtsp://mediamtx:8554/webcam` | Live demo camera. Walk across the frame left → right to cross the virtual gate line inbound |

To add a camera:
- **Real IP camera:** add an entry with its RTSP URL.
- **Test clip:** put the file in `samples/`, uncomment the matching path in [`deploy/mediamtx/mediamtx.yml`](../deploy/mediamtx/mediamtx.yml), and point a camera at `rtsp://mediamtx:8554/<path>`.

Then add the camera's zones and rules in [`ibvap-core/config/rules.yaml`](../ibvap-core/config/rules.yaml), and its name and map position in [`ibvap-core/config/site.yaml`](../ibvap-core/config/site.yaml).

## Frigate UI

Open http://127.0.0.1:8971 and log in as `admin`. On first start, Frigate prints a generated password:

```bash
docker compose -f deploy/docker-compose.yml logs frigate | grep Password
```

The internal API on port 5000 has no login. It is bound to 127.0.0.1, and only ibvap-core uses it.

## GPU (optional)

This laptop has an NVIDIA RTX 3050. To use it, install the NVIDIA Container Toolkit (needs admin rights), switch to the `-tensorrt` Frigate image and an ONNX model. The CPU detector is already well within the real-time budget for a few cameras.
