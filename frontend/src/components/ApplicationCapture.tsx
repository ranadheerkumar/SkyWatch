"use client";

import { useRef, useState } from "react";
import { apiFetch } from "../lib/api";
import { useAuth } from "../hooks/useAuth";
import { normalizeHttpUrl, requiredField } from "../lib/validations";

type Platform = "Web" | "Android" | "iOS";

const PLATFORM_OPTIONS: Array<{ id: Platform; label: string; description: string }> = [
  { id: "Web", label: "Web", description: "Connect a browser URL with login context." },
  { id: "Android", label: "Android", description: "Upload APK builds for mobile discovery." },
  { id: "iOS", label: "iOS", description: "Upload IPA builds for iOS validation." },
];

function PlatformIcon({ platform }: { platform: Platform }) {
  if (platform === "Web") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.8 2.5 4.5 5.6 4.5 9s-1.7 6.5-4.5 9c-2.8-2.5-4.5-5.6-4.5-9s1.7-6.5 4.5-9z" />
      </svg>
    );
  }

  if (platform === "Android") {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 9h10a1 1 0 0 1 1 1v7a3 3 0 0 1-3 3h-6a3 3 0 0 1-3-3v-7a1 1 0 0 1 1-1z" />
        <path d="M9 6l-1.5-2M15 6l1.5-2M9.5 12h.01M14.5 12h.01" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="6.5" y="4.5" width="11" height="15" rx="2.2" />
      <path d="M11 7h2M10 17h4" />
    </svg>
  );
}

type ApplicationCaptureProps = {
  onSaved: (savedApplicationName?: string) => void;
};

export default function ApplicationCapture({ onSaved }: ApplicationCaptureProps) {
  const { token } = useAuth();
  const [platform, setPlatform] = useState<Platform>("Web");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [artifact, setArtifact] = useState<File | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const selectPlatform = (nextPlatform: Platform) => {
    setPlatform(nextPlatform);
    setError("");
    setArtifact(null);
    setUrl("");
  };

  const acceptFile = (file?: File) => {
    if (!file) return;
    const extension = file.name.toLowerCase().split(".").pop();
    const expected = platform === "Android" ? "apk" : "ipa";
    if (extension !== expected) {
      setError(`Choose a .${expected} file for ${platform}.`);
      return;
    }
    setArtifact(file);
    setError("");
  };

  const save = async () => {
    const nameError = requiredField(name, "Application name");
    if (nameError) return setError(nameError);
    const normalizedUrl = platform === "Web" ? normalizeHttpUrl(url) : null;
    if (platform === "Web") {
      if (!normalizedUrl) return setError("Enter a complete HTTP(S) URL.");
    } else if (!artifact) {
      return setError(`Drop a ${platform === "Android" ? ".apk" : ".ipa"} file to continue.`);
    }

    try {
      if (platform === "Web") {
        await apiFetch("/api/v1/applications", {
          method: "POST",
          body: JSON.stringify({ name: name.trim(), platform: "web", target: normalizedUrl }),
        }, token);
      } else {
        const formData = new FormData();
        formData.append("name", name.trim());
        formData.append("platform", platform.toLowerCase());
        formData.append("file", artifact as File);
        await apiFetch("/api/v1/applications/mobile", { method: "POST", body: formData }, token);
      }
      setName("");
      setUrl("");
      setArtifact(null);
      setError("");
      onSaved(name.trim());
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to save application.");
    }
  };

  return <div className="panel capture-card">
    <div className="capture-copy"><h2>Add an application</h2><p>Bring a URL or mobile build into the QA workspace.</p></div>
    <div className="platform-tabs">
      {PLATFORM_OPTIONS.map((item) => (
        <button
          type="button"
          className={platform === item.id ? "platform-tab active" : "platform-tab"}
          onClick={() => selectPlatform(item.id)}
          key={item.id}
          aria-pressed={platform === item.id}
        >
          <span className="platform-tab-icon"><PlatformIcon platform={item.id} /></span>
          <span className="platform-tab-copy">
            <strong>{item.label}</strong>
            <small>{item.description}</small>
          </span>
        </button>
      ))}
    </div>
    <label className="capture-label">Application name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Checkout portal" /></label>
    {platform === "Web" ? <label className="capture-label">Web application URL<input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://your-app.example.com" /></label> : <div className="capture-label">{platform} application package<div className="drop-zone" onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); acceptFile(event.dataTransfer.files[0]); }} onClick={() => inputRef.current?.click()}><input ref={inputRef} hidden type="file" accept={platform === "Android" ? ".apk,application/vnd.android.package-archive" : ".ipa,application/octet-stream"} onChange={(event) => acceptFile(event.target.files?.[0])} />{artifact ? <strong>{artifact.name}</strong> : <><strong>Drop your .{platform === "Android" ? "apk" : "ipa"} here</strong><span>or browse from your computer</span></>}</div></div>}
    {error && <p className="form-error">{error}</p>}
    <button type="button" className="primary capture-submit" onClick={save}>Save application</button>
  </div>;
}
