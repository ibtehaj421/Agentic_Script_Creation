// src/app.jsx
import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Fragment, jsx, jsxs } from "react/jsx-runtime";
var API = "";
var WS = (job) => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/progress/${job}`;
};
function StatusPill({ status }) {
  return /* @__PURE__ */ jsx("span", { className: `status-pill ${status}`, children: status });
}
function PhaseRow({ name, status }) {
  return /* @__PURE__ */ jsxs("div", { className: "phase-row", children: [
    /* @__PURE__ */ jsx("span", { className: "phase-name", children: name }),
    /* @__PURE__ */ jsx(StatusPill, { status: status || "pending" })
  ] });
}
function PromptForm({ onSubmit, disabled }) {
  const [prompt, setPrompt] = useState("A young astronaut discovers a hidden ocean on Mars and uncovers an ancient intelligence.");
  const [numScenes, setNumScenes] = useState(3);
  const [style, setStyle] = useState("cinematic");
  return /* @__PURE__ */ jsxs("div", { className: "form-block", children: [
    /* @__PURE__ */ jsx("label", { children: "Prompt" }),
    /* @__PURE__ */ jsx("textarea", { value: prompt, onChange: (e) => setPrompt(e.target.value) }),
    /* @__PURE__ */ jsxs("div", { className: "row", children: [
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("label", { children: "Scenes" }),
        /* @__PURE__ */ jsx(
          "input",
          {
            type: "number",
            min: "1",
            max: "8",
            value: numScenes,
            onChange: (e) => setNumScenes(Number(e.target.value))
          }
        )
      ] }),
      /* @__PURE__ */ jsxs("div", { children: [
        /* @__PURE__ */ jsx("label", { children: "Style" }),
        /* @__PURE__ */ jsxs("select", { value: style, onChange: (e) => setStyle(e.target.value), children: [
          /* @__PURE__ */ jsx("option", { children: "cinematic" }),
          /* @__PURE__ */ jsx("option", { children: "anime" }),
          /* @__PURE__ */ jsx("option", { children: "noir" }),
          /* @__PURE__ */ jsx("option", { children: "cyberpunk" }),
          /* @__PURE__ */ jsx("option", { children: "photorealistic" }),
          /* @__PURE__ */ jsx("option", { children: "watercolor" })
        ] })
      ] })
    ] }),
    /* @__PURE__ */ jsx(
      "button",
      {
        className: "btn",
        disabled: disabled || !prompt.trim(),
        onClick: () => onSubmit({ prompt, num_scenes: numScenes, style }),
        children: "\u25B6 Generate video"
      }
    )
  ] });
}
function JobResumePicker({ currentJobId, onPick }) {
  const [jobs, setJobs] = useState([]);
  useEffect(() => {
    fetch(`${API}/api/jobs`).then((r) => r.ok ? r.json() : []).then(setJobs).catch(() => setJobs([]));
  }, [currentJobId]);
  if (!jobs.length) return null;
  return /* @__PURE__ */ jsxs("div", { className: "form-block", style: { marginTop: 8 }, children: [
    /* @__PURE__ */ jsx("label", { children: "Or resume a previous job" }),
    /* @__PURE__ */ jsxs(
      "select",
      {
        value: currentJobId || "",
        onChange: (e) => e.target.value && onPick(e.target.value),
        children: [
          /* @__PURE__ */ jsx("option", { value: "", children: "\u2014 pick one \u2014" }),
          jobs.map((j) => /* @__PURE__ */ jsxs("option", { value: j.job_id, children: [
            j.title || "(untitled)",
            " \xB7 ",
            j.job_id,
            " \xB7 v",
            j.latest_version
          ] }, j.job_id))
        ]
      }
    )
  ] });
}
function EventStream({ events }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events]);
  return /* @__PURE__ */ jsx("div", { className: "events", ref, children: events.length === 0 ? /* @__PURE__ */ jsx("div", { style: { color: "var(--muted)" }, children: "waiting for pipeline events\u2026" }) : events.slice(-200).map((e, i) => /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsxs("b", { children: [
      "[",
      e.phase,
      "]"
    ] }),
    " ",
    e.event,
    " ",
    e.data && Object.keys(e.data).length ? JSON.stringify(e.data).slice(0, 120) : ""
  ] }, i)) });
}
function Scenes({ outputs, bust = 0 }) {
  if (!outputs || !outputs.scenes) return null;
  return /* @__PURE__ */ jsx("div", { className: "scene-grid", children: Object.entries(outputs.scenes).map(([id, s]) => (
    // `key` includes bust so an explicit edit / undo / restore
    // remounts the tile (forcing a fresh fetch). Bust only changes
    // on user actions, so this doesn't loop.
    /* @__PURE__ */ jsxs("div", { className: "scene-tile", children: [
      s.composed ? /* @__PURE__ */ jsx("video", { src: `${s.composed}?b=${bust}`, controls: true, muted: true }) : s.background ? /* @__PURE__ */ jsx("img", { src: `${s.background}?b=${bust}`, alt: `scene ${id}` }) : null,
      /* @__PURE__ */ jsxs("div", { className: "meta", children: [
        "Scene ",
        id
      ] })
    ] }, `${id}-${bust}`)
  )) });
}
function CharactersRow({ outputs }) {
  if (!outputs || !outputs.character_portraits) return null;
  const entries = Object.entries(outputs.character_portraits);
  if (!entries.length) return null;
  return /* @__PURE__ */ jsx("div", { className: "chip-row", style: { gap: 14 }, children: entries.map(([name, path]) => /* @__PURE__ */ jsxs("div", { style: { textAlign: "center" }, children: [
    /* @__PURE__ */ jsx("img", { src: path, alt: name, style: { width: 68, height: 68, borderRadius: "50%", objectFit: "cover", border: "1px solid var(--border)" } }),
    /* @__PURE__ */ jsx("div", { style: { fontSize: 11, color: "var(--muted)", marginTop: 4 }, children: name })
  ] }, name)) });
}
function _lineage(versions, target) {
  const byVer = new Map(versions.map((v) => [v.version, v]));
  const chain = [];
  const seen = /* @__PURE__ */ new Set();
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
  if (!jobId) return /* @__PURE__ */ jsx("div", { className: "empty", children: "Start a job to see versions." });
  const active = versions.find((v) => v.is_active);
  const canUndo = active && active.parent_version != null;
  return /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsxs("div", { className: "row", style: { marginBottom: 12 }, children: [
      /* @__PURE__ */ jsx("button", { className: "btn small warn", onClick: onUndo, disabled: !canUndo, children: "\u21B6 Undo last" }),
      /* @__PURE__ */ jsx("button", { className: "btn small secondary", onClick: refresh, children: "\u27F3" })
    ] }),
    /* @__PURE__ */ jsxs("div", { className: "versions-list", children: [
      versions.length === 0 && /* @__PURE__ */ jsx("div", { className: "empty", children: "no versions yet" }),
      versions.slice().reverse().map((v) => {
        const isActive = !!v.is_active;
        const chain = _lineage(versions, v.version);
        const lineageText = chain.length > 1 ? `lineage: ${chain.map((n) => "v" + n).join(" \u2192 ")}` : `root version`;
        return /* @__PURE__ */ jsxs(
          "div",
          {
            className: "version-row" + (isActive ? " active" : ""),
            title: lineageText,
            style: isActive ? {
              borderColor: "var(--accent, #5b8def)",
              background: "rgba(91,141,239,0.08)"
            } : void 0,
            children: [
              /* @__PURE__ */ jsxs("div", { children: [
                /* @__PURE__ */ jsxs("div", { className: "v-num", children: [
                  "v",
                  v.version,
                  isActive && /* @__PURE__ */ jsx("span", { style: { color: "var(--accent, #5b8def)", marginLeft: 6, fontSize: 11 }, children: "\u25CF active" }),
                  v.parent_version != null && /* @__PURE__ */ jsxs("span", { style: { color: "var(--muted)", marginLeft: 6, fontSize: 10 }, children: [
                    "\u2190 v",
                    v.parent_version
                  ] })
                ] }),
                /* @__PURE__ */ jsxs("div", { style: { fontSize: 11, color: "var(--muted)" }, children: [
                  "[",
                  v.triggered_by,
                  "] ",
                  v.change_summary || v.changed_phase || "pipeline"
                ] })
              ] }),
              !isActive && /* @__PURE__ */ jsx("button", { className: "btn small secondary", onClick: () => onRestore(v.version), children: "Restore" })
            ]
          },
          v.version
        );
      })
    ] })
  ] });
}
function EditPanel({ jobId, busy, onEdit, chatLog }) {
  const [q, setQ] = useState("");
  return /* @__PURE__ */ jsxs("div", { children: [
    /* @__PURE__ */ jsxs("div", { className: "edit-chat", children: [
      chatLog.length === 0 && /* @__PURE__ */ jsx("div", { className: "empty", children: 'Try: "make scene 2 darker", "change voice to whispered", "apply cyberpunk filter"' }),
      chatLog.map((m, i) => /* @__PURE__ */ jsx("div", { className: `edit-bubble ${m.role}`, children: m.role === "agent" && m.intent ? /* @__PURE__ */ jsxs(Fragment, { children: [
        /* @__PURE__ */ jsx("b", { children: m.intent.intent }),
        " \u2192 target=",
        m.intent.target,
        ", scope=",
        m.intent.scope || "global",
        " (conf=",
        m.intent.confidence?.toFixed(2),
        ")",
        /* @__PURE__ */ jsx("br", {}),
        m.message
      ] }) : m.text }, i))
    ] }),
    /* @__PURE__ */ jsxs("div", { style: { marginTop: 12 }, children: [
      /* @__PURE__ */ jsx(
        "textarea",
        {
          value: q,
          onChange: (e) => setQ(e.target.value),
          placeholder: "Describe your edit\u2026",
          disabled: !jobId || busy
        }
      ),
      /* @__PURE__ */ jsx("div", { className: "row", style: { marginTop: 6 }, children: /* @__PURE__ */ jsx(
        "button",
        {
          className: "btn small",
          disabled: !jobId || busy || !q.trim(),
          onClick: () => {
            onEdit(q);
            setQ("");
          },
          children: "Send edit"
        }
      ) })
    ] })
  ] });
}
function App() {
  const [jobId, setJobId] = useState(() => {
    try {
      return localStorage.getItem("agentic_jobId");
    } catch {
      return null;
    }
  });
  const [events, setEvents] = useState([]);
  const [state, setState] = useState(null);
  const [outputs, setOutputs] = useState(null);
  const [versions, setVersions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [chatLog, setChatLog] = useState([]);
  const wsRef = useRef(null);
  const [videoBust, setVideoBust] = useState(0);
  const finalVideoRef = useRef(null);
  useEffect(() => {
    try {
      if (jobId) localStorage.setItem("agentic_jobId", jobId);
      else localStorage.removeItem("agentic_jobId");
    } catch {
    }
  }, [jobId]);
  useEffect(() => {
    if (videoBust === 0) return;
    const v = finalVideoRef.current;
    if (v) {
      v.pause();
      v.load();
    }
  }, [videoBust]);
  const phaseStatuses = state?.phase_status || {
    story: "pending",
    audio: "pending",
    video: "pending"
  };
  const refreshAll = async () => {
    if (!jobId) return;
    try {
      const [s, o, v] = await Promise.all([
        fetch(`${API}/api/state/${jobId}`).then((r) => r.ok ? r.json() : null),
        fetch(`${API}/api/outputs/${jobId}`).then((r) => r.ok ? r.json() : null),
        fetch(`${API}/api/versions/${jobId}`).then((r) => r.ok ? r.json() : [])
      ]);
      if (s) setState(s);
      if (o) setOutputs(o);
      setVersions(v || []);
      const active = (v || []).find((row) => row.is_active);
      if (active && active.version != null) {
        setVideoBust((prev) => prev === active.version ? prev : active.version);
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
      } catch (e) {
        console.warn(e);
      }
    };
    ws.onclose = () => setBusy(false);
    wsRef.current = ws;
    return () => ws.close();
  }, [jobId]);
  useEffect(() => {
    refreshAll();
  }, [jobId]);
  const handleGenerate = async (req) => {
    setBusy(true);
    setEvents([]);
    setChatLog([]);
    const r = await fetch(`${API}/api/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req)
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
      body: JSON.stringify({ query })
    });
    if (!r.ok) {
      setChatLog((l) => [...l, { role: "agent", text: "failed to submit edit" }]);
      setBusy(false);
      return;
    }
    const check = setInterval(() => {
      const applied = events.slice(before).findLast?.((e) => e.event === "applied");
      if (applied) {
        clearInterval(check);
        setChatLog((l) => [...l, { role: "agent", intent: applied.data.intent, message: applied.data.message }]);
        setVideoBust((n) => n + 1);
        setBusy(false);
      }
    }, 400);
    setTimeout(() => clearInterval(check), 18e4);
  };
  const handleUndo = async () => {
    if (!jobId) return;
    setBusy(true);
    await fetch(`${API}/api/undo/${jobId}`, { method: "POST" });
    await refreshAll();
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
  return /* @__PURE__ */ jsxs("div", { className: "app", children: [
    /* @__PURE__ */ jsxs("aside", { className: "sidebar", children: [
      /* @__PURE__ */ jsxs("h1", { children: [
        "\u{1F3AC} Agentic ",
        /* @__PURE__ */ jsx("span", { children: "Video Studio" })
      ] }),
      /* @__PURE__ */ jsx("div", { style: { color: "var(--muted)", fontSize: 12, marginBottom: 14 }, children: "Prompt \u2192 Script \u2192 Audio \u2192 Video, with intelligent edits and undo." }),
      /* @__PURE__ */ jsx("h2", { children: "1. Prompt" }),
      /* @__PURE__ */ jsx(PromptForm, { onSubmit: handleGenerate, disabled: busy }),
      /* @__PURE__ */ jsx(JobResumePicker, { currentJobId: jobId, onPick: setJobId }),
      /* @__PURE__ */ jsx("h2", { children: "2. Pipeline" }),
      /* @__PURE__ */ jsxs("div", { className: "card", children: [
        /* @__PURE__ */ jsx(PhaseRow, { name: "Story & Script", status: phaseStatuses.story }),
        /* @__PURE__ */ jsx(PhaseRow, { name: "Audio", status: phaseStatuses.audio }),
        /* @__PURE__ */ jsx(PhaseRow, { name: "Video", status: phaseStatuses.video }),
        /* @__PURE__ */ jsxs("div", { className: "row", style: { marginTop: 12 }, children: [
          /* @__PURE__ */ jsx("button", { className: "btn small secondary", disabled: !jobId || busy, onClick: () => handleRerun("story"), children: "Rerun story" }),
          /* @__PURE__ */ jsx("button", { className: "btn small secondary", disabled: !jobId || busy, onClick: () => handleRerun("audio"), children: "Rerun audio" }),
          /* @__PURE__ */ jsx("button", { className: "btn small secondary", disabled: !jobId || busy, onClick: () => handleRerun("video"), children: "Rerun video" })
        ] })
      ] }),
      /* @__PURE__ */ jsx("h2", { children: "Live events" }),
      /* @__PURE__ */ jsx(EventStream, { events })
    ] }),
    /* @__PURE__ */ jsxs("main", { className: "main", children: [
      /* @__PURE__ */ jsx("h2", { children: "Final video" }),
      outputs?.final_mp4 ? (
        // `?b=<videoBust>` cache-busts ONLY when the user makes an edit
        // / undo / restore (videoBust is bumped manually in those
        // handlers, never on incidental re-renders). Combined with the
        // useEffect below calling .load(), the player drops its cached
        // MP4 and re-fetches, but without remounting the element — so
        // no NS_BINDING_ABORTED loops.
        /* @__PURE__ */ jsx(
          "video",
          {
            className: "video-player",
            ref: finalVideoRef,
            src: `${outputs.final_mp4}?b=${videoBust}`,
            controls: true
          }
        )
      ) : /* @__PURE__ */ jsx("div", { className: "video-player", style: { display: "flex", alignItems: "center", justifyContent: "center", color: "var(--muted)", fontSize: 14 }, children: jobId ? "rendering\u2026" : "no video yet \u2014 start a generation from the sidebar." }),
      /* @__PURE__ */ jsx("h2", { children: "Story & characters" }),
      /* @__PURE__ */ jsx("div", { className: "card", children: state?.story?.title ? /* @__PURE__ */ jsxs(Fragment, { children: [
        /* @__PURE__ */ jsx("h3", { style: { margin: 0 }, children: state.story.title }),
        /* @__PURE__ */ jsx("div", { style: { color: "var(--muted)", fontSize: 13, marginBottom: 10 }, children: state.story.logline }),
        /* @__PURE__ */ jsx(CharactersRow, { outputs })
      ] }) : /* @__PURE__ */ jsx("div", { className: "empty", children: "no story yet" }) }),
      /* @__PURE__ */ jsx("h2", { children: "Scenes" }),
      /* @__PURE__ */ jsx(Scenes, { outputs, bust: videoBust }),
      state?.story?.scenes?.length > 0 && /* @__PURE__ */ jsxs("div", { className: "card", style: { marginTop: 18 }, children: [
        /* @__PURE__ */ jsx("h3", { style: { margin: "0 0 6px" }, children: "Script preview" }),
        state.story.scenes.map((s) => /* @__PURE__ */ jsxs("div", { style: { padding: "8px 0", borderBottom: "1px dashed var(--border)" }, children: [
          /* @__PURE__ */ jsxs("b", { children: [
            "Scene ",
            s.scene_id,
            " \xB7 ",
            s.location
          ] }),
          /* @__PURE__ */ jsx("div", { style: { fontSize: 12, color: "var(--muted)", margin: "4px 0" }, children: s.action }),
          /* @__PURE__ */ jsx("div", { children: s.dialogue.map((d, i) => /* @__PURE__ */ jsxs("div", { style: { fontSize: 12 }, children: [
            /* @__PURE__ */ jsxs("span", { style: { color: "var(--accent)" }, children: [
              d.speaker,
              ":"
            ] }),
            ' "',
            d.line,
            '"',
            /* @__PURE__ */ jsxs("span", { style: { color: "var(--muted)" }, children: [
              " \u2014 ",
              d.emotion
            ] })
          ] }, i)) })
        ] }, s.scene_id))
      ] })
    ] }),
    /* @__PURE__ */ jsxs("aside", { className: "right", children: [
      /* @__PURE__ */ jsx("h2", { children: "Edit agent" }),
      /* @__PURE__ */ jsx(EditPanel, { jobId, busy, onEdit: handleEdit, chatLog }),
      /* @__PURE__ */ jsx("h2", { children: "Version history" }),
      /* @__PURE__ */ jsx(
        VersionPanel,
        {
          jobId,
          versions,
          refresh: refreshAll,
          onUndo: handleUndo,
          onRestore: handleRestore
        }
      )
    ] })
  ] });
}
var root = createRoot(document.getElementById("root"));
root.render(/* @__PURE__ */ jsx(App, {}));
