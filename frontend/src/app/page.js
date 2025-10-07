"use client";
import React, { useState, useEffect, useRef } from "react";

export default function Home() {
  const [jenkinsUrl, setJenkinsUrl] = useState("http://localhost:8080");
  const [jobName, setJobName] = useState("HelloJenkinsLive");
  const [buildNumber, setBuildNumber] = useState("1");
  const [username, setUsername] = useState("admin");
  const [apiToken, setApiToken] = useState("11675a28f9e88da72c7844548ac4aa14f0");
  const [logs, setLogs] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [start, setStart] = useState(0);
  const logRef = useRef(null);

  // Auto-scroll log area
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logs]);

  // poll every 1 second
  useEffect(() => {
    if (isRunning) {
      const interval = setInterval(fetchLogs, 1000);
      return () => clearInterval(interval);
    }
  }, [isRunning, start]);

  const fetchLogs = async () => {
    try {
      // const proxyUrl = `/api/jenkins/proxy?jenkinsUrl=${encodeURIComponent(
      //   jenkinsUrl
      // )}&jobName=${encodeURIComponent(jobName)}&buildNumber=${buildNumber}&start=${start}&username=${encodeURIComponent(
      //   username
      // )}&apiToken=${encodeURIComponent(apiToken)}`;

      const proxyUrl = `http://localhost:8000/api/jenkins/proxy?jenkinsUrl=${encodeURIComponent(
        jenkinsUrl
      )}&jobName=${encodeURIComponent(jobName)}&buildNumber=${buildNumber}&start=${start}&username=${encodeURIComponent(
        username
      )}&apiToken=${encodeURIComponent(apiToken)}`;

      const res = await fetch(proxyUrl);
      if (!res.ok) throw new Error(`HTTP error: ${res.status}`);

      const data = await res.json();
      
      setLogs((prev) => prev + data.logs);
      setStart(data.next_start);

      if (!data.more_data) {
        setIsRunning(false);
        console.log("All logs fetched, streaming finished");
      }
    } catch (err) {
      console.error("Error fetching logs:", err);
      setIsRunning(false);
    }
  };

  const startStreaming = () => {
    setLogs("");
    setStart(0);
    setIsRunning(true);
  };

  return (
    <div style={{ padding: 2, fontFamily: "monospace" }}>
      <h1 style={{textAlign: 'center', paddingBottom: '10px'}}>🧩 Jenkins Live Console Logs</h1>

      <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxWidth: "100%" }}>
        {/* Inputs Row */}
        <div
          style={{
            display: "flex",
            gap: "8px",
            flexWrap: "wrap",
            maxWidth: "100%",
          }}
        >
          {/* Jenkins URL */}
          <div style={{ display: "flex", flexDirection: "column", flex: "1 1 180px", minWidth: "120px" }}>
            <label style={{ fontSize: "11px", color: "#555" }}>Jenkins URL</label>
            <input
              placeholder="https://jenkins.example.com"
              value={jenkinsUrl}
              onChange={(e) => setJenkinsUrl(e.target.value)}
              style={{ padding: "4px 6px", borderRadius: "3px", border: "1px solid #ccc", fontSize: "13px" }}
            />
          </div>

          {/* Job Name */}
          <div style={{ display: "flex", flexDirection: "column", flex: "1 1 130px", minWidth: "100px" }}>
            <label style={{ fontSize: "11px", color: "#555" }}>Job Name</label>
            <input
              placeholder="MyJob"
              value={jobName}
              onChange={(e) => setJobName(e.target.value)}
              style={{ padding: "4px 6px", borderRadius: "3px", border: "1px solid #ccc", fontSize: "13px" }}
            />
          </div>

          {/* Build Number */}
          <div style={{ display: "flex", flexDirection: "column", flex: "0 1 80px", minWidth: "60px" }}>
            <label style={{ fontSize: "11px", color: "#555" }}>Build #</label>
            <input
              placeholder="42"
              value={buildNumber}
              onChange={(e) => setBuildNumber(e.target.value)}
              style={{ padding: "4px 6px", borderRadius: "3px", border: "1px solid #ccc", fontSize: "13px" }}
            />
          </div>

          {/* Username */}
          <div style={{ display: "flex", flexDirection: "column", flex: "1 1 110px", minWidth: "90px" }}>
            <label style={{ fontSize: "11px", color: "#555" }}>Username</label>
            <input
              placeholder="admin"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={{ padding: "4px 6px", borderRadius: "3px", border: "1px solid #ccc", fontSize: "13px" }}
            />
          </div>

          {/* API Token */}
          <div style={{ display: "flex", flexDirection: "column", flex: "1 1 130px", minWidth: "100px" }}>
            <label style={{ fontSize: "11px", color: "#555" }}>API Token</label>
            <input
              type="password"
              placeholder="*****"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              style={{ padding: "4px 6px", borderRadius: "3px", border: "1px solid #ccc", fontSize: "13px" }}
            />
          </div>
        </div>

        {/* Final URL + Button Row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            flexWrap: "wrap",
          }}
        >
          {/* Final URL Preview */}
          <div
            style={{
              fontSize: "12px",
              color: "#333",
              padding: "6px 10px",
              background: "#f5f5f5",
              borderRadius: "4px",
              wordBreak: "break-all",
              border: "1px solid #ccc",
              flex: 1,
            }}
          >
            <strong>Jenkins Final URL:</strong>{" "}
            {`${jenkinsUrl || "https://jenkins.example.com"}/job/${jobName || "MyJob"}/${
              buildNumber || "42"
            }/?user=${username || "admin"}&token=${apiToken ? "*".repeat(apiToken.length) : "*****"}`}
          </div>

          {/* Start Streaming Button */}
          <button
            onClick={startStreaming}
            disabled={isRunning}
            style={{
              padding: "5px 12px",
              borderRadius: "4px",
              border: "none",
              background: isRunning ? "#999" : "#007bff",
              color: "#fff",
              cursor: isRunning ? "not-allowed" : "pointer",
              fontSize: "13px",
              whiteSpace: "nowrap",
            }}
          >
            {isRunning ? "Streaming..." : "Start Streaming"}
          </button>
        </div>
      </div>

      <div
        ref={logRef}
        style={{
          marginTop: 10,
          background: "linear-gradient(180deg, #0a0a0a 0%, #000000 100%)",
          color: "#00ff7f",
          fontFamily: "'Fira Code', monospace",
          fontSize: "14px",
          lineHeight: "1.5",
          height: "570px",
          borderRadius: "8px",
          boxShadow: "0 0 10px rgba(0, 255, 100, 0.2)",
          overflowY: "auto", // vertical scroll
          overflowX: "hidden", // prevent horizontal scroll
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
          <div
            style={{
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              background: "#ff5f56",
            }}
          />
          <div
            style={{
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              background: "#ffbd2e",
            }}
          />
          <div
            style={{
              width: "10px",
              height: "10px",
              borderRadius: "50%",
              background: "#27c93f",
            }}
          />
        </div>

        <div style={{ padding: "5px 10px" }}>
          {logs || "Logs will appear here..."}
        </div>
      </div>
    </div>
  );
}
