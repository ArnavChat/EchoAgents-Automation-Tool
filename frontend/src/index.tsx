import React, { useState, useRef, useEffect } from "react";
import "./styles.css";
import { createRoot } from "react-dom/client";

type TimelineEntry = { timestamp?: string; message: string };

// Robust extractor to find email draft irrespective of nesting shape
function extractEmailDraft(resp: any): any | null {
  if (!resp) return null;
  if (resp.result?.email) return resp.result.email; // direct
  if (resp.email) return resp.email; // direct alt
  const nested = resp.details?.orchestrator?.body?.result?.email; // msg-proxy nested
  if (nested) return nested;
  return null;
}

const STYLE_OPTIONS = [
  { key: "formal", label: "Formal" },
  { key: "casual", label: "Casual" },
  { key: "concise", label: "Concise" },
  { key: "bullet_summary", label: "Bullet" },
];

const VoiceConsole: React.FC = () => {
  // Media / audio
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(
    null
  );
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Text + transcripts
  const [transcript, setTranscript] = useState("");
  const [originalTranscript, setOriginalTranscript] = useState("");
  const [manualText, setManualText] = useState("");

  // Results / email
  const [confirmedResult, setConfirmedResult] = useState<any>(null);
  const [pendingEmail, setPendingEmail] = useState<any>(null);
  const [draftStyle, setDraftStyle] = useState("formal");
  const [showDiff, setShowDiff] = useState(false);
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  // Misc
  const [inFlight, setInFlight] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);

  const log = (m: string) =>
    setLogs((l) => [
      new Date().toLocaleTimeString() + " " + m,
      ...l.slice(0, 199),
    ]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  function toggleTheme() {
    setTheme((t) => (t === "dark" ? "light" : "dark"));
  }

  function diffTokens(raw: string, styled: string) {
    const rawTokens = raw.split(/\s+/).filter(Boolean);
    const styledTokens = styled.split(/\s+/).filter(Boolean);
    const rawCounts: Record<string, number> = {};
    rawTokens.forEach((t) => (rawCounts[t] = (rawCounts[t] || 0) + 1));
    const nodes: React.ReactNode[] = [];
    styledTokens.forEach((t, i) => {
      if (rawCounts[t]) {
        rawCounts[t] -= 1;
        nodes.push(<span key={i}>{t} </span>);
      } else {
        nodes.push(
          <span key={i} className="token-added">
            {t + " "}
          </span>
        );
      }
    });
    const removed: string[] = [];
    Object.entries(rawCounts).forEach(([tok, cnt]) => {
      for (let i = 0; i < cnt; i++) removed.push(tok);
    });
    return { nodes, removed };
  }

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data);
      };
      mr.onstop = () => {
        const blob = new Blob(chunks, { type: "audio/webm" });
        setAudioBlob(blob);
        const url = URL.createObjectURL(blob);
        if (audioRef.current) audioRef.current.src = url;
        log(`Captured audio ${(blob.size / 1024).toFixed(1)} KB`);
      };
      mr.start();
      setMediaRecorder(mr);
      setRecording(true);
      log("Recording...");
    } catch (e: any) {
      log("Failed to start recording: " + e.message);
    }
  }

  function stopRecording() {
    if (!mediaRecorder) return;
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
    setRecording(false);
    setMediaRecorder(null);
    log("Stopped recording");
  }

  // Service endpoints (allow override via build-time env variables)
  const VOICE_AGENT_BASE = (
    process.env.VOICE_AGENT_URL || "http://localhost:8003"
  ).replace(/\/$/, "");
  const MSG_PROXY_BASE = (
    process.env.MSG_PROXY_URL || "http://localhost:8001"
  ).replace(/\/$/, "");
  const ORCHESTRATOR_BASE = (
    process.env.ORCHESTRATOR_URL || "http://localhost:8002"
  ).replace(/\/$/, "");

  async function transcribeOnly() {
    if (!audioBlob) return;
    setInFlight(true);
    setTranscript("");
    setOriginalTranscript("");
    setConfirmedResult(null);
    setPendingEmail(null);
    log("Uploading audio for transcription");
    try {
      const form = new FormData();
      form.append("file", audioBlob, "input.webm");
      form.append("user_id", "web_client");
      const resp = await fetch(`${VOICE_AGENT_BASE}/voice/command`, {
        method: "POST",
        body: form,
      });
      const data = await resp.json();
      setConfirmedResult(data);
      // Attempt to derive transcript; leaving flexible due to unknown shape
      const tx =
        data.details?.voice_agent?.body?.transcript || data.transcript || "";
      if (tx) {
        setTranscript(tx);
        setOriginalTranscript(tx);
      }
      const draft = extractEmailDraft(data);
      if (draft?.status === "pending_confirmation") setPendingEmail(draft);
    } catch (e: any) {
      log("Transcription failed: " + e.message);
    } finally {
      setInFlight(false);
    }
  }

  async function confirmForward() {
    if (!transcript) return;
    setInFlight(true);
    log("Forwarding transcript to orchestrator");
    try {
      const resp = await fetch(`${VOICE_AGENT_BASE}/voice/forward`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: transcript, user_id: "web_client" }),
      });
      const data = await resp.json();
      setConfirmedResult(data);
      const draft = extractEmailDraft(data);
      if (draft?.status === "pending_confirmation") setPendingEmail(draft);
      log("Forward result: " + JSON.stringify(data));
    } catch (e: any) {
      log("Forward failed: " + e.message);
    } finally {
      setInFlight(false);
    }
  }

  async function submitManual() {
    if (!manualText.trim()) return;
    setInFlight(true);
    setConfirmedResult(null);
    log("Sending manual text via msg-proxy");
    try {
      const payload = {
        source: "voice",
        user_id: "web_client",
        text: manualText,
        attachments: [],
        timestamp: new Date().toISOString(),
      };
      const resp = await fetch(`${MSG_PROXY_BASE}/webhook/voice`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      setConfirmedResult(data);
      const draft = extractEmailDraft(data);
      if (draft?.status === "pending_confirmation") setPendingEmail(draft);
      log("Manual submit result: " + JSON.stringify(data));
    } catch (e: any) {
      log("Manual submit failed: " + e.message);
    } finally {
      setInFlight(false);
    }
  }

  async function sendEmailConfirmation(confirm: boolean) {
    setInFlight(true);
    try {
      const payload = {
        source: "voice",
        user_id: "web_client",
        text: confirm ? "yes" : "no",
        attachments: [],
        timestamp: new Date().toISOString(),
      };
      const resp = await fetch(`${MSG_PROXY_BASE}/webhook/voice`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      setConfirmedResult(data);
      const draft = extractEmailDraft(data);
      if (draft?.status === "pending_confirmation") setPendingEmail(draft);
      else if (confirm) setPendingEmail(null);
      log("Email confirmation result: " + JSON.stringify(data));
    } catch (e: any) {
      log("Email confirmation failed: " + e.message);
    } finally {
      setInFlight(false);
    }
  }

  async function applyStyle() {
    if (!pendingEmail) return;
    setInFlight(true);
    try {
      const resp = await fetch(`${ORCHESTRATOR_BASE}/email/style`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ style: draftStyle }),
      });
      const data = await resp.json();
      if (data.email) setPendingEmail(data.email);
    } catch (e: any) {
      log("Apply style failed: " + e.message);
    } finally {
      setInFlight(false);
    }
  }

  const diff =
    pendingEmail &&
    pendingEmail.raw_body &&
    pendingEmail.styled_body &&
    showDiff
      ? diffTokens(pendingEmail.raw_body, pendingEmail.styled_body)
      : null;

  return (
    <div className="app-shell fade-in">
      <header className="hero">
        <h1 className="gradient-text">EchoAgents Console</h1>
        <p className="lead">
          Voice, email drafting & style transformations in a streamlined
          workspace.
        </p>
        <div className="top-bar-actions">
          <button
            onClick={toggleTheme}
            aria-label="Toggle theme"
            className="ghost-btn"
          >
            {theme === "dark" ? "🌙 Dark" : "☀️ Light"}
          </button>
        </div>
      </header>
      <div className="layout-grid">
        <section className="panel">
          <h2 className="section">Compose / Record</h2>
          <div className="controls">
            {!recording && (
              <button className="primary" onClick={startRecording}>
                🎙 Start
              </button>
            )}
            {recording && (
              <button className="primary recording" onClick={stopRecording}>
                ■ Stop
              </button>
            )}
            <button disabled={!audioBlob || inFlight} onClick={transcribeOnly}>
              Transcribe
            </button>
            <button disabled={!transcript || inFlight} onClick={confirmForward}>
              Forward
            </button>
          </div>
          <label className="field-label">Manual Instruction</label>
          <textarea
            placeholder="Send email to bob@example.com subject: Update We will meet tomorrow. Make it casual"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
          />
          <div className="compose-actions">
            <button
              className="primary"
              disabled={!manualText || inFlight}
              onClick={submitManual}
            >
              Submit
            </button>
            {pendingEmail && (
              <>
                <div className="style-chips">
                  {STYLE_OPTIONS.map((s) => (
                    <button
                      key={s.key}
                      className={
                        "chip" + (draftStyle === s.key ? " active" : "")
                      }
                      disabled={inFlight}
                      onClick={() => setDraftStyle(s.key)}
                      aria-label={`Select ${s.label} style`}
                    >
                      {s.label}
                    </button>
                  ))}
                  <button
                    className="chip apply"
                    disabled={inFlight}
                    onClick={applyStyle}
                  >
                    Apply
                  </button>
                </div>
                <div className="send-actions">
                  <button
                    className="success"
                    disabled={inFlight}
                    onClick={() => sendEmailConfirmation(true)}
                  >
                    Send
                  </button>
                  <button
                    className="ghost danger"
                    disabled={inFlight}
                    onClick={() => sendEmailConfirmation(false)}
                  >
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
          <div className="divider" />
          <h3 className="subhead">Transcript</h3>
          <textarea
            readOnly
            value={transcript}
            placeholder="Transcript will appear here..."
          />
          {originalTranscript && originalTranscript !== transcript && (
            <p className="orig-inline">
              Original: <code>{originalTranscript}</code>
            </p>
          )}
          <audio ref={audioRef} controls />
        </section>
        <section className="panel">
          <h2 className="section">Draft Preview</h2>
          {pendingEmail?.status === "pending_confirmation" ? (
            <div className="email-preview enhanced">
              <div className="meta-row">
                <div>
                  <span className="badge-inline">To</span>{" "}
                  {pendingEmail.to?.join(", ") || "(none)"}
                </div>
                <div>
                  <span className="badge-inline">Subject</span>{" "}
                  {pendingEmail.subject}
                </div>
                {pendingEmail.styles?.length > 0 && (
                  <div>
                    <span className="badge-inline">Styles</span>{" "}
                    {pendingEmail.styles.join(" → ")}
                  </div>
                )}
              </div>
              <div className="preview-toolbar">
                {pendingEmail.raw_body &&
                  pendingEmail.styled_body &&
                  pendingEmail.raw_body.trim() !==
                    pendingEmail.styled_body.trim() && (
                    <button
                      className="ghost-btn"
                      onClick={() => setShowDiff((v) => !v)}
                    >
                      {showDiff ? "Hide Diff" : "Show Diff"}
                    </button>
                  )}
              </div>
              {!showDiff && (
                <div className="email-preview-body">
                  <pre>{pendingEmail.styled_body || pendingEmail.raw_body}</pre>
                </div>
              )}
              {showDiff && diff && (
                <div className="email-preview-body diff">
                  <pre className="diff-styled">{diff.nodes}</pre>
                  {diff.removed.length > 0 && (
                    <div className="removed-tokens">
                      Removed:{" "}
                      {diff.removed.map((t, i) => (
                        <span key={i} className="token-removed">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {pendingEmail.raw_body &&
                pendingEmail.styled_body &&
                pendingEmail.raw_body.trim() !==
                  pendingEmail.styled_body.trim() &&
                !showDiff && (
                  <details>
                    <summary>Show original body</summary>
                    <pre>{pendingEmail.raw_body}</pre>
                  </details>
                )}
            </div>
          ) : (
            <p className="placeholder">
              No draft yet. Submit an instruction or recording.
            </p>
          )}
          <div className="divider" />
          <h2 className="section">Result JSON</h2>
          {confirmedResult ? (
            <pre className="confirm-pre code-block">
              {JSON.stringify(confirmedResult, null, 2)}
            </pre>
          ) : (
            <p className="placeholder">No result yet.</p>
          )}
        </section>
        <section className="panel span-2">
          <h2 className="section">Logs</h2>
          <div className="log-view">
            {logs.map((l, i) => (
              <div className="log-line" key={i}>
                {l}
              </div>
            ))}
          </div>
        </section>
      </div>
      <footer>EchoAgents • UI prototype • Theme: {theme}</footer>
    </div>
  );
};

createRoot(document.getElementById("root")!).render(<VoiceConsole />);
