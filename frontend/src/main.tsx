import { useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { createRoot } from "react-dom/client";
import {
  Users,
  SquarePlay,
  Settings,
  Search,
  Bell,
  ChevronDown,
  Headphones,
  BatteryMedium,
  Signal,
  Mic,
  Maximize,
  Circle,
  VideoOff,
  Play,
  Pause,
  Download,
  X,
  LogOut,
  Volume2,
  VolumeX,
  RefreshCw,
} from "lucide-react";
import {
  api,
  auth,
  defaults,
  duration,
  initialize,
  listRecordings,
  repository,
  type BluetoothDevice,
  type BluetoothStatus,
  type Preferences,
  type RealStatus,
  type Recording,
  type Worker,
} from "./data";
import { LiveStream, Talkback, paintVideoFrames } from "./media";
import "./style.css";

type Page = "Live Workers" | "Recordings" | "Settings";
const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
const label = (worker: Worker) => `Worker #${worker.number} — ${worker.name}`;

function App() {
  const [signedIn, setSignedIn] = useState(auth.current);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [preferences, setPreferences] = useState(defaults);
  const [page, setPage] = useState<Page>("Live Workers");
  const [selectedId, setSelectedId] = useState("cam-007");
  const [search, setSearch] = useState("");
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [playback, setPlayback] = useState<Recording | null>(null);
  const [notice, setNotice] = useState("");
  const [recordingsError, setRecordingsError] = useState("");
  const [metadataWarnings, setMetadataWarnings] = useState<string[]>([]);
  const [maintenance, setMaintenance] = useState<RealStatus['maintenance']>(null);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [talking, setTalking] = useState(false);
  const [stoppingTalk, setStoppingTalk] = useState(false);
  const [recordStatusKnown, setRecordStatusKnown] = useState(false);
  const [recordFinalizing, setRecordFinalizing] = useState(false);
  const [rotation, setRotation] = useState(0);
  const [effectiveRotation, setEffectiveRotation] = useState(0);
  const [rotationKnown, setRotationKnown] = useState(false);
  const rotationRevision = useRef(0);
  const [playerSize, setPlayerSize] = useState({ width: 0, height: 0 });
  const wasFinalizing = useRef(false);
  const [headset, setHeadset] = useState<BluetoothStatus | null>(null);
  const [talkAvailable, setTalkAvailable] = useState(false);
  const [streamState, setStreamState] = useState("Connecting");
  const [micState, setMicState] = useState("Connecting");
  const [micRetry, setMicRetry] = useState(0);
  const [time, setTime] = useState(new Date());
  const [retry, setRetry] = useState(0);
  const [muted, setMuted] = useState(true);
  const [userMenu, setUserMenu] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const returnAudio = useRef<HTMLAudioElement>(null);
  const videoCard = useRef<HTMLDivElement>(null);
  const talkback = useRef<Talkback | null>(null);
  const talkPending = useRef(false);
  const talkStopping = useRef(false);
  const worker = workers.find((item) => item.id === selectedId);
  const real = worker?.mode === "real";

  useEffect(() => {
    initialize()
      .then((data) => {
        setWorkers(data.workers);
        setPreferences(data.preferences);
      })
      .catch((error) =>
        setLoadError(`Cannot open the local database: ${message(error)}`),
      );
  }, []);
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 6500);
    return () => clearTimeout(timer);
  }, [notice]);

  async function refresh() {
    const revision = rotationRevision.current;
    const local = await repository.list<Recording>("recordings");
    try {
      const remote = await listRecordings();
      setRecordings(
        [...remote, ...local].sort((a, b) =>
          b.createdAt.localeCompare(a.createdAt),
        ),
      );
      setRecordingsError("");
    } catch (error) {
      setRecordings(
        local.sort((a, b) => b.createdAt.localeCompare(a.createdAt)),
      );
      setRecordingsError(message(error));
    }
    const results = await Promise.allSettled([
      api<RealStatus>("/api/recordings/status"),
      api<BluetoothStatus>("/api/bluetooth/status"),
      api<{ available: boolean }>("/api/talkback/status"),
    ]);
    // A poll may wait on Bluetooth after it has read the old camera angle.
    // Do not let it overwrite a rotation saved while that poll was pending.
    const status = results[0];
    if (revision === rotationRevision.current) {
      setRecordStatusKnown(status.status === "fulfilled");
      setRotationKnown(status.status === "fulfilled" && [0, 90, 180, 270].includes(status.value.rotation));
      if (status.status === "fulfilled") {
        setMetadataWarnings(status.value.metadata_warnings ?? []);
        setMaintenance(status.value.maintenance ?? null);
        if ([0, 90, 180, 270].includes(status.value.rotation)) {
          setRotation(status.value.rotation);
          setEffectiveRotation(status.value.effective_rotation ?? status.value.rotation);
        }
        setRecordFinalizing(Boolean(status.value.finalizing));
        if (status.value.error) setNotice(status.value.error);
        else if (wasFinalizing.current && !status.value.recording) setNotice("MaixCAM recording saved.");
        wasFinalizing.current = Boolean(status.value.finalizing);
      }
      if (status.status === "fulfilled")
        setWorkers((items) =>
          items.map((item) =>
            item.mode === "real"
              ? { ...item, recording: status.value.recording }
              : item,
          ),
        );
    }
    setHeadset(results[1].status === "fulfilled" ? results[1].value : null);
    setTalkAvailable(
      results[2].status === "fulfilled" && results[2].value.available,
    );
  }
  useEffect(() => {
    if (!signedIn || !workers.length) return;
    void refresh().catch((error) => setNotice(message(error)));
    const timer = setInterval(() => {
      void refresh().catch((error) => setNotice(message(error)));
    }, 10000);
    return () => clearInterval(timer);
  }, [signedIn, workers.length]);

  useEffect(() => {
    const body = videoCard.current?.querySelector(".video-body");
    if (!body) return;
    const observer = new ResizeObserver(([entry]) => {
      setPlayerSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    observer.observe(body);
    return () => observer.disconnect();
  }, [signedIn, page, worker?.id]);

  async function rotateCamera(value: number) {
    if (busy) return;
    rotationRevision.current++;
    setBusy(true);
    try {
      const view = await api<{ rotation: number; effective_rotation?: number; metadata_warnings?: string[] }>("/api/camera/view", "POST", { rotation: value });
      setRotation(view.rotation);
      setEffectiveRotation(view.effective_rotation ?? view.rotation);
      setNotice("Camera rotation saved. New recordings will use this orientation.");
      setMetadataWarnings(view.metadata_warnings ?? []);
    } catch (error) {
      setNotice(message(error));
      await refresh();
    } finally {
      rotationRevision.current++;
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!signedIn || !worker || page !== "Live Workers" || !video.current)
      return;
    setMuted(true);
    if (worker.mode === "demo") {
      setStreamState("Demo");
      return;
    }
    const reader = new LiveStream(video.current, setStreamState);
    void reader.start(preferences.whep);
    return () => reader.stop();
  }, [signedIn, selectedId, page, preferences.whep, retry, workers.length]);

  useEffect(() => {
    if (!signedIn || !real || page !== "Live Workers" || !returnAudio.current) return;
    const reader = new LiveStream(returnAudio.current, setMicState, ["audio"]);
    const url = new URL(preferences.whep);
    url.pathname = "/headsetmic/whep";
    void reader.start(url.href);
    return () => reader.stop();
  }, [signedIn, selectedId, page, preferences.whep, micRetry, workers.length]);

  async function stopTalk() {
    talkPending.current = false;
    setTalking(false);
    const active = talkback.current;
    talkback.current = null;
    if (active) {
      talkStopping.current = true;
      setStoppingTalk(true);
      try {
        await active.stop();
      } finally {
        talkStopping.current = false;
        setStoppingTalk(false);
      }
    }
  }
  useEffect(() => {
    const stop = () => {
      void stopTalk();
    };
    const visibility = () => {
      if (document.hidden) stop();
    };
    window.addEventListener("blur", stop);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      stop();
      window.removeEventListener("blur", stop);
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [selectedId, page, signedIn]);

  async function startTalk() {
    if (talkPending.current || talkStopping.current) return;
    talkPending.current = true;
    if (!real) {
      setTalking(true);
      return;
    }
    const active = new Talkback((error) => {
      setNotice(error);
      setTalking(false);
      talkPending.current = false;
    });
    talkback.current = active;
    try {
      const started = await active.start();
      if (started && talkPending.current && talkback.current === active)
        setTalking(true);
    } catch (error) {
      setNotice(`Microphone: ${message(error)}`);
      await stopTalk();
    }
  }

  async function toggleRecording() {
    if (!worker || busy) return;
    setBusy(true);
    try {
      if (worker.mode === "real") {
        const result = await api<RealStatus>(
          `/api/recordings/${worker.recording ? "stop" : "start"}`,
          "POST",
        );
        setRotation(result.rotation);
        setEffectiveRotation(result.effective_rotation ?? result.rotation);
        setWorkers((items) =>
          items.map((item) =>
            item.id === worker.id
              ? { ...item, recording: result.recording }
              : item,
          ),
        );
        setNotice(
          result.error ? result.error : result.finalizing
            ? "Finalizing recording. Please wait before starting another."
            : result.recording
            ? "MaixCAM recording started."
            : "MaixCAM recording saved.",
        );
        await refresh();
      } else {
        const now = new Date();
        if (worker.recording) {
          const id = crypto.randomUUID();
          const createdAt = worker.startedAt || now.toISOString();
          await repository.put<Recording>("recordings", id, {
            id,
            worker: worker.name,
            createdAt,
            duration: Math.max(
              1,
              (now.getTime() - new Date(createdAt).getTime()) / 1000,
            ),
            filename: `${worker.id}_${createdAt.replace(/[:.]/g, "-")}.mp4`,
            url: preferences.demoVideo,
            source: "demo",
          });
        }
        const next = {
          ...worker,
          recording: !worker.recording,
          startedAt: worker.recording ? undefined : now.toISOString(),
        };
        await repository.put("workers", worker.id, next);
        setWorkers((items) =>
          items.map((item) => (item.id === worker.id ? next : item)),
        );
        await refresh();
        setNotice(
          next.recording ? "Demo recording started." : "Demo recording saved.",
        );
      }
    } catch (error) {
      setNotice(message(error));
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    void stopTalk();
    auth.logout();
    setSignedIn(false);
    setUserMenu(false);
    setPlayback(null);
    setPage("Live Workers");
  }
  if (!signedIn) return <Login onLogin={() => setSignedIn(true)} />;
  if (loadError)
    return (
      <div className="boot-error" role="alert">
        {loadError}
        <button onClick={() => location.reload()}>Retry</button>
      </div>
    );

  const online = !real || streamState === "Online";
  const connected = real ? headset?.connected : true;
  const filtered = workers.filter((item) =>
    `${label(item)} ${item.device} ${item.id}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const visibleRecordings = recordings.filter((item) =>
    `${item.worker} ${item.filename}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">WorkerCam Admin</div>
        <label className="search">
          <Search size={19} />
          <input
            aria-label="Search workers, devices"
            placeholder="Search workers, devices..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {search && (
            <button aria-label="Clear search" onClick={() => setSearch("")}>
              <X size={16} />
            </button>
          )}
        </label>
        <div className="account">
          <div className="popover-anchor">
            <button
              className="icon-button notification"
              aria-label="Notifications"
              aria-expanded={notifications}
              onClick={() => {
                setNotifications(!notifications);
                setUserMenu(false);
              }}
            >
              <Bell size={21} />
              <i />
            </button>
            {notifications && (
              <div className="popover">
                <strong>Notifications</strong>
                <p>No new notifications.</p>
              </div>
            )}
          </div>
          <div className="popover-anchor">
            <button
              className="user-button"
              aria-expanded={userMenu}
              onClick={() => {
                setUserMenu(!userMenu);
                setNotifications(false);
              }}
            >
              <span className="avatar">AD</span>
              <span>Admin</span>
              <ChevronDown size={16} />
            </button>
            {userMenu && (
              <div className="popover">
                <button onClick={logout}>
                  <LogOut size={17} />
                  Log out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <div className="layout">
        <aside className="sidebar">
          <nav aria-label="Main navigation">
            {(
              [
                { title: "Live Workers", icon: Users },
                { title: "Recordings", icon: SquarePlay },
                { title: "Settings", icon: Settings },
              ] as const
            ).map((item) => (
              <button
                key={item.title}
                className={page === item.title ? "nav-item active" : "nav-item"}
                aria-current={page === item.title ? "page" : undefined}
                onClick={() => setPage(item.title)}
              >
                <item.icon size={21} />
                {item.title}
              </button>
            ))}
          </nav>
          <div className="sidebar-footer">
            <span className="dot green" />
            WorkerCam workspace
            <span className="subtle">MaixCAM monitoring</span>
          </div>
        </aside>
        <main>
          {maintenance && (
            <div className="inline-message" role="status" aria-label="Maintenance active">
              <strong>Maintenance active. Recording is unavailable.</strong>
              <p>{maintenance.error ?? `Owner: ${maintenance.owner}. Wait for the operation to finish. If it crashed, follow owner-specific recovery in scripts/README.md.`}</p>
            </div>
          )}
          {metadataWarnings.length > 0 && (
            <div className="inline-message" role="status" aria-label="Metadata warnings">
              <strong>Optional metadata needs attention.</strong>
              {metadataWarnings.map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          )}
          {page === "Live Workers" && worker && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Live Workers</h1>
                  <p>Live camera feeds and device controls</p>
                </div>
                <span className="quiet-tag">{workers.length} workers</span>
              </div>
              <div className="dashboard">
                <section className="live-column">
                  <div className="worker-toolbar">
                    <label className="worker-select">
                      <Users size={18} />
                      <select
                        aria-label="Select worker"
                        value={
                          filtered.some((item) => item.id === selectedId)
                            ? selectedId
                            : ""
                        }
                        disabled={busy}
                        onChange={(event) => setSelectedId(event.target.value)}
                      >
                        {!filtered.some((item) => item.id === selectedId) && (
                          <option value="">
                            {filtered.length
                              ? "Select a worker"
                              : "No matching workers"}
                          </option>
                        )}
                        {filtered.map((item) => (
                          <option key={item.id} value={item.id}>
                            {label(item)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <span className="source-label">
                      {real ? "Physical MaixCAM" : "Demo camera"}
                    </span>
                  </div>
                  <div className="video-card" ref={videoCard}>
                    <div className="video-header">
                      <h2>
                        <span className={`dot ${online ? "green" : ""}`} />
                        {label(worker)}
                      </h2>
                      <div>
                        {online && (
                          <span className={real ? "live-badge" : "demo-badge"}>
                            {real ? "● LIVE" : "DEMO"}
                          </span>
                        )}
                        <time>{time.toLocaleTimeString("en-GB")}</time>
                      </div>
                    </div>
                    <div className="video-body">
                      <video
                        key={`${worker.id}-${retry}`}
                        ref={video}
                        className={real && effectiveRotation % 180 ? "canvas-source" : undefined}
                        data-rotation={real ? effectiveRotation : 0}
                        style={real ? {
                          width: effectiveRotation % 180 ? playerSize.height : "100%",
                          height: effectiveRotation % 180 ? playerSize.width : "100%",
                          transform: `translate(-50%, -50%) rotate(${-effectiveRotation}deg)`,
                        } : undefined}
                        src={real ? undefined : preferences.demoVideo}
                        autoPlay
                        playsInline
                        loop={!real}
                        muted={real || muted}
                        onError={() => {
                          if (!real) setStreamState("Demo video unavailable");
                        }}
                      />
                      {real && effectiveRotation % 180 !== 0 && <VideoPicture
                        key={`picture-${worker.id}-${retry}`} source={video} rotation={effectiveRotation} />}
                      {real && <audio ref={returnAudio} autoPlay muted={muted} />}
                      {!online || streamState === "Demo video unavailable" ? (
                        <div className="video-empty">
                          <VideoOff size={38} />
                          <h3>
                            {streamState === "Connecting"
                              ? "Connecting to MaixCAM"
                              : "Camera feed unavailable"}
                          </h3>
                          <p>
                            {streamState === "Connecting"
                              ? "Waiting for the live video stream…"
                              : streamState}
                          </p>
                          <button
                            onClick={() => setRetry((value) => value + 1)}
                          >
                            <RefreshCw size={16} />
                            Reconnect
                          </button>
                        </div>
                      ) : null}
                      <button
                        className="fullscreen"
                        aria-label="Fullscreen video"
                        onClick={() => {
                          const action = document.fullscreenElement
                            ? document.exitFullscreen()
                            : videoCard.current?.requestFullscreen();
                          void action?.catch((error) =>
                            setNotice(message(error)),
                          );
                        }}
                      >
                        <Maximize size={20} />
                      </button>
                    </div>
                  </div>
                  <div className="video-caption">
                    <span>
                      {worker.device} <span className="caption-divider">/</span>{" "}
                      {real ? "MediaMTX live stream" : "Demonstration stream"}
                    </span>
                    <button
                      className="text-button"
                      onClick={() => {
                        setMuted(!muted);
                        const element = real ? returnAudio.current : video.current;
                        if (element) element.muted = !muted;
                        void element
                          ?.play()
                          .catch((error) => setNotice(message(error)));
                      }}
                    >
                      {muted ? <VolumeX size={17} /> : <Volume2 size={17} />}{" "}
                      {muted ? "Enable audio" : "Mute audio"}
                    </button>
                  </div>
                  {real && <div className="video-caption">
                    <span>Earbuds microphone: {micState}{muted ? " · Muted" : ""}</span>
                    <button className="text-button" onClick={() => setMicRetry((value) => value + 1)}>
                      <RefreshCw size={16} /> Reconnect microphone
                    </button>
                  </div>}
                  {real && <div className="video-caption camera-rotation">
                    <label htmlFor="camera-rotation">Camera rotation</label>
                    <select id="camera-rotation" value={rotation}
                      disabled={busy || !rotationKnown || !recordStatusKnown || worker.recording || recordFinalizing}
                      onChange={(event) => void rotateCamera(Number(event.target.value))}>
                      <option value={0}>Original (0°)</option>
                      <option value={90}>90° counter-clockwise</option>
                      <option value={180}>180°</option>
                      <option value={270}>90° clockwise</option>
                    </select>
                    {(worker.recording || recordFinalizing) && <span>Stop recording to rotate</span>}
                  </div>}
                </section>
                <aside className="status-column">
                  <section className="card">
                    <h2>Device Status</h2>
                    <div className="status-rows">
                      <StatusRow
                        icon={
                          <span className={`dot ${online ? "green" : ""}`} />
                        }
                        label="Device"
                        value={real ? (online ? "Online" : "Offline") : "Demo"}
                        healthy={online}
                      />
                      {real && <StatusRow icon={<Signal />} label="Media transport"
                        value={online ? "WebRTC / UDP" : "Unverified"} healthy={online} />}
                      <StatusRow
                        icon={
                          <span
                            className={`dot ${worker.recording ? "red" : ""}`}
                          />
                        }
                        label="Recording"
                        value={
                          real && !recordStatusKnown
                            ? "Unknown"
                            : worker.recording
                              ? "On"
                              : "Off"
                        }
                        healthy={
                          worker.recording && (!real || recordStatusKnown)
                        }
                      />
                      <StatusRow
                        icon={<Headphones />}
                        label="Headset"
                        value={
                          connected
                            ? "Connected"
                            : headset
                              ? "Disconnected"
                              : "Unknown"
                        }
                        healthy={!!connected}
                      />
                      <StatusRow
                        icon={
                          <BatteryMedium
                            className={worker.battery !== null ? "healthy" : ""}
                          />
                        }
                        label="Battery"
                        value={
                          worker.battery === null ? "—" : `${worker.battery}%`
                        }
                      />
                      <StatusRow
                        icon={<Signal className={!real ? "healthy" : ""} />}
                        label="Signal"
                        value={worker.signal}
                      />
                      <StatusRow
                        icon={<Mic />}
                        label="Microphone"
                        value={real ? "Unknown" : "On"}
                        healthy={!real}
                      />
                    </div>
                  </section>
                  <section className="card actions">
                    <h2>Actions</h2>
                    <div className="action-buttons">
                      <button
                        className={`primary ${talking ? "talking" : ""}`}
                        disabled={stoppingTalk || (real && !talkAvailable)}
                        onPointerDown={(event) => {
                          event.currentTarget.setPointerCapture(
                            event.pointerId,
                          );
                          void startTalk();
                        }}
                        onPointerUp={() => void stopTalk()}
                        onPointerCancel={() => void stopTalk()}
                        onKeyDown={(event) => {
                          if ([" ", "Enter"].includes(event.key)) {
                            event.preventDefault();
                            void startTalk();
                          }
                        }}
                        onKeyUp={(event) => {
                          if ([" ", "Enter"].includes(event.key)) {
                            event.preventDefault();
                            void stopTalk();
                          }
                        }}
                        aria-pressed={talking}
                      >
                        <Mic size={19} />
                        {talking ? "Talking..." : "Talk"}
                      </button>
                      <button
                        className={
                          worker.recording
                            ? "record-button recording"
                            : "record-button"
                        }
                        disabled={
                          (real && recordFinalizing) ||
                          busy ||
                          (real &&
                            (!recordStatusKnown || !rotationKnown ||
                              Boolean(maintenance) || (!online && !worker.recording)))
                        }
                        onClick={() => void toggleRecording()}
                      >
                        <Circle size={13} fill="currentColor" />
                        {busy
                          ? "Saving..."
                          : real && recordFinalizing
                            ? "Finalizing..."
                          : worker.recording
                            ? "Stop Recording"
                            : "Record"}
                      </button>
                    </div>
                    <p className="action-hint">
                      {real && !talkAvailable
                        ? "Talkback unavailable. Check the PC server."
                        : "Hold Talk to speak. Release to stop."}
                    </p>
                    {real && <EarbudVolume key={worker.id} notify={setNotice} />}
                  </section>
                </aside>
              </div>
            </>
          )}
          {page === "Recordings" && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Recordings</h1>
                  <p>Saved worker camera recordings</p>
                </div>
                <button
                  className="outline"
                  onClick={() =>
                    void refresh().catch((error) => setNotice(message(error)))
                  }
                >
                  <RefreshCw size={16} />
                  Refresh
                </button>
              </div>
              {recordingsError && (
                <div className="inline-message" role="status">
                  {recordingsError} Local demo recordings are still available.
                </div>
              )}
              <div className="card table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Worker</th>
                      <th>Start Time</th>
                      <th>Duration</th>
                      <th>Filename</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRecordings.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <strong>{item.worker}</strong>
                          <span className="table-sub">
                            {item.source === "real" ? "MaixCAM" : "Demo"}
                          </span>
                        </td>
                        <td>
                          {new Date(item.createdAt).toLocaleTimeString("en-GB")}
                          <span className="table-sub">
                            {new Date(item.createdAt).toLocaleDateString()}
                          </span>
                        </td>
                        <td>
                          {item.active ? "Recording…" : duration(item.duration)}
                        </td>
                        <td className="filename">{item.filename}</td>
                        <td>
                          <div className="table-actions">
                            <button
                              className="text-button"
                              disabled={item.active}
                              onClick={() => setPlayback(item)}
                            >
                              <Play size={15} />
                              Play
                            </button>
                            <button
                              className="text-button neutral"
                              disabled={item.active}
                              onClick={() =>
                                void download(item).catch((error) =>
                                  setNotice(message(error)),
                                )
                              }
                            >
                              <Download size={15} />
                              Download
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {!visibleRecordings.length && (
                      <tr>
                        <td colSpan={5} className="empty-table">
                          {search
                            ? "No recordings match your search."
                            : "No saved recordings yet. Start and stop a recording in Live Workers."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
          {page === "Settings" && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Settings</h1>
                  <p>Workspace and camera connection</p>
                </div>
              </div>
              <section className="card settings-summary">
                <h2>Prototype Settings</h2>
                <div className="settings-row">
                  <span>Demo Mode</span>
                  <span>Worker #12 only</span>
                </div>
                <div className="settings-row">
                  <span>Backend</span>
                  <span>WorkerCam Backend</span>
                </div>
                <div className="settings-row">
                  <span>Environment</span>
                  <span>Prototype</span>
                </div>
                <div className="settings-row">
                  <span>Database</span>
                  <span>Local browser database (IndexedDB)</span>
                </div>
                <div className="settings-row">
                  <span>Authentication</span>
                  <span>Local demo session</span>
                </div>
              </section>
              <ConnectionSettings
                preferences={preferences}
                onSave={async (next) => {
                  await repository.put("preferences", "default", next);
                  setPreferences(next);
                  setNotice("Connection settings saved.");
                }}
                notify={setNotice}
                headset={headset}
                onHeadset={setHeadset}
              />
              <button className="outline logout" onClick={logout}>
                <LogOut size={17} />
                Log out
              </button>
            </>
          )}
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          {notice}
          <button aria-label="Dismiss message" onClick={() => setNotice("")}>
            <X size={16} />
          </button>
        </div>
      )}
      {playback && (
        <Playback recording={playback} onClose={() => setPlayback(null)} />
      )}
    </div>
  );
}

function StatusRow({
  icon,
  label,
  value,
  healthy = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  healthy?: boolean;
}) {
  return (
    <div className="status-row">
      <span className="status-icon">{icon}</span>
      <span>{label}</span>
      <strong className={healthy ? "healthy" : ""}>{value}</strong>
    </div>
  );
}
function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await auth.login(username.trim(), password);
      onLogin();
    } catch (error) {
      setError(message(error));
    }
  }
  return (
    <main className="login-screen">
      <form className="login-card" onSubmit={submit}>
        <h1>WorkerCam Admin</h1>
        <p>Admin Login</p>
        <label>
          Username
          <input
            name="username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
        </label>
        <label>
          Password
          <input
            name="password"
            type="password"
            placeholder="Enter your password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && (
          <div className="login-error" role="alert">
            {error}
          </div>
        )}
        <button className="primary" type="submit">
          Sign In
        </button>
        <div className="login-note">
          Demo credentials: admin / admin
          <br />
          Local prototype login
        </div>
      </form>
    </main>
  );
}
function VideoPicture({ source, rotation = 0 }: {
  source: RefObject<HTMLVideoElement | null>;
  rotation?: number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (source.current && canvas.current)
      return paintVideoFrames(source.current, canvas.current, rotation);
  }, [source, rotation]);
  return <canvas ref={canvas} className="video-picture" aria-label="Video picture" role="img" />;
}

function Playback({
  recording,
  onClose,
}: {
  recording: Recording;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const player = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [portrait, setPortrait] = useState(false);
  const [paused, setPaused] = useState(false);
  const [position, setPosition] = useState(0);
  const [length, setLength] = useState(recording.duration ?? 0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      className="playback"
      ref={dialog}
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === dialog.current) onClose();
      }}
    >
      <div className="modal-header">
        <div>
          <h2>{recording.filename}</h2>
          <p>
            {recording.worker} ·{" "}
            {recording.source === "demo" ? "Demo playback" : "Camera recording"}
          </p>
        </div>
        <button
          className="icon-button"
          aria-label="Close recording"
          onClick={onClose}
        >
          <X />
        </button>
      </div>
      <div className="recording-player" ref={player}>
        <div className="playback-picture">
          <video ref={video} src={recording.url} controls={!portrait} autoPlay playsInline
            className={portrait ? "canvas-source" : undefined}
            onLoadedMetadata={(event) => {
              const media = event.currentTarget;
              setPortrait(media.videoHeight > media.videoWidth);
              if (Number.isFinite(media.duration)) setLength(media.duration);
            }}
            onPlay={() => setPaused(false)} onPause={() => setPaused(true)}
            onEnded={() => setPaused(true)}
            onTimeUpdate={(event) => setPosition(event.currentTarget.currentTime)}
            onVolumeChange={(event) => {
              setVolume(event.currentTarget.volume);
              setMuted(event.currentTarget.muted);
            }}
            onError={() => setError("This recording could not be played.")} />
          {portrait && <VideoPicture source={video} />}
        </div>
        {portrait && <div className="recording-controls">
          <button aria-label={paused ? "Play recording" : "Pause recording"}
            onClick={() => {
              const media = video.current;
              if (!media) return;
              if (media.paused) void media.play().catch((error) => setError(message(error)));
              else media.pause();
            }}>{paused ? <Play size={19} /> : <Pause size={19} />}</button>
          <span>{duration(position)} / {duration(length)}</span>
          <input aria-label="Recording position" type="range" min={0} max={length || 1}
            step={0.01} value={position} onInput={(event) => {
              const next = Number(event.currentTarget.value);
              setPosition(next);
              if (video.current) video.current.currentTime = next;
            }} />
          <button aria-label={muted ? "Unmute recording" : "Mute recording"}
            onClick={() => { if (video.current) video.current.muted = !video.current.muted; }}>
            {muted || !volume ? <VolumeX size={19} /> : <Volume2 size={19} />}
          </button>
          <input aria-label="Recording volume" type="range" min={0} max={1} step={0.05}
            value={muted ? 0 : volume} onInput={(event) => {
              if (video.current) {
                video.current.volume = Number(event.currentTarget.value);
                video.current.muted = false;
              }
            }} />
          <button aria-label="Fullscreen recording" onClick={() => {
            const action = document.fullscreenElement ? document.exitFullscreen() : player.current?.requestFullscreen();
            void action?.catch((error) => setError(message(error)));
          }}><Maximize size={19} /></button>
        </div>}
      </div>
      {error && <p className="modal-note" role="alert">{error}</p>}
      <p className="modal-note">
        {recording.source === "demo"
          ? "Demo records replay the demonstration clip."
          : "Recorded on the physical MaixCAM."}
      </p>
    </dialog>
  );
}
async function download(recording: Recording) {
  let url = recording.url;
  if (recording.source === "demo") {
    const response = await fetch(url);
    if (!response.ok) throw new Error("Recording download failed.");
    url = URL.createObjectURL(await response.blob());
  }
  const link = document.createElement("a");
  link.href = url;
  link.download = recording.filename;
  link.click();
  if (recording.source === "demo")
    setTimeout(() => URL.revokeObjectURL(url), 10000);
}
function EarbudVolume({ notify }: { notify: (value: string) => void }) {
  const [earbudVolume, setEarbudVolume] = useState<number | null>(null);
  const [volumeBusy, setVolumeBusy] = useState(false);
  const [volumeError, setVolumeError] = useState("");
  useEffect(() => {
    let active = true;
    setEarbudVolume(null);
    setVolumeError("");
    void api<{ volume: number }>("/api/bluetooth/volume").then((result) => {
      if (active) setEarbudVolume(result.volume);
    }).catch((error) => { if (active) setVolumeError(message(error)); });
    return () => { active = false; };
  }, []);
  async function saveEarbudVolume() {
    if (earbudVolume === null) return;
    setVolumeBusy(true);
    setVolumeError("");
    try {
      const result = await api<{ volume: number }>("/api/bluetooth/volume", "POST", { volume: earbudVolume });
      setEarbudVolume(result.volume);
      notify(`Earbud playback volume set to ${result.volume}%.`);
    } catch (error) { setVolumeError(message(error)); }
    finally { setVolumeBusy(false); }
  }
  return (
    <div className="earbud-volume">
        <label>
          Earbud playback volume: {earbudVolume === null ? "Unavailable" : `${earbudVolume}%`}
          <input aria-label="Earbud playback volume" type="range" min="0" max="100" step="1"
            value={earbudVolume ?? 0} disabled={earbudVolume === null || volumeBusy}
            onChange={(event) => setEarbudVolume(Number(event.target.value))} />
        </label>
        <button className="outline" disabled={earbudVolume === null || volumeBusy}
          onClick={() => void saveEarbudVolume()}>
          {volumeBusy ? "Applying…" : "Apply earbud volume"}
        </button>
        <p>Controls sound from Talk in the camera earbuds, not microphone input or laptop speaker volume.</p>
        {volumeError && <p role="status">{volumeError}</p>}
    </div>
  );
}

function ConnectionSettings({
  preferences,
  onSave,
  notify,
  headset,
  onHeadset,
}: {
  preferences: Preferences;
  onSave: (value: Preferences) => Promise<void>;
  notify: (value: string) => void;
  headset: BluetoothStatus | null;
  onHeadset: (value: BluetoothStatus) => void;
}) {
  const [whep, setWhep] = useState(preferences.whep);
  const [demoVideo, setDemoVideo] = useState(
    preferences.demoVideo === defaults.demoVideo ? "" : preferences.demoVideo,
  );
  const [devices, setDevices] = useState<BluetoothDevice[]>([]);
  const [mac, setMac] = useState("");
  const [busy, setBusy] = useState(false);
  const [diagnosing, setDiagnosing] = useState(false);
  const [diagnosis, setDiagnosis] = useState<{
    message: string;
    wifi: { ip: string; reachable: boolean; tcp_services: Record<string, boolean> };
    usb: { ip: string; reachable: boolean; tcp_services: Record<string, boolean> } | null;
    usb_ip: string | null;
  } | null>(null);
  async function diagnose() {
    setDiagnosing(true);
    try { setDiagnosis(await api("/api/camera/diagnostics")); }
    catch (error) { notify(message(error)); }
    finally { setDiagnosing(false); }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      for (const url of [whep, ...(demoVideo ? [demoVideo] : [])]) {
        if (!["http:", "https:"].includes(new URL(url).protocol))
          throw new Error("Use an HTTP or HTTPS media URL.");
      }
      await onSave({ whep, demoVideo: demoVideo || defaults.demoVideo });
    } catch (error) {
      notify(message(error));
    }
  }
  async function bluetooth(action: "scan" | "select") {
    setBusy(true);
    try {
      const result = await api<
        BluetoothStatus & { devices?: BluetoothDevice[] }
      >(
        `/api/bluetooth/${action}`,
        "POST",
        action === "select" ? { mac } : undefined,
      );
      onHeadset(result);
      if (result.devices) {
        setDevices(result.devices);
        setMac(result.devices[0]?.mac || "");
      }
      notify(
        action === "scan"
          ? `${result.devices?.length || 0} headsets found.`
          : "Headset connected.",
      );
    } catch (error) {
      notify(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card connection-settings">
      <h2>Camera Connection</h2>
      <form onSubmit={save}>
        <label>
          MaixCAM stream (WHEP)
          <input
            type="url"
            value={whep}
            onChange={(event) => setWhep(event.target.value)}
            required
          />
        </label>
        <label>
          Demo video URL
          <input
            type="url"
            value={demoVideo}
            placeholder="Built-in warehouse demo (optional custom URL)"
            onChange={(event) => setDemoVideo(event.target.value)}
          />
        </label>
        <button className="primary" type="submit">
          Save connection
        </button>
      </form>
      <div className="headset-settings">
        <h3>Camera Diagnostics</h3>
        <p>Check camera services over Wi-Fi, then USB if Wi-Fi services are unreachable.</p>
        <button className="outline" disabled={diagnosing} onClick={() => void diagnose()}>
          {diagnosing ? "Checking camera…" : "Diagnose camera"}
        </button>
        {diagnosis && <div role="status">
          <p>{diagnosis.message}</p>
          <p>Wi-Fi: {diagnosis.wifi.ip} · USB: {diagnosis.usb_ip || "Not configured"}</p>
          {[diagnosis.wifi, diagnosis.usb].filter((link) => link !== null).map((link) =>
            <p key={link.ip}>{link.ip}: SSH {link.tcp_services.ssh ? "reachable" : "unreachable"},
              RTSP control {link.tcp_services.rtsp_control ? "reachable" : "unreachable"},
              Bluetooth control {link.tcp_services.bluetooth_control ? "reachable" : "unreachable"}</p>
          )}
        </div>}
      </div>
      <div className="headset-settings">
        <h3>MaixCAM Earbuds</h3>
        <p>
          {headset?.selected
            ? `${headset.connected ? "Connected" : "Disconnected"} · ${headset.selected}`
            : "Put your headset in pairing mode, then scan and connect."}
        </p>
        {headset?.fixed ? (
          <p>These earbuds are bound to MaixCAM and reconnect automatically.</p>
        ) : <div className="headset-controls">
          <button
            className="outline"
            disabled={busy}
            onClick={() => void bluetooth("scan")}
          >
            {busy ? "Working…" : "Scan"}
          </button>
          <select
            aria-label="Bluetooth headset"
            value={mac}
            onChange={(event) => setMac(event.target.value)}
            disabled={!devices.length || busy}
          >
            <option value="">Select headset</option>
            {devices.map((item) => (
              <option key={item.mac} value={item.mac}>
                {item.name} ({item.mac})
              </option>
            ))}
          </select>
          <button
            className="outline"
            disabled={!mac || busy}
            onClick={() => void bluetooth("select")}
          >
            Connect
          </button>
        </div>}

      </div>
    </section>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
