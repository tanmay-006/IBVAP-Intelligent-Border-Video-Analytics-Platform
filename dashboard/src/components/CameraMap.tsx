import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useMemo, useRef } from "react";
import { SEVERITY_LABEL, highestOpenSeverity, isOpen, timeAgo } from "../alerts";
import type { Theme } from "../theme";
import type { Camera, IbvapEvent } from "../types";

// OpenStreetMap raster tiles need internet. Offline at the BOP the markers still
// show on the plain background, so the map never blocks the console.
const PAINT: Record<Theme, { bg: string; saturation: number; brightness: number }> = {
  light: { bg: "#e9ebee", saturation: -0.6, brightness: 1 },
  dark: { bg: "#1b1e22", saturation: -0.8, brightness: 0.5 },
};

function style(theme: Theme): maplibregl.StyleSpecification {
  const p = PAINT[theme];
  return {
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
      { id: "bg", type: "background", paint: { "background-color": p.bg } },
      {
        id: "osm",
        type: "raster",
        source: "osm",
        paint: { "raster-saturation": p.saturation, "raster-brightness-max": p.brightness },
      },
    ],
  };
}

interface Props {
  cameras: Camera[];
  events: IbvapEvent[];
  focusCamera: string | null;
  cameraFilter: string | null;
  onSelectCamera: (id: string) => void;
  theme: Theme;
  now: number;
}

export function CameraMap({ cameras, events, focusCamera, cameraFilter, onSelectCamera, theme, now }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markers = useRef<Record<string, HTMLButtonElement>>({});
  const fitted = useRef(false);
  const placed = useMemo(() => cameras.filter((c) => c.lat !== null && c.lon !== null), [cameras]);

  useEffect(() => {
    if (!container.current) return;
    map.current = new maplibregl.Map({
      container: container.current,
      style: style(theme),
      center: [84.85, 26.99],
      zoom: 14,
      attributionControl: { compact: true },
    });
    map.current.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    return () => {
      map.current?.remove();
      map.current = null;
      markers.current = {};
      fitted.current = false;
    };
    // The map is created once; theme changes are applied below without rebuilding it.
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const apply = () => {
      const p = PAINT[theme];
      m.setPaintProperty("bg", "background-color", p.bg);
      m.setPaintProperty("osm", "raster-saturation", p.saturation);
      m.setPaintProperty("osm", "raster-brightness-max", p.brightness);
    };
    if (m.isStyleLoaded()) apply();
    else m.once("load", apply);
  }, [theme]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    for (const cam of placed) {
      let el = markers.current[cam.camera_id];
      if (!el) {
        el = document.createElement("button");
        el.addEventListener("click", () => onSelectCamera(cam.camera_id));
        new maplibregl.Marker({ element: el }).setLngLat([cam.lon!, cam.lat!]).addTo(m);
        markers.current[cam.camera_id] = el;
      }
      const sev = highestOpenSeverity(events, cam.camera_id);
      el.className = [
        "cam-marker",
        sev ? `sev-${sev}` : "quiet",
        focusCamera === cam.camera_id ? "focus" : "",
      ].join(" ");
      el.setAttribute("aria-label", `${cam.name}: ${sev ? `${SEVERITY_LABEL[sev]} alert open` : "no open alerts"}`);
      el.title = cam.name;
    }
    if (!fitted.current && placed.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      placed.forEach((c) => bounds.extend([c.lon!, c.lat!]));
      m.fitBounds(bounds, { padding: 48, maxZoom: 16, duration: 0 });
      fitted.current = true;
    }
  }, [placed, events, focusCamera, onSelectCamera]);

  return (
    <>
      <section className="card map-card" aria-label="Camera map">
        <div className="card-head">
          <h2>Map</h2>
        </div>
        <div ref={container} className="map" />
      </section>

      <section className="card" aria-label="Cameras">
        <div className="card-head">
          <h2>Cameras</h2>
          {cameraFilter && (
            <button className="text-button" onClick={() => onSelectCamera(cameraFilter)}>
              Show all
            </button>
          )}
        </div>
        <ul className="cam-list">
          {cameras.map((c) => {
            const sev = highestOpenSeverity(events, c.camera_id);
            const open = events.filter(
              (e) => e.camera_id === c.camera_id && e.event_type !== "detection" && isOpen(e.status),
            ).length;
            return (
              <li key={c.camera_id}>
                <button
                  className={`cam-row ${sev ? `sev-${sev}` : "quiet"}`}
                  aria-pressed={cameraFilter === c.camera_id}
                  onClick={() => onSelectCamera(c.camera_id)}
                >
                  <span className="dot" aria-hidden="true" />
                  <span className="cam-name">{c.name}</span>
                  <span className="cam-meta">
                    {open > 0 ? `${open} open` : "No open alerts"}
                    {c.last_event_at ? `, active ${timeAgo(c.last_event_at, now)}` : ", no activity yet"}
                    {c.live_url ? ", live view" : ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </section>
    </>
  );
}
