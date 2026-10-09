import type { Camera } from "../types";

interface Props {
  camera: Camera | undefined;
}

/** Live picture from Frigate's go2rtc (WebRTC, MSE fallback) for the camera in focus. */
export function LiveView({ camera }: Props) {
  return (
    <section className="card live-view" aria-label="Live view">
      <div className="card-head">
        <h2>Live view</h2>
        {camera && <span className="card-meta">{camera.name}</span>}
      </div>
      {camera?.live_url ? (
        <div className="video-frame">
          <iframe
            key={camera.live_url}
            title={`Live view of ${camera.name}`}
            src={camera.live_url}
            allow="autoplay; fullscreen"
          />
        </div>
      ) : (
        <p className="media-empty">
          {camera
            ? `No live stream is set up for ${camera.name}.`
            : "Select an alert or a camera to watch it live."}
        </p>
      )}
    </section>
  );
}
