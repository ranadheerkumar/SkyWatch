import type { AppIconName } from "../../types";

export default function AppIcon({ name, className = "" }: { name: AppIconName; className?: string }) {
  const strokeProps = { stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", fill: "none" } as const;
  if (name === "overview") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <rect x="3" y="3" width="8" height="8" rx="1.5" {...strokeProps} />
        <rect x="13" y="3" width="8" height="6" rx="1.5" {...strokeProps} />
        <rect x="3" y="13" width="8" height="8" rx="1.5" {...strokeProps} />
        <rect x="13" y="11" width="8" height="10" rx="1.5" {...strokeProps} />
      </svg>
    );
  }

  if (name === "projects") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="M3 7.5h6l2 2h10v8a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z" {...strokeProps} />
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2" {...strokeProps} />
      </svg>
    );
  }
  if (name === "applications") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <rect x="3" y="4" width="18" height="12" rx="2" {...strokeProps} />
        <path d="M9 20h6M12 16v4" {...strokeProps} />
      </svg>
    );
  }
  if (name === "cases") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <rect x="6" y="3.5" width="12" height="17" rx="2" {...strokeProps} />
        <path d="M9 2.5h6v3H9zM9 11l2 2 4-4M9 17h6" {...strokeProps} />
      </svg>
    );
  }
  if (name === "execution") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="9" {...strokeProps} />
        <path d="m10 8 6 4-6 4z" fill="currentColor" stroke="none" />
      </svg>
    );
  }
  if (name === "defects" || name === "warning") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="M12 3.5 2.7 20h18.6z" {...strokeProps} />
        <path d="M12 9v5M12 17.4h.01" {...strokeProps} />
      </svg>
    );
  }
  if (name === "suites") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="M4 7h16l-8 4zM4 12l8 4 8-4M4 17l8 4 8-4" {...strokeProps} />
      </svg>
    );
  }
  if (name === "reports") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="M4 20h16M7 16v-4M12 16V8M17 16v-7" {...strokeProps} />
      </svg>
    );
  }
  if (name === "ai") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="m12 3 1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8zM19 14l.9 2.1L22 17l-2.1.9L19 20l-.9-2.1L16 17l2.1-.9zM5 14l.7 1.5L7 16l-1.3.5L5 18l-.7-1.5L3 16l1.3-.5z" {...strokeProps} />
      </svg>
    );
  }
  if (name === "recommendations") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="M8.5 14.5a6 6 0 1 1 7 0c-.8.7-1.3 1.4-1.5 2.5h-4c-.2-1.1-.7-1.8-1.5-2.5z" {...strokeProps} />
        <path d="M9 20h6M10 22h4M12 2v1.5M4.9 4.9 6 6M19.1 4.9 18 6" {...strokeProps} />
      </svg>
    );
  }
  if (name === "map") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21" {...strokeProps} />
        <line x1="9" y1="3" x2="9" y2="18" {...strokeProps} />
        <line x1="15" y1="6" x2="15" y2="21" {...strokeProps} />
      </svg>
    );
  }
  if (name === "audit") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="m12 3 7 3v5c0 4.4-2.9 8.2-7 10-4.1-1.8-7-5.6-7-10V6z" {...strokeProps} />
        <path d="m8.5 12 2.2 2.2 4.8-4.8" {...strokeProps} />
      </svg>
    );
  }
  if (name === "settings") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="3.2" {...strokeProps} />
        <path d="M12 2.8v2.4M12 18.8v2.4M21.2 12h-2.4M5.2 12H2.8M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7M18.5 18.5l-1.7-1.7M7.2 7.2 5.5 5.5" {...strokeProps} />
      </svg>
    );
  }
  if (name === "logout") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M14 12H4m10-4 4 4-4 4" {...strokeProps} />
      </svg>
    );
  }
  if (name === "help") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="9" {...strokeProps} />
        <path d="M9.7 9a2.6 2.6 0 1 1 4.8 1.4c-.5.7-1.4 1.2-2.1 1.8-.5.4-.9.9-.9 1.8M12 17.2h.01" {...strokeProps} />
      </svg>
    );
  }
  if (name === "notifications") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d="M6 9a6 6 0 1 1 12 0v4l1.8 2.5H4.2L6 13zM10 18a2 2 0 0 0 4 0" {...strokeProps} />
      </svg>
    );
  }
  if (name === "menu" || name === "close") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        {name === "menu" ? <path d="M4 7h16M4 12h16M4 17h16" {...strokeProps} /> : <path d="m6 6 12 12M18 6 6 18" {...strokeProps} />}
      </svg>
    );
  }
  if (name === "chevron-left" || name === "chevron-right") {
    return (
      <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
        <path d={name === "chevron-left" ? "m14.5 5-7 7 7 7" : "m9.5 5 7 7-7 7"} {...strokeProps} />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className={`app-icon ${className}`.trim()} aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="9" {...strokeProps} />
      <path d="M12 7v5l3 2" {...strokeProps} />
    </svg>
  );
}
