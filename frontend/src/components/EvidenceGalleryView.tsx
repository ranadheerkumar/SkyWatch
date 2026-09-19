"use client";

import { useEffect, useState } from "react";
import { apiFetchBlob } from "../lib/api";

export type EvidenceItem = {
  run_id: string;
  application_id: number;
  label: string;
  file_url: string;
  created_at?: string | null;
  status: string;
};

interface EvidenceGalleryViewProps {
  appName: string;
  token: string;
  screenshots: EvidenceItem[];
  videos: EvidenceItem[];
  onRefresh: () => Promise<void>;
  refreshing: boolean;
}

function ProtectedEvidenceMedia({
  item,
  token,
  className,
  video = false,
  style,
}: {
  item: EvidenceItem;
  token: string;
  className: string;
  video?: boolean;
  style?: React.CSSProperties;
}) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    setUrl("");
    setError("");
    if (!token) {
      setError("Sign in to view evidence.");
      return () => undefined;
    }

    void apiFetchBlob(item.file_url, token)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((loadError) => {
        if (!cancelled) setError(loadError instanceof Error ? loadError.message : "Unable to load evidence.");
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [item.file_url, token]);

  if (error) return <span className="muted">{error}</span>;
  if (!url) return <span className="muted">Loading evidence...</span>;
  if (video) {
    return <video controls preload="metadata" src={url} className={className} style={style}>Your browser does not support HTML5 video playback.</video>;
  }
  return <img src={url} alt={item.label} className={className} style={style} />;
}

export default function EvidenceGalleryView({
  appName,
  token,
  screenshots,
  videos,
  onRefresh,
  refreshing,
}: EvidenceGalleryViewProps) {
  const [activeTab, setActiveTab] = useState<"screenshots" | "videos">("screenshots");
  const [selectedImage, setSelectedImage] = useState<EvidenceItem | null>(null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      <div className="evidence-header-bar">
        <div>
          <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 700, color: "var(--text-primary)" }}>
            Visual Evidence Gallery · {appName}
          </h2>
          <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--text-secondary)" }}>
            Browse step-by-step full-page screenshots, assertion validation captures, and complete browser video recordings.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <div className="evidence-tab-group">
            <button
              type="button"
              onClick={() => setActiveTab("screenshots")}
              className={`evidence-tab-btn ${activeTab === "screenshots" ? "active" : ""}`}
            >
              Screenshots ({screenshots.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("videos")}
              className={`evidence-tab-btn ${activeTab === "videos" ? "active" : ""}`}
            >
              Video Recordings ({videos.length})
            </button>
          </div>
          <button
            type="button"
            onClick={() => void onRefresh()}
            disabled={refreshing}
            className="btn btn-secondary btn-sm"
          >
            {refreshing ? "Refreshing..." : "Refresh Gallery"}
          </button>
        </div>
      </div>

      {activeTab === "screenshots" && (
        <div>
          {screenshots.length === 0 ? (
            <div className="panel" style={{ padding: "40px", textAlign: "center", color: "var(--text-secondary)" }}>
              No execution screenshots captured yet. Execute tests with "Capture screenshot" enabled.
            </div>
          ) : (
            <div className="evidence-grid">
              {screenshots.map((item, idx) => (
                <div key={`ss-${item.run_id}-${idx}`} className="evidence-card">
                  <div
                    className="evidence-thumb-wrapper"
                    onClick={() => setSelectedImage(item)}
                    title="Click to expand image"
                  >
                    <ProtectedEvidenceMedia item={item} token={token} className="evidence-thumb-img" />
                  </div>
                  <div className="evidence-card-body">
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontFamily: "var(--font-code)", fontSize: "11px", color: "var(--text-secondary)" }}>
                          Run: {item.run_id.slice(0, 8)}
                        </span>
                        <span style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: "4px",
                          background: item.status === "passed" ? "rgba(22, 163, 74, 0.15)" : "rgba(220, 38, 38, 0.15)",
                          color: item.status === "passed" ? "var(--success-dark)" : "var(--error-dark)",
                        }}>
                          {item.status.toUpperCase()}
                        </span>
                      </div>
                      <div style={{ fontWeight: 600, fontSize: "13px", color: "var(--text-primary)", marginTop: "4px" }}>
                        {item.label}
                      </div>
                    </div>
                    {item.created_at && (
                      <div style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>
                        {new Date(item.created_at).toLocaleString()}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "videos" && (
        <div>
          {videos.length === 0 ? (
            <div className="panel" style={{ padding: "40px", textAlign: "center", color: "var(--text-secondary)" }}>
              No execution video recordings available yet. Enable "Record video" during test runs.
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: "20px" }}>
              {videos.map((item, idx) => (
                <div key={`vid-${item.run_id}-${idx}`} className="evidence-card" style={{ padding: "16px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <div>
                      <h4 style={{ margin: 0, fontSize: "14px", fontWeight: 700, color: "var(--text-primary)" }}>{item.label}</h4>
                      <span style={{ fontFamily: "var(--font-code)", fontSize: "11px", color: "var(--text-secondary)" }}>
                        Run: {item.run_id.slice(0, 10)}
                      </span>
                    </div>
                    <span style={{
                      fontSize: "10px",
                      fontWeight: 700,
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: item.status === "passed" ? "rgba(22, 163, 74, 0.15)" : "rgba(220, 38, 38, 0.15)",
                      color: item.status === "passed" ? "var(--success-dark)" : "var(--error-dark)",
                    }}>
                      {item.status.toUpperCase()}
                    </span>
                  </div>
                  <div style={{ aspectRatio: "16 / 9", background: "#000000", borderRadius: "6px", overflow: "hidden" }}>
                    <ProtectedEvidenceMedia item={item} token={token} className="evidence-gallery-video" video style={{ width: "100%", height: "100%" }} />
                  </div>
                  {item.created_at && (
                    <div style={{ fontSize: "11px", color: "var(--text-tertiary)", marginTop: "8px", textAlign: "right" }}>
                      {new Date(item.created_at).toLocaleString()}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Lightbox image preview */}
      {selectedImage && (
        <div className="lightbox-overlay" onClick={() => setSelectedImage(null)}>
          <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
            <div className="lightbox-header">
              <span>{selectedImage.label} · Run: {selectedImage.run_id}</span>
              <button
                type="button"
                onClick={() => setSelectedImage(null)}
                className="btn-ghost btn-xs"
                style={{ color: "#ffffff", border: "none" }}
              >
                ✕ Close
              </button>
            </div>
            <div className="lightbox-body">
              <ProtectedEvidenceMedia item={selectedImage} token={token} className="lightbox-img" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
