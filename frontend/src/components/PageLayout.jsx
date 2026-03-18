import { NavLink } from "react-router-dom";

function navClassName({ isActive }) {
  return `nav-link ${isActive ? "active" : ""}`;
}

export default function PageLayout({ wide = false, children }) {
  return (
    <div className={`page-shell ${wide ? "page-shell-wide" : ""}`}>
      <nav className="top-nav">
        <NavLink end to="/approval" className={navClassName}>
          项目列表
        </NavLink>
        <NavLink to="/review-feedback" className={navClassName}>
          建议复核
        </NavLink>
        <NavLink to="/workbench" className={navClassName}>
          管理配置
        </NavLink>
        <NavLink to="/skills" className={navClassName}>
          Skill 调整
        </NavLink>
      </nav>
      {children}
    </div>
  );
}
