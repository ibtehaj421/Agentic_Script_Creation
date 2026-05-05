import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

const API = ""; // same-origin
const WS = (job) => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/progress/${job}`;
};

function StatusPill({ status }) {
  return <span className={`status-pill ${status}`}>{status}</span>;
}

function PhaseRow({ name, status }) {
  return (
    <div className="phase-row">
      <span className="phase-name">{name}</span>
      <StatusPill status={status || "pending"} />
    </div>
  );
}

function PromptForm({ onSubmit, disabled }) {
  const [prompt, setPrompt] = useState("A young astronaut discovers a hidden ocean on Mars and uncovers an ancient intelligence.");
  const [numScenes, setNumScenes] = useState(3);
  const [style, setStyle] = useState("cinematic");
  return (
    <div className="form-block">
      <label>Prompt</label>
      <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} />
      <div className="row">
        <div>
          <label>Scenes</label>
          <input
            type="number" min="1" max="8"
            value={numScenes}
            onChange={(e) => setNumScenes(Number(e.target.value))}
          />
        </div>
        <div>
          <label>Style</label>
          <select value={style} onChange={(e) => setStyle(e.target.value)}>
            <option>cinematic</option>
            <option>anime</option>
            <option>noir</option>
            <option>cyberpunk</option>
            <option>photorealistic</option>
            <option>watercolor</option>
          </select>
        </div>
      </div>
      <button
        className="btn"
        disabled={disabled || !prompt.trim()}
        onClick={() => onSubmit({ prompt, num_scenes: numScenes, style })}
      >
        ▶ Generate video
      </button>
    </div>
  );
}

function JobResumePicker({ currentJobId, onPick }) {
  const [jobs, setJobs] = useState([]);
  useEffect(() => {
    fetch(`${API}/api/jobs`)
      .then((r) => (r.ok ? r.json() : []))
      .then(setJobs)
      .catch(() => setJobs([]));
  }, [currentJobId]);
  if (!jobs.length) return null;
  return (
    <div className="form-block" style={{ marginTop: 8 }}>
      <label>Or resume a previous job</label>
      <select
        value={currentJobId || ""}
        onChange={(e) => e.target.value && onPick(e.target.value)}
      >
        <option value="">— pick one —</option>
        {jobs.map((j) => (
          <option key={j.job_id} value={j.job_id}>
            {j.title || "(untitled)"} · {j.job_id} · v{j.latest_version}
          </option>
        ))}
      </select>
    </div>
  );
}

function EventStream({ events }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events]);
  return (
    <div className="events" ref={ref}>
      {events.length === 0
        ? <div style={{ color: "var(--muted)" }}>waiting for pipeline events…</div>
        : events.slice(-200).map((e, i) => (
          <div key={i}><b>[{e.phase}]</b> {e.event} {e.data && Object.keys(e.data).length ? JSON.stringify(e.data).slice(0, 120) : ""}</div>
        ))}
    </div>
  );
}

function Scenes({ outputs, bust = 0 }) {
  if (!outputs || !outputs.scenes) return null;
  return (
    <div className="scene-grid">
      {Object.entries(outputs.scenes).map(([id, s]) => (
        // `key` includes bust so an explicit edit / undo / restore
        // remounts the tile (forcing a fresh fetch). Bust only changes
        // on user actions, so this doesn't loop.
        <div className="scene-tile" key={`${id}-${bust}`}>
          {s.composed ? (
            <video src={`${s.composed}?b=${bust}`} controls muted />
          ) : s.background ? (
            <img src={`${s.background}?b=${bust}`} alt={`scene ${id}`} />
          ) : null}
          <div className="meta">Scene {id}</div>
        </div>
      ))}
    </div>
  );
}

function CharactersRow({ outputs }) {
  if (!outputs || !outputs.character_portraits) return null;
  const entries = Object.entries(outputs.character_portraits);
  if (!entries.length) return null;
  return (
    <div className="chip-row" style={{ gap: 14 }}>
      {entries.map(([name, path]) => (
        <div key={name} style={{ textAlign: "center" }}>
          <img src={path} alt={name} style={{ width: 68, height: 68, borderRadius: "50%", objectFit: "cover", border: "1px solid var(--border)" }} />
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4 }}>{name}</div>
        </div>
      ))}
    </div>
  );
}

function _lineage(versions, target) {
  // Walk parent_version pointers from `target` (a version number) back
  // to the root. Returns child→parent ordered list.
  const byVer = new Map(versions.map((v) => [v.version, v]));
  const chain = [];
  const seen = new Set();
  let cur = target;
  while (cur != null && !seen.has(cur)) {
    chain.push(cur);
    seen.add(cur);
    const row = byVer.get(cur);
    cur = row && row.parent_version != null ? row.parent_version : null;
  }
  return chain;
}

function VersionPanel({ jobId, versions, refresh, onUndo, onRestore }) {
  if (!jobId) return <div className="empty">Start a job to see versions.</div>;
  const active = versions.find((v) => v.is_active);
  const canUndo = active && active.parent_version != null;
  return (
    <div>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className="btn small warn" onClick={onUndo} disabled={!canUndo}>↶ Undo last</button>
        <button className="btn small secondary" onClick={refresh}>⟳</button>
      </div>
      <div className="versions-list">
        {versions.length === 0 && <div className="empty">no versions yet</div>}
        {versions.slice().reverse().map((v) => {
          const isActive = !!v.is_active;
          const chain = _lineage(versions, v.version);
          // Tooltip shows the lineage chain (current → parent → ... → root).
          const lineageText = chain.length > 1
            ? `lineage: ${chain.map((n) => "v" + n).join(" → ")}`
            : `root version`;
          return (
            <div
              className={"version-row" + (isActive ? " active" : "")}
              key={v.version}
              title={lineageText}
              style={isActive ? {
                borderColor: "var(--accent, #5b8def)",
                background: "rgba(91,141,239,0.08)",
              } : undefined}
            >
              <div>
                <div className="v-num">
                  v{v.version}
                  {isActive && <span style={{ color: "var(--accent, #5b8def)", marginLeft: 6, fontSize: 11 }}>● active</span>}
                  {v.parent_version != null && (
                    <span style={{ color: "var(--muted)", marginLeft: 6, fontSize: 10 }}>
                      ← v{v.parent_version}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                  [{v.triggered_by}] {v.change_summary || v.changed_phase || "pipeline"}
                </div>
              </div>
              {!isActive && (
                <button className="btn small secondary" onClick={() => onRestore(v.version)}>Restore</button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EditPanel({ jobId, busy, onEdit, chatLog }) {
  const [q, setQ] = useState("");
  return (
    <div>
      <div className="edit-chat">
        {chatLog.length === 0 && <div className="empty">Try: "make scene 2 darker", "change voice to whispered", "apply cyberpunk filter"</div>}
        {chatLog.map((m, i) => (
          <div key={i} className={`edit-bubble ${m.role}`}>
            {m.role === "agent" && m.intent
              ? <><b>{m.intent.intent}</b> → target={m.intent.target}, scope={m.intent.scope || "global"} (conf={m.intent.confidence?.toFixed(2)})<br/>{m.message}</>
              : m.text}
          </div>
        ))}
      </div>
      <div style={{ marginTop: 12 }}>
        <textarea
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Describe your edit…"
          disabled={!jobId || busy}
        />
        <div className="row" style={{ marginTop: 6 }}>
          <button
            className="btn small"
            disabled={!jobId || busy || !q.trim()}
            onClick={() => { onEdit(q); setQ(""); }}
          >Send edit</button>
        </div>
      </div>
    </div>
  );
}

function App() {
  // Persist the active jobId across page refreshes so we don't lose the
  // session (and the version-history with its edit results) on a reload.
  const [jobId, setJobId] = useState(() => {
    try { return localStorage.getItem("agentic_jobId"); } catch { return null; }
  });
  const [events, setEvents] = useState([]);
  const [state, setState] = useState(null);
  const [outputs, setOutputs] = useState(null);
  const [versions, setVersions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [chatLog, setChatLog] = useState([]);
  const wsRef = useRef(null);
  // The <video> element appends `?b=<bust>` to its src and calls .load()
  // when bust changes, forcing the browser to drop its cached MP4 (path
  // stays the same across re-renders). The bust value is the active
  // version number, so any time a new snapshot lands — whether from a UI
  // edit, CLI run, or external snapshot — the URL changes and the player
  // reloads. Initial value 0; gets set from the versions list as soon as
  // the first refresh lands.
  const [videoBust, setVideoBust] = useState(0);
  const finalVideoRef = useRef(null);

  useEffect(() => {
    try {
      if (jobId) localStorage.setItem("agentic_jobId", jobId);
      else localStorage.removeItem("agentic_jobId");
    } catch { /* private mode etc. — non-fatal */ }
  }, [jobId]);

  // Force the <video> element to drop its cached buffer + reset to 0:00
  // whenever the user causes the underlying file to change. Skipping the
  // initial render (videoBust === 0) avoids interrupting the very first
  // load on page mount.
  useEffect(() => {
    if (videoBust === 0) return;
    const v = finalVideoRef.current;
    if (v) {
      v.pause();
      v.load();
    }
  }, [videoBust]);

  const phaseStatuses = state?.phase_status || {
    story: "pending", audio: "pending", video: "pending",
  };

  const refreshAll = async () => {
    if (!jobId) return;
    try {
      const [s, o, v] = await Promise.all([
        fetch(`${API}/api/state/${jobId}`).then((r) => r.ok ? r.json() : null),
        fetch(`${API}/api/outputs/${jobId}`).then((r) => r.ok ? r.json() : null),
        fetch(`${API}/api/versions/${jobId}`).then((r) => r.ok ? r.json() : []),
      ]);
      if (s) setState(s);
      if (o) setOutputs(o);
      setVersions(v || []);
      // Sync the cache-buster to the active version so the <video> reloads
      // whenever the active version changes — including snapshots created
      // outside the UI (CLI, scripts, programmatic re-renders).
      const active = (v || []).find((row) => row.is_active);
      if (active && active.version != null) {
        setVideoBust((prev) => (prev === active.version ? prev : active.version));
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    if (!jobId) return;
    const ws = new WebSocket(WS(jobId));
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        setEvents((prev) => [...prev, msg]);
        if (["scene_composed", "phase_done", "final_ready", "applied", "snapshot", "job_complete"].includes(msg.event)) {
          refreshAll();
        }
        if (msg.event === "job_complete") setBusy(false);
      } catch (e) { console.warn(e); }
    };
    ws.onclose = () => setBusy(false);
    wsRef.current = ws;
    return () => ws.close();
     // eslint-disable-next-line
  }, [jobId]);

  useEffect(() => { refreshAll(); /* eslint-disable-next-line */ }, [jobId]);

  const handleGenerate = async (req) => {
    setBusy(true);
    setEvents([]);
    setChatLog([]);
    const r = await fetch(`${API}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }).then((x) => x.json());
    setJobId(r.job_id);
  };

  const handleEdit = async (query) => {
    if (!jobId) return;
    setBusy(true);
    setChatLog((l) => [...l, { role: "user", text: query }]);
    const before = events.length;
    const r = await fetch(`${API}/api/edit/${jobId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!r.ok) {
      setChatLog((l) => [...l, { role: "agent", text: "failed to submit edit" }]);
      setBusy(false);
      return;
    }
    // Wait briefly for the `applied` event to populate chat
    const check = setInterval(() => {
      const applied = events.slice(before).findLast?.((e) => e.event === "applied");
      if (applied) {
        clearInterval(check);
        setChatLog((l) => [...l, { role: "agent", intent: applied.data.intent, message: applied.data.message }]);
        setVideoBust((n) => n + 1);
        setBusy(false);
      }
    }, 400);
    setTimeout(() => clearInterval(check), 180_000);
  };

  const handleUndo = async () => {
    if (!jobId) return;
    setBusy(true);
    await fetch(`${API}/api/undo/${jobId}`, { method: "POST" });
    await refreshAll();
    // Force the video player to drop its cached MP4 and refetch.
    setVideoBust((n) => n + 1);
    setBusy(false);
  };

  const handleRestore = async (version) => {
    if (!jobId) return;
    setBusy(true);
    await fetch(`${API}/api/undo/${jobId}?to_version=${version}`, { method: "POST" });
    await refreshAll();
    setVideoBust((n) => n + 1);
    setBusy(false);
  };

  const handleRerun = async (phase) => {
    if (!jobId) return;
    setBusy(true);
    setEvents([]);
    await fetch(`${API}/api/rerun/${phase}/${jobId}`, { method: "POST" });
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>🎬 Agentic <span>Video Studio</span></h1>
        <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 14 }}>
          Prompt → Script → Audio → Video, with intelligent edits and undo.
        </div>

        <h2>1. Prompt</h2>
        <PromptForm onSubmit={handleGenerate} disabled={busy} />
        <JobResumePicker currentJobId={jobId} onPick={setJobId} />

        <h2>2. Pipeline</h2>
        <div className="card">
          <PhaseRow name="Story & Script" status={phaseStatuses.story} />
          <PhaseRow name="Audio" status={phaseStatuses.audio} />
          <PhaseRow name="Video" status={phaseStatuses.video} />
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn small secondary" disabled={!jobId || busy} onClick={() => handleRerun("story")}>Rerun story</button>
            <button className="btn small secondary" disabled={!jobId || busy} onClick={() => handleRerun("audio")}>Rerun audio</button>
            <button className="btn small secondary" disabled={!jobId || busy} onClick={() => handleRerun("video")}>Rerun video</button>
          </div>
        </div>

        <h2>Live events</h2>
        <EventStream events={events} />
      </aside>

      <main className="main">
        <h2>Final video</h2>
        {outputs?.final_mp4 ? (
          // `?b=<videoBust>` cache-busts ONLY when the user makes an edit
          // / undo / restore (videoBust is bumped manually in those
          // handlers, never on incidental re-renders). Combined with the
          // useEffect below calling .load(), the player drops its cached
          // MP4 and re-fetches, but without remounting the element — so
          // no NS_BINDING_ABORTED loops.
          <video
            className="video-player"
            ref={finalVideoRef}
            src={`${outputs.final_mp4}?b=${videoBust}`}
            controls
          />
        ) : (
          <div className="video-player" style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontSize: 14 }}>
            {jobId ? "rendering…" : "no video yet — start a generation from the sidebar."}
          </div>
        )}

        <h2>Story & characters</h2>
        <div className="card">
          {state?.story?.title
            ? <>
                <h3 style={{ margin: 0 }}>{state.story.title}</h3>
                <div style={{ color: "var(--muted)", fontSize: 13, marginBottom: 10 }}>{state.story.logline}</div>
                <CharactersRow outputs={outputs} />
              </>
            : <div className="empty">no story yet</div>}
        </div>

        <h2>Scenes</h2>
        <Scenes outputs={outputs} bust={videoBust} />

        {state?.story?.scenes?.length > 0 && (
          <div className="card" style={{ marginTop: 18 }}>
            <h3 style={{ margin: "0 0 6px" }}>Script preview</h3>
            {state.story.scenes.map((s) => (
              <div key={s.scene_id} style={{ padding: "8px 0", borderBottom: "1px dashed var(--border)" }}>
                <b>Scene {s.scene_id} · {s.location}</b>
                <div style={{ fontSize: 12, color: "var(--muted)", margin: "4px 0" }}>{s.action}</div>
                <div>
                  {s.dialogue.map((d, i) => (
                    <div key={i} style={{ fontSize: 12 }}>
                      <span style={{ color: "var(--accent)" }}>{d.speaker}:</span> "{d.line}"
                      <span style={{ color: "var(--muted)" }}> — {d.emotion}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <aside className="right">
        <h2>Edit agent</h2>
        <EditPanel jobId={jobId} busy={busy} onEdit={handleEdit} chatLog={chatLog} />

        <h2>Version history</h2>
        <VersionPanel
          jobId={jobId}
          versions={versions}
          refresh={refreshAll}
          onUndo={handleUndo}
          onRestore={handleRestore}
        />
      </aside>
    </div>
  );
}

const root = createRoot(document.getElementById("root"));
root.render(<App />);
