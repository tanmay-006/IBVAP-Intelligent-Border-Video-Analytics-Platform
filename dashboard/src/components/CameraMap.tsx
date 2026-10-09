import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef } from "react";
import { SEVERITY_LABEL, highestOpenSeverity, timeAgo } from "../alerts";
import type { Camera, IbvapEvent } from "../types";

// OpenStreetMap raster tiles need internet. Offline at the BOP the markers still
// show on the plain background, so the map never blocks the console.
const STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#1b2c33" } },
    {
      id: "osm",
      type: "raster",
      source: "osm",
      paint: { "raster-saturation": -0.7, "raster-brightness-max": 0.55, "raster-contrast": 0.1 },
    },
  ],
};

interface Props {
  cameras: Camera[];
  events: IbvapEvent[];
  selectedCamera: string | null;
  onSelectCamera: (id: string) => void;
  now: number;
}

export function CameraMap({ cameras, events, selectedCamera, onSelectCamera, now }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<Record<string, { marker: maplibregl.Marker; el: HTMLButtonElement }>>({});
  const placed = useMemo(() => cameras.filter((c) => c.lat !== null && c.lon !== null), [cameras]);
  const fitted = useRef(false);

  useEffect(() => {
    if (!container.current) return;
    map.current = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [84.85, 26.99],
      zoom: 14,
      attributionControl: { compact: true },
    });
    map.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    return () => {
      map.current?.remove();
      map.current = null;
      markers.current = {};
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    for (const cam of placed) {
      let entry = markers.current[cam.camera_id];
      if (!entry) {
        const el = document.createElement("button");
        el.className = "cam-marker";
        el.addEventListener("click", () => onSelectCamera(cam.camera_id));
        const marker = new maplibregl.Marker({ element: el }).setLngLat([cam.lon!, cam.lat!]).addTo(m);
        entry = markers.current[cam.camera_id] = { marker, el };
      }
      const sev = highestOpenSeverity(events, cam.camera_id);
      entry.el.className = `cam-marker ${sev ? `sev-${sev}` : "quiet"} ${
        selectedCamera === cam.camera_id ? "selected" : ""
      }`;
      entry.el.setAttribute(
        "aria-label",
        `${cam.name}: ${sev ? `${SEVERITY_LABEL[sev]} alert open` : "no open alerts"}`,
      );
      entry.el.title = cam.name;
    }
    if (!fitted.current && placed.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      placed.forEach((c) => bounds.extend([c.lon!, c.lat!]));
      m.fitBounds(bounds, { padding: 60, maxZoom: 16, duration: 0 });
      fitted.current = true;
    }
  }, [placed, events, selectedCamera, onSelectCamera]);

  return (
    <section className="map-pane" aria-label="Camera map">
      <div className="pane-head">
        <h2>Cameras</h2>
      </div>
      <div ref={container} className="map" />
      <ul className="cam-list">
        {cameras.map((c) => {
          const sev = highestOpenSeverity(events, c.camera_id);
          const open = events.filter(
            (e) => e.camera_id === c.camera_id && e.event_type !== "detection" && e.status !== "closed" && e.status !== "rejected",
          ).length;
          return (
            <li key={c.camera_id}>
              <button
                className={`cam-row ${sev ? `sev-${sev}` : ""}`}
                aria-pressed={selectedCamera === c.camera_id}
                onClick={() => onSelectCamera(c.camera_id)}
              >
                <span className="dot" aria-hidden="true" />
                <span className="cam-name">{c.name}</span>
                <span className="cam-meta">
                  {open > 0 ? `${open} open` : "Clear"}
                  {c.last_event_at ? `, last activity ${timeAgo(c.last_event_at, now)}` : ", no activity yet"}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
