"use client";
import React, { useState, useEffect, useRef } from "react";

export default function JenkinsConsole() {
  const API_BASE = "http://localhost:8000/api/builds";

  // --- Build Info ---
  const [jobName, setJobName] = useState("HelloJenkinsLive");
  const [buildId, setBuildId] = useState("");
  const [status, setStatus] = useState("Idle");

  // --- Logs ---
  const [logsBuildId, setLogsBuildId] = useState("");
  const [tailLines, setTailLines] = useState(1000);
  const [displayLogs, setDisplayLogs] = useState("");
  const [isLive, setIsLive] = useState(false);

  const pollIntervalRef = useRef(null);
  const fullLogBuffer = useRef([]);
  const logRef = useRef(null);

  // --- Auto-scroll for logs ---
  useEffect(() => {
    const logBox = logRef.current;
    if (logBox) {
      const isNearBottom =
        logBox.scrollHeight - logBox.scrollTop - logBox.clientHeight < 100;
      if (isNearBottom) logBox.scrollTop = logBox.scrollHeight;
    }
  }, [displayLogs]);

  // --- Start Build ---
  const startBuild = async () => {
    setStatus("Starting...");
    try {
      const res = await fetch(`${API_BASE}/start/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_name: jobName }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to start build");

      const newBuildId = data.id;
      setBuildId(newBuildId);
      setLogsBuildId(newBuildId);
      setStatus(data.status || "PENDING");
    } catch (err) {
      setStatus(`⚠️ ${err.message}`);
    }
  };

  // --- Stop Build ---
  const stopBuild = async () => {
    if (!buildId) return;
    setStatus("Stopping...");
    try {
      const res = await fetch(`${API_BASE}/${buildId}/stop/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to stop build");
      setStatus("Stop requested");
    } catch (err) {
      setStatus(`⚠️ ${err.message}`);
    }
  };

  // --- Check Status ---
  const checkStatus = async () => {
    if (!buildId) return;
    try {
      const res = await fetch(`${API_BASE}/${buildId}/status/`);
      const data = await res.json();
      setStatus(data.status || "UNKNOWN");
      setLogsBuildId(buildId);
    } catch (err) {
      setStatus(`⚠️ ${err.message}`);
    }
  };

  // --- Fetch Logs Once ---
  const fetchLogsOnce = async () => {
    if (!logsBuildId) return;
    stopLiveLogs();
    try {
      const res = await fetch(
        `${API_BASE}/${logsBuildId}/logs/?full=false&tail=${tailLines}`
      );
      const text = await res.text();
      fullLogBuffer.current = text.split("\n").slice(-3000);
      setDisplayLogs(fullLogBuffer.current.join("\n"));
    } catch (err) {
      setDisplayLogs(`⚠️ ${err.message}`);
    }
  };

  // --- Live Logs ---
  const startLiveLogs = () => {
    if (!logsBuildId) return;
    setIsLive(true);
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);

    pollIntervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(
          `${API_BASE}/${logsBuildId}/logs/?full=false&tail=${tailLines}`
        );
        const text = await res.text();
        fullLogBuffer.current = text.split("\n").slice(-3000);
        setDisplayLogs(fullLogBuffer.current.join("\n"));
      } catch (err) {
        setDisplayLogs(`⚠️ ${err.message}`);
      }
    }, 2000);
  };

  const stopLiveLogs = () => {
    setIsLive(false);
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
  };

  return (
    <div style={{ padding: 5, fontFamily: "monospace" }}>
      <h1 style={{ textAlign: "center", margin: "5px 0", fontSize: "20px" }}>
        Aura Jenkins Console
      </h1>

      {/* --- Top Controls / Status --- */}
      <div
        style={{
          display: "flex",
          gap: "10px",
          alignItems: "center",
          flexWrap: "wrap",
          marginBottom: 8,
          padding: "4px 8px",
          background: "#111",
          borderRadius: "6px",
          color: "#0f0",
          fontSize: "12px",
        }}
      >
        <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
          <span>Job:</span>
          <input
            placeholder="Job Name"
            value={jobName}
            onChange={(e) => setJobName(e.target.value)}
            style={{ width: "140px", height: "24px", fontSize: "12px" }}
          />
        </div>

        <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
          <span>Build ID:</span>
          <input
            placeholder="Build ID"
            value={buildId}
            onChange={(e) => setBuildId(e.target.value)}
            style={{ width: "100px", height: "24px", fontSize: "12px" }}
          />
        </div>

        <div style={{ flex: 1 }}>Status: {status}</div>

        {/* Action Buttons */}
        <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
          <button style={{ height: "24px", fontSize: "12px" }} onClick={startBuild}>
            Start
          </button>
          <button style={{ height: "24px", fontSize: "12px" }} onClick={stopBuild}>
            Stop
          </button>
          <button style={{ height: "24px", fontSize: "12px" }} onClick={checkStatus}>
            Status
          </button>
          <select
            value={tailLines}
            onChange={(e) => setTailLines(Number(e.target.value))}
            style={{ height: "24px", fontSize: "12px" }}
          >
            <option value={500}>Last 500</option>
            <option value={1000}>Last 1000</option>
          </select>
          <button style={{ height: "24px", fontSize: "12px" }} onClick={fetchLogsOnce}>
            Fetch Logs
          </button>
          <button style={{ height: "24px", fontSize: "12px" }} onClick={startLiveLogs} disabled={isLive}>
            Live On
          </button>
          <button style={{ height: "24px", fontSize: "12px" }} onClick={stopLiveLogs} disabled={!isLive}>
            Live Off
          </button>
          <button
            style={{ height: "24px", fontSize: "12px", background: "#900", color: "#fff" }}
            onClick={() => setDisplayLogs("")}
          >
            Clear
          </button>
        </div>
      </div>

      {/* --- Logs --- */}
      <div style={{ marginBottom: 8 }}>
        <h3 style={{ margin: "4px 0", fontSize: "14px" }}>Logs</h3>
        <div
          ref={logRef}
          style={{
            marginTop: 10,
            background: "linear-gradient(180deg, #0a0a0a 0%, #000000 100%)",
            color: "#00ff7f",
            fontFamily: "'Fira Code', monospace",
            fontSize: "14px",
            lineHeight: "1.5",
            height: "600px",
            borderRadius: "8px",
            boxShadow: "0 0 10px rgba(0, 255, 100, 0.2)",
            overflowY: "auto",
            overflowX: "hidden",
            whiteSpace: "pre-wrap",
            wordWrap: "break-word",
            position: "relative",
          }}
        >
          <div
            style={{
              position: "sticky",
              top: 0,
              left: 0,
              right: 0,
              zIndex: 10,
              height: "30px",
              background: "linear-gradient(90deg, #111, #1a1a1a)",
              borderTopLeftRadius: "8px",
              borderTopRightRadius: "8px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              paddingLeft: "10px",
              boxShadow: "0 2px 4px rgba(0,0,0,0.5)",
            }}
          >
            <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#ff5f56" }} />
            <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#ffbd2e" }} />
            <div style={{ width: "10px", height: "10px", borderRadius: "50%", background: "#27c93f" }} />
          </div>

          <div style={{ padding: "5px 10px" }}>
            {displayLogs || "Logs will appear here..."}
          </div>
        </div>
      </div>
    </div>
  );
}
