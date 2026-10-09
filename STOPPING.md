# Stopping IBVAP

How to stop IBVAP completely, stop one part, or remove it, and why closing the terminal is not enough.

## Why it keeps running after you close the terminal

| Part | What keeps it alive |
|---|---|
| Mosquitto, MediaMTX, Frigate (and ibvap-core, if started with `--profile core`) | These are Docker containers. The Docker service runs them, not your terminal. They are set to `restart: unless-stopped`, and Docker starts at boot, so they also **come back after a reboot** until you stop them yourself |
| ibvap-core started with `uv run uvicorn …` | If it was started in the background (`&`, `nohup`, an IDE task, an AI assistant) or its terminal window was closed without killing it, the process is handed over to the system and keeps running. Ctrl+C can no longer reach it |
| Dashboard dev server (`npm run dev`) | Same as above, if started in the background |

So stopping IBVAP takes two steps: stop the containers with Docker Compose, and kill any detached ibvap-core or dashboard process.

---

## Stop everything

Run from the repository folder:

```bash
cd ~/IBVAP-Intelligent-Border-Video-Analytics-Platform

# 1. Containers: Mosquitto, MediaMTX, Frigate, and ibvap-core if it runs in Docker
docker compose -f deploy/docker-compose.yml --profile core down

# 2. ibvap-core running outside Docker (port 8000)
pkill -f "uvicorn ibvap_core.api:create_app"

# 3. Dashboard dev server, if you used npm run dev (port 5173)
pkill -f "dashboard/node_modules/.bin/vite"

# 4. Brokers started with plain "docker run" by older instructions (harmless if none exist)
docker stop ibvap-mqtt 2>/dev/null
```

`down` removes the containers, so they **will not start again at boot**. Your data stays: Frigate's clips, snapshots and database live in Docker volumes, and IBVAP's events in `ibvap-core/data/ibvap.db`. To start again, follow [SETUP.md](SETUP.md#4-start-the-project).

### Check that it really stopped

```bash
docker ps --filter name=ibvap                                   # should list nothing
ss -ltnp | grep -E ':(1883|5000|5173|8000|8554|8971) '            # should print nothing
```

If a port is still in use, see [Something is still running](#something-is-still-running).

---

## Stop only one part

| To stop | Run | Start it again |
|---|---|---|
| ibvap-core in your terminal | Ctrl+C in that terminal | `cd ibvap-core && uv run uvicorn ibvap_core.api:create_app --factory --port 8000` |
| ibvap-core running detached | `pkill -f "uvicorn ibvap_core.api:create_app"` | same as above |
| Frigate only | `docker compose -f deploy/docker-compose.yml stop frigate` | `docker compose -f deploy/docker-compose.yml start frigate` |
| The webcam stream only | `docker compose -f deploy/docker-compose.yml stop mediamtx` | `docker compose -f deploy/docker-compose.yml start mediamtx` |
| All containers, keeping them for a quick restart | `docker compose -f deploy/docker-compose.yml stop` | `docker compose -f deploy/docker-compose.yml start` |

`stop` vs `down`:
- **`stop`** pauses the containers but keeps them. A container you stopped by hand does not restart at boot either.
- **`down`** removes the containers. The data volumes are kept unless you add `-v`.

Both are safe ways to end a session.

Stopping Frigate or MediaMTX turns the camera off; the webcam light goes out. ibvap-core keeps running and shows "Camera feed connected" as long as the broker is up.

---

## Something is still running

**Find what holds a port** (8000 shown here):

```bash
ss -ltnp | grep ':8000 '
# LISTEN ... users:(("uvicorn",pid=129591,fd=15))
kill 129591          # use the pid from your output
```

- If `ss` shows no process name, the port belongs to a Docker container: run `docker ps` and stop that container.
- If a process ignores `kill`, use `kill -9 <pid>` as a last resort.

**Find detached IBVAP processes:**

```bash
pgrep -af "uvicorn ibvap_core|publish_sample_events|dashboard/node_modules/.bin/vite"
```

**Find every IBVAP container,** including stopped ones and old names:

```bash
docker ps -a --filter name=ibvap
```

**The webcam light stays on:** MediaMTX is still running. Run `docker compose -f deploy/docker-compose.yml stop mediamtx`, or stop everything.

---

## Avoid detached processes

- Start ibvap-core in a terminal you keep open, in the foreground (no `&`), and stop it with Ctrl+C.
- Or run ibvap-core inside Docker as well, so one `down` stops everything:

  ```bash
  docker compose -f deploy/docker-compose.yml --profile core up -d --build
  docker compose -f deploy/docker-compose.yml --profile core down
  ```

---

## Remove IBVAP completely

To free the disk space (the Frigate image alone is about 8.6 GB) and delete all demo data:

```bash
cd ~/IBVAP-Intelligent-Border-Video-Analytics-Platform
docker compose -f deploy/docker-compose.yml --profile core down -v --rmi all   # containers, volumes (clips, snapshots, Frigate DB), images
pkill -f "uvicorn ibvap_core.api:create_app"
rm -f ibvap-core/data/ibvap.db*                                                # IBVAP events and audit trail
docker image prune                                                             # optional: other unused images
```

`-v` deletes Frigate's recordings, snapshots and its generated admin password. `--rmi all` means the next start downloads the images again.
