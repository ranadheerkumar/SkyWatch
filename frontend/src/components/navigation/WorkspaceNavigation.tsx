import { useEffect, useState, type ReactNode } from "react";

type NavigationItem = {
  id: string;
  label: string;
  icon: string;
};

type NavigationGroup = {
  id: string;
  label?: string;
  items: NavigationItem[];
};

type WorkspaceNavigationProps = {
  groups: NavigationGroup[];
  activeSection: string;
  onNavigate: (section: string) => void;
  renderIcon: (name: string) => ReactNode;
  onLogout: () => void;
};

const SIDEBAR_COLLAPSED_STORAGE_KEY = "ai-qa-engine:sidebar-collapsed";

export default function WorkspaceNavigation({
  groups,
  activeSection,
  onNavigate,
  renderIcon,
  onLogout,
}: WorkspaceNavigationProps) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "true");
    } catch {
      setCollapsed(false);
    }
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(next));
      } catch {
      }
      return next;
    });
  };

  return (
    <aside className={`app-shell-sidebar ${collapsed ? "collapsed" : ""}`} aria-label="Primary navigation">
      <div className="sidebar-collapse-toolbar">
        <button
          type="button"
          className="sidebar-collapse-toggle"
          onClick={toggleCollapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          aria-controls="workspace-primary-navigation"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <span className="nav-icon"><span className="sidebar-toggle-icon">{renderIcon(collapsed ? "chevron-right" : "chevron-left")}</span></span>
        </button>
      </div>
      <nav className="sidebar-nav" id="workspace-primary-navigation">
        {groups.map((group) => (
          <div className="nav-section" key={group.id}>
            {group.items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`nav-button ${activeSection === item.id ? "active" : ""}`}
                onClick={() => onNavigate(item.id)}
                title={item.label}
                aria-label={item.label}
                aria-current={activeSection === item.id ? "page" : undefined}
              >
                <span className="nav-icon">{renderIcon(item.icon)}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-footer">
        <button type="button" className="sidebar-footer-button" onClick={onLogout} title="Sign out" aria-label="Sign out">
          <span className="nav-icon">{renderIcon("logout")}</span>
          <span>Logout</span>
        </button>
      </div>
    </aside>
  );
}
