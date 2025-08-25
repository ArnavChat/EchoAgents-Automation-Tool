import React, { useState, useRef } from "react";
import { createRoot } from "react-dom/client";

const VoiceConsole: React.FC = () => {
  const [recording, setRecording] = useState(false);
  const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(
    null
  );
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [transcript, setTranscript] = useState("");
  const [originalTranscript, setOriginalTranscript] = useState("");
  const [confirmedResult, setConfirmedResult] = useState<any>(null);
  const [inFlight, setInFlight] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const log = (m: string) =>
    setLogs((l) => [
      new Date().toLocaleTimeString() + " " + m,
      ...l.slice(0, 199),
    ]);

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
        log("Captured audio " + (blob.size / 1024).toFixed(1) + " KB");
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
    if (mediaRecorder && recording) {
      mediaRecorder.stop();
      mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      setRecording(false);
      setMediaRecorder(null);
      log("Stopped recording");
    }
  }

  async function transcribeOnly() {
    if (!audioBlob) return;
    setInFlight(true);
    setTranscript("");
    setOriginalTranscript("");
    setConfirmedResult(null);
    log("Uploading audio to voice-agent for transcription only");
    try {
      const form = new FormData();
      form.append("file", audioBlob, "input.webm");
      form.append("user_id", "web_client");
      const resp = await fetch("http://localhost:8003/voice/command", {
        method: "POST",
        body: form,
      });
      const data = await resp.json();
      setTranscript(data.transcript || "");
      setOriginalTranscript(data.original_transcript || "");
      log("Received transcript");
      log("(Not auto-confirmed yet.)");
    } catch (e: any) {
      log("Upload failed: " + e.message);
    } finally {
      setInFlight(false);
    }
  }

  async function confirmForward() {
    if (!transcript) return;
    setInFlight(true);
    log("Forwarding confirmed transcript to orchestrator via msg-proxy");
    try {
      const resp = await fetch("http://localhost:8003/voice/forward", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: transcript, user_id: "web_client" }),
      });
      const data = await resp.json();
      setConfirmedResult(data);
      log("Forward result: " + JSON.stringify(data));
    } catch (e: any) {
      log("Forward failed: " + e.message);
    } finally {
      setInFlight(false);
    }
  }

  return (
    <div className="panel">
      <h1>EchoAgents Voice Console</h1>
      <p>
        Record a command like:{" "}
        <code>
          Schedule a meeting with someone@example.com on Friday at 5 p.m.
        </code>
      </p>
      <div className="flex">
        {!recording && (
          <button onClick={startRecording}>Start Recording</button>
        )}
        {recording && (
          <button className="recording" onClick={stopRecording}>
            Stop
          </button>
        )}
        <button disabled={!audioBlob || inFlight} onClick={transcribeOnly}>
          Transcribe
        </button>
        <button disabled={!transcript || inFlight} onClick={confirmForward}>
          Confirm & Send
        </button>
      </div>
      <audio ref={audioRef} controls />
      <h3>Transcript</h3>
      <textarea readOnly value={transcript}></textarea>
      {originalTranscript && originalTranscript !== transcript && (
        <p>
          Original: <code>{originalTranscript}</code>
        </p>
      )}
      {confirmedResult && (
        <div>
          <h3>Confirmation Result</h3>
          <pre style={{ background: "#1e293b", padding: "0.75rem" }}>
            {JSON.stringify(confirmedResult, null, 2)}
          </pre>
        </div>
      )}
      <h3>Logs</h3>
      <div>
        {logs.map((l, i) => (
          <div className="log-line" key={i}>
            {l}
          </div>
        ))}
      </div>
    </div>
  );
};

createRoot(document.getElementById("root")!).render(<VoiceConsole />);
