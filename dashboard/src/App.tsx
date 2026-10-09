import { useCallback, useEffect, useMemo, useState } from "react";
import { buildQueue, isOpen, needsAttention } from "./alerts";
import { api } from "./api";
import { AlertDetail } from "./components/AlertDetail";
import { AlertQueue } from "./components/AlertQueue";
import { CameraMap } from "./components/CameraMap";
import { Header } from "./components/Header";
import { LiveView } from "./components/LiveView";
import { SearchView } from "./components/SearchView";
import { useTheme } from "./theme";
import type { Camera, Health, IbvapEvent } from "./types";
import { useAlertStream } from "./useAlertStream";

export function App() {
  const { events, status, fresh, merge } = useAlertStream();
  const { theme, toggle: toggleTheme } = useTheme();
  const [health, setHealth] = useState<Health | null>(null);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setViewState] = useState<"live" | "search">(() =>
    location.hash === "#search" ? "search" : "live",
  );
  const setView = (v: "live" | "search") => {
    setViewState(v);
    history.replaceState(null, "", v === "search" ? "#search" : location.pathname);
  };
  const [showDetections, setShowDetections] = useState(false);
  const [showClosed, setShowClosed] = useState(false);
  const [cameraFilter, setCameraFilter] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const poll = () => {
      api.health().then(setHealth).catch(() => setHealth(null));
      api.cameras().then(setCameras).catch(() => undefined);
    };
    poll();
    const t = setInterval(poll, 10000);
    const tick = setInterval(() => setNow(Date.now()), 15000);
    return () => {
      clearInterval(t);
      clearInterval(tick);
    };
  }, []);

  const all = useMemo(() => Object.values(events), [events]);
  const queue = useMemo(
    () => buildQueue(events, { showDetections, showClosed, cameraId: cameraFilter }),
    [events, showDetections, showClosed, cameraFilter],
  );
  const cameraById = useMemo(() => Object.fromEntries(cameras.map((c) => [c.camera_id, c])), [cameras]);

  const counts = useMemo(() => {
    const open = all.filter((e) => e.event_type !== "detection" && isOpen(e.status));
    return {
      critical: open.filter((e) => e.severity === "critical").length,
      high: open.filter((e) => e.severity === "high").length,
      waiting: open.filter((e) => needsAttention(e.status)).length,
    };
  }, [all]);

  // Keep the most severe alert in view until the operator picks one.
  useEffect(() => {
    if (!selectedId && queue.length > 0) setSelectedId(queue[0].event_id);
  }, [queue, selectedId]);

  const selectCamera = useCallback((id: string) => setCameraFilter((cur) => (cur === id ? null : id)), []);
  const openFromSearch = (e: IbvapEvent) => {
    merge([e]);
    setSelectedId(e.event_id);
    if (!isOpen(e.status)) setShowClosed(true);
    if (e.event_type === "detection") setShowDetections(true);
    setCameraFilter(null);
    setView("live");
  };

  const selected = selectedId ? events[selectedId] ?? null : null;
  // Live view follows the camera filter, else the selected alert's camera, else the first live camera.
  const liveCamera =
    (cameraFilter && cameraById[cameraFilter]) ||
    (selected && cameraById[selected.camera_id]) ||
    cameras.find((c) => c.live_url) ||
    undefined;

  return (
    <div className="app">
      <Header
        health={health}
        stream={status}
        counts={counts}
        view={view}
        onView={setView}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
      {view === "live" ? (
        <main className="live">
          <AlertQueue
            queue={queue}
            cameras={cameraById}
            selectedId={selectedId}
            fresh={fresh}
            onSelect={setSelectedId}
            showDetections={showDetections}
            showClosed={showClosed}
            cameraFilter={cameraFilter}
            onToggleDetections={() => setShowDetections((v) => !v)}
            onToggleClosed={() => setShowClosed((v) => !v)}
            onClearCamera={() => setCameraFilter(null)}
            now={now}
          />
          <AlertDetail
            event={selected}
            camera={selected ? cameraById[selected.camera_id] : undefined}
            onUpdated={(e) => merge([e])}
          />
          <aside className="side" aria-label="Cameras">
            <LiveView camera={liveCamera} />
            <CameraMap
              cameras={cameras}
              events={all}
              focusCamera={liveCamera?.camera_id ?? null}
              cameraFilter={cameraFilter}
              onSelectCamera={selectCamera}
              theme={theme}
              now={now}
            />
          </aside>
        </main>
      ) : (
        <main className="search-view">
          <SearchView cameras={cameras} onOpen={openFromSearch} />
        </main>
      )}
    </div>
  );
}
