"use client";

import { useEffect, useRef, type ReactNode } from "react";
import AppIcon from "./AppIcon";
import TractorSupplyLogo from "./TractorSupplyLogo";
import WorkspaceNavigation from "./WorkspaceNavigation";
import ErrorBoundary from "../ErrorBoundary";
import type { AppIconName, Application, Section, WorkspaceProject } from "../../types";
import { APP_VERSION } from "../../lib/appVersion";

type NavigationGroup = {
  id: string;
  label?: string;
  items: Array<{ id: Section; label: string; icon: AppIconName }>;
};

type WorkspaceShellProps = {
  children: ReactNode;
  brandTitle: string;
  section: Section;
  apps: Application[];
  selectedApplication: Application | null;
  projects?: WorkspaceProject[];
  selectedProjectId?: string;
  onSelectProject?: (projectId: string) => void;
  onCreateProject?: () => void;
  onCreateApplication?: () => void;
  mobileNavOpen: boolean;
  navigationGroups: NavigationGroup[];
  toast?: string;
  onMobileNavOpenChange: (open: boolean) => void;
  onSelectApplication: (name: string) => void;
  onNavigate: (section: Section) => void;
  onLogout: () => void;
  onNotify: (message: string) => void;
};

export default function WorkspaceShell({
  children,
  brandTitle,
  section,
  apps,
  selectedApplication,
  projects = [],
  selectedProjectId,
  onSelectProject,
  onCreateProject,
  onCreateApplication,
  mobileNavOpen,
  navigationGroups,
  toast,
  onMobileNavOpenChange,
  onSelectApplication,
  onNavigate,
  onLogout,
  onNotify,
}: WorkspaceShellProps) {
  const mobileNavToggleRef = useRef<HTMLButtonElement>(null);
  const firstMobileNavItemRef = useRef<HTMLButtonElement>(null);
  const contentRef = useRef<HTMLElement>(null);
  const sectionLabel = navigationGroups
    .flatMap((group) => group.items)
    .find((item) => item.id === section)?.label ?? "Overview";

  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? projects[0] ?? null;

  useEffect(() => {
    if (!mobileNavOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => firstMobileNavItemRef.current?.focus(), 0);
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      onMobileNavOpenChange(false);
      window.setTimeout(() => mobileNavToggleRef.current?.focus(), 0);
    };

    window.addEventListener("keydown", handleEscape);
    return () => {
      window.clearTimeout(focusTimer);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [mobileNavOpen]);

  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [section]);

  const closeMobileNavigation = (restoreFocus = false) => {
    onMobileNavOpenChange(false);
    if (restoreFocus) window.setTimeout(() => mobileNavToggleRef.current?.focus(), 0);
  };

  return (
    <div className={`app-shell ${mobileNavOpen ? "mobile-nav-active" : ""}`}>
      <button
        type="button"
        className={`mobile-nav-overlay ${mobileNavOpen ? "open" : ""}`}
        aria-label="Close navigation menu"
        aria-hidden={!mobileNavOpen}
        onClick={() => closeMobileNavigation(true)}
        tabIndex={mobileNavOpen ? 0 : -1}
      />

      <header className="app-header">
        <div className="header-left">
          <button
            ref={mobileNavToggleRef}
            type="button"
            className="mobile-menu-toggle"
            aria-label={mobileNavOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={mobileNavOpen}
            aria-controls="mobile-navigation-drawer"
            onClick={() => onMobileNavOpenChange(!mobileNavOpen)}
          >
            <AppIcon name={mobileNavOpen ? "close" : "menu"} />
          </button>
          <div className="mobile-header-context">
            <TractorSupplyLogo variant="header" showCopy={false} className="mobile-header-brand-logo" />
            <div className="mobile-header-context-copy">
              <strong>{brandTitle}</strong>
              <small>
                {selectedProject?.name ? `${selectedProject.name} › ` : ""}
                {selectedApplication?.name ? `${selectedApplication.name} › ` : ""}
                {sectionLabel}
              </small>
            </div>
          </div>
          <div className="desktop-header-brand">
            <TractorSupplyLogo variant="header" showCopy={false} className="header-brand-logo" />
          </div>

          {/* Desktop Dual Hierarchy Bar (Project -> Application -> Section) */}
          <div className="header-hierarchy-bar">
            {projects.length > 0 ? (
              <div className="header-hierarchy-group">
                <label className="header-hierarchy-item" htmlFor="header-project-selector" title="Active QA Project Scope">
                  <span className="hierarchy-icon" aria-hidden="true">📁</span>
                  <span className="hierarchy-label">Project</span>
                  <select
                    id="header-project-selector"
                    value={selectedProjectId ?? projects[0]?.id ?? ""}
                    onChange={(event) => onSelectProject?.(event.target.value)}
                  >
                    {projects.map((p) => (
                      <option key={`header-proj-${p.id}`} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </label>
                {onCreateProject && (
                  <button
                    type="button"
                    className="hierarchy-action-btn"
                    onClick={onCreateProject}
                    title="Create new project"
                    aria-label="Create new project"
                  >
                    +
                  </button>
                )}
              </div>
            ) : onCreateProject ? (
              <button
                type="button"
                className="hierarchy-action-btn-pill"
                onClick={onCreateProject}
                title="Create new project"
              >
                + Project
              </button>
            ) : null}

            <span className="header-hierarchy-sep" aria-hidden="true">›</span>

            {apps.length > 0 ? (
              <div className="header-hierarchy-group">
                <label className="header-hierarchy-item" htmlFor="header-application-selector" title="Active Target Application Scope">
                  <span className="hierarchy-icon" aria-hidden="true">💻</span>
                  <span className="hierarchy-label">App</span>
                  <select
                    id="header-application-selector"
                    value={selectedApplication?.name ?? ""}
                    onChange={(event) => onSelectApplication(event.target.value)}
                  >
                    {apps.map((item) => (
                      <option key={`header-app-${item.id}`} value={item.name}>{item.name}</option>
                    ))}
                  </select>
                </label>
                {onCreateApplication && (
                  <button
                    type="button"
                    className="hierarchy-action-btn"
                    onClick={onCreateApplication}
                    title="Add target application"
                    aria-label="Add target application"
                  >
                    +
                  </button>
                )}
              </div>
            ) : onCreateApplication ? (
              <button
                type="button"
                className="hierarchy-action-btn-pill"
                onClick={onCreateApplication}
                title="Add target application"
              >
                + App
              </button>
            ) : null}

            <span className="header-hierarchy-sep" aria-hidden="true">›</span>

            <div className="header-hierarchy-section-badge" title={`Current Workspace View: ${sectionLabel}`}>
              <span className="section-dot" aria-hidden="true" />
              <strong>{sectionLabel}</strong>
            </div>
          </div>

          <span className="header-app-version" aria-label={`Application version ${APP_VERSION}`}>
            v{APP_VERSION}
          </span>
        </div>

        <div className="header-actions">
          <button type="button" className="header-action-button desktop-only-action" onClick={() => onNotify("Help center opened")} title="Help" aria-label="Help">
            <AppIcon name="help" />
          </button>
          <button type="button" className="header-action-button desktop-only-action" onClick={() => onNotify("No new notifications")} title="Notifications" aria-label="Notifications">
            <AppIcon name="notifications" />
          </button>
          <button type="button" className="header-user-profile" onClick={() => onNotify("Admin profile opened")} title="Profile menu">
            <div className="user-avatar">AD</div>
            <div className="user-info">
              <span className="user-name">Admin</span>
              <span className="user-role">QA Lead</span>
            </div>
          </button>
        </div>
      </header>

      <aside
        id="mobile-navigation-drawer"
        className={`mobile-nav-drawer ${mobileNavOpen ? "open" : ""}`}
        role="dialog"
        aria-modal={mobileNavOpen ? true : undefined}
        aria-hidden={!mobileNavOpen}
        aria-label="Mobile navigation drawer"
      >
        <div className="mobile-nav-drawer-head">
          <div className="mobile-nav-brand"><TractorSupplyLogo variant="drawer" showCopy={false} /></div>
          <button type="button" className="mobile-nav-close" onClick={() => closeMobileNavigation(true)} aria-label="Close navigation menu">
            <AppIcon name="close" />
          </button>
        </div>
        <nav className="mobile-nav-drawer-body" aria-label="Mobile navigation">
          {navigationGroups.map((group, groupIndex) => (
            <div className="nav-section" key={`mobile-nav-group-${group.id}`}>
              {group.items.map((item, itemIndex) => (
                <button
                  key={`mobile-nav-${item.id}`}
                  ref={groupIndex === 0 && itemIndex === 0 ? firstMobileNavItemRef : undefined}
                  type="button"
                  className={`nav-button ${section === item.id ? "active" : ""}`}
                  onClick={() => { closeMobileNavigation(false); onNavigate(item.id); }}
                  aria-current={section === item.id ? "page" : undefined}
                >
                  <span className="nav-icon"><AppIcon name={item.icon} /></span>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="mobile-nav-drawer-foot">
          <button type="button" className="sidebar-footer-button" onClick={() => { closeMobileNavigation(false); onLogout(); }}>
            <span className="nav-icon"><AppIcon name="logout" /></span>
            <span>Logout</span>
          </button>
        </div>
      </aside>

      <div className="app-shell-body">
        <WorkspaceNavigation
          groups={navigationGroups}
          activeSection={section}
          onNavigate={(nextSection) => onNavigate(nextSection as Section)}
          renderIcon={(name) => <AppIcon name={name as AppIconName} />}
          onLogout={onLogout}
        />
        <div className="app-shell-main">
          <main className="content" id="main-content" ref={contentRef}>
            <div className="page-content-wrapper">
              <ErrorBoundary fallbackTitle={`Workspace Error (${sectionLabel})`}>
                {children}
              </ErrorBoundary>
            </div>
          </main>
        </div>
      </div>

      {toast && <div className="toast" role="status" aria-live="polite">{toast}</div>}
    </div>
  );
}
