import type { Camera } from "../types";

interface Props {
  camera: Camera | undefined;
}

export function LiveCamera({ camera }: Props) {
  if (!camera) {
    return (
      <section className="live-camera" aria-label="Live camera">
        <div className="pane-head">
          <h2>Live camera</h2>
        </div>
        <p className="empty">Select an alert to view its camera feed.</p>
      </section>
    );
  }

  const streamUrl = new URL(
    `/stream.html?src=${encodeURIComponent(camera.camera_id)}&mode=mse`,
    window.location.origin,
  );
  streamUrl.port = "1984";

  return (
    <section className="live-camera" aria-label={`Live camera: ${camera.name}`}>
      <div className="pane-head">
        <h2>Live camera</h2>
        <span className="camera-label">{camera.name}</span>
      </div>
      <iframe
        title={`Live feed from ${camera.name}`}
        src={streamUrl.toString()}
        allow="autoplay; fullscreen"
        loading="eager"
      />
      <p className="live-camera-note">Live stream from Frigate go2rtc</p>
    </section>
  );
}
