import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

function navClassName(isActive) {
  return `nav-link ${isActive ? "active" : ""}`;
}

function normalizeScene(scene) {
  const normalized = String(scene || "").trim().toLowerCase();
  if (normalized === "acceptance") {
    return "acceptance";
  }
  if (normalized === "task_order" || normalized === "task-order" || normalized === "taskorder") {
    return "task_order";
  }
  return "initiation";
}

export default function PageLayout({ wide = false, scene = "", section = "", children }) {
  const location = useLocation();
  const menuRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState("");
  const normalizedScene = scene ? normalizeScene(scene) : "";
  const pathname = location.pathname || "";

  const menuItems = [
    {
      key: "initiation",
      label: "立项",
      active: pathname.startsWith("/initiation") || (pathname.startsWith("/project/") && normalizedScene === "initiation"),
      links: [
        { to: "/initiation", label: "首页", active: pathname === "/initiation" },
        {
          to: "/initiation/projects",
          label: "列表",
          active: pathname.startsWith("/initiation/projects") || (pathname.startsWith("/project/") && normalizedScene === "initiation" && section === "projects"),
        },
        { to: "/initiation/review-feedback", label: "复核", active: pathname.startsWith("/initiation/review-feedback") },
        { to: "/initiation/skills", label: "Skill", active: pathname.startsWith("/initiation/skills") },
      ],
    },
    {
      key: "acceptance",
      label: "验收",
      active: pathname.startsWith("/acceptance") || (pathname.startsWith("/project/") && normalizedScene === "acceptance"),
      links: [
        { to: "/acceptance", label: "首页", active: pathname === "/acceptance" },
        {
          to: "/acceptance/projects",
          label: "列表",
          active: pathname.startsWith("/acceptance/projects") || (pathname.startsWith("/project/") && normalizedScene === "acceptance" && section === "projects"),
        },
        { to: "/acceptance/review-feedback", label: "复核", active: pathname.startsWith("/acceptance/review-feedback") },
        { to: "/acceptance/skills", label: "Skill", active: pathname.startsWith("/acceptance/skills") },
      ],
    },
    {
      key: "task_order",
      label: "任务单",
      active: pathname.startsWith("/task-order") || (pathname.startsWith("/project/") && normalizedScene === "task_order"),
      links: [
        { to: "/task-order", label: "首页", active: pathname === "/task-order" },
        {
          to: "/task-order/projects",
          label: "列表",
          active: pathname.startsWith("/task-order/projects") || (pathname.startsWith("/project/") && normalizedScene === "task_order" && section === "projects"),
        },
        { to: "/task-order/review-feedback", label: "复核", active: pathname.startsWith("/task-order/review-feedback") },
        { to: "/task-order/skills", label: "SKILL", active: pathname.startsWith("/task-order/skills") },
      ],
    },
    {
      key: "management",
      label: "管理",
      active: pathname.startsWith("/workbench"),
      links: [{ to: "/workbench", label: "工作台", active: pathname.startsWith("/workbench") }],
    },
  ];

  useEffect(() => {
    const currentGroup = menuItems.find((item) => item.active)?.key || "";
    setActiveGroup(currentGroup);
    setMenuOpen(false);
  }, [pathname, location.search]);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  const hasActiveGroup = menuItems.some((item) => item.active);

  return (
    <div className={`page-shell ${wide ? "page-shell-wide" : ""}`}>
      <nav className="top-nav">
        <div className="nav-menu-shell" ref={menuRef}>
          <button
            className={`nav-menu-button ${menuOpen || hasActiveGroup ? "active" : ""}`}
            type="button"
            onClick={() => {
              setMenuOpen((current) => {
                const nextOpen = !current;
                if (nextOpen && !activeGroup) {
                  setActiveGroup(menuItems.find((item) => item.active)?.key || menuItems[0]?.key || "");
                }
                return nextOpen;
              });
            }}
            aria-label="打开菜单"
          >
            <span className="nav-menu-icon" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
          </button>
          {menuOpen ? (
            <div className="nav-menu-dropdown nav-menu-dropdown-wide">
              {menuItems.map((group) => (
                <section key={group.key} className="nav-menu-group">
                  <button
                    type="button"
                    className={`nav-menu-group-title ${group.active ? "active" : ""} ${activeGroup === group.key ? "open" : ""}`}
                    onClick={() => setActiveGroup((current) => (current === group.key ? "" : group.key))}
                  >
                    <span>{group.label}</span>
                    <span className="nav-menu-group-arrow" aria-hidden="true">
                      {activeGroup === group.key ? "−" : "+"}
                    </span>
                  </button>
                  {activeGroup === group.key ? (
                    <div className="nav-menu-group-links">
                      {group.links.map((link) => (
                        <NavLink key={link.to} to={link.to} className={navClassName(link.active)}>
                          {link.label}
                        </NavLink>
                      ))}
                    </div>
                  ) : null}
                </section>
              ))}
            </div>
          ) : null}
        </div>
      </nav>
      {children}
    </div>
  );
}
