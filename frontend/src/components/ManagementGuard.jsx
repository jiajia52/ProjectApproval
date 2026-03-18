import { useEffect, useState } from "react";
import { requestJson } from "../api";

export default function ManagementGuard({ title, description, children }) {
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginName, setLoginName] = useState("");
  const [statusText, setStatusText] = useState("正在校验管理权限。");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let alive = true;
    requestJson("/api/admin/session")
      .then((payload) => {
        if (!alive) {
          return;
        }
        const authenticatedValue = Boolean(payload?.authenticated);
        const nextUsername = String(payload?.username || "");
        setAuthenticated(authenticatedValue);
        setAuthChecked(true);
        setLoginName(nextUsername);
        setUsername(nextUsername);
        setStatusText(authenticatedValue ? `当前已使用账号 ${nextUsername} 登录。` : "请输入管理账号和密码。");
      })
      .catch((error) => {
        if (!alive) {
          return;
        }
        setAuthChecked(true);
        setStatusText(error.message || "管理权限校验失败。");
      });
    return () => {
      alive = false;
    };
  }, []);

  async function handleLogin(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const payload = await requestJson("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: username.trim(),
          password,
        }),
      });
      const nextUsername = String(payload?.username || username.trim());
      setAuthenticated(true);
      setLoginName(nextUsername);
      setPassword("");
      setStatusText(`当前已使用账号 ${nextUsername} 登录。`);
    } catch (error) {
      setStatusText(error.message || "登录失败。");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleLogout() {
    setSubmitting(true);
    try {
      await requestJson("/api/admin/logout", { method: "POST" });
      setAuthenticated(false);
      setLoginName("");
      setPassword("");
      setStatusText("已退出管理界面，请重新登录。");
    } catch (error) {
      setStatusText(error.message || "退出登录失败。");
    } finally {
      setSubmitting(false);
    }
  }

  if (!authChecked) {
    return (
      <section className="management-auth-shell">
        <div className="management-auth-card">
          <p className="eyebrow">Management Access</p>
          <h1>{title}</h1>
          <p className="hero-copy">{statusText}</p>
        </div>
      </section>
    );
  }

  if (authenticated) {
    if (typeof children === "function") {
      return children({ username: loginName, onLogout: handleLogout, logoutPending: submitting });
    }
    return children;
  }

  return (
    <section className="management-auth-shell">
      <div className="management-auth-card">
        <p className="eyebrow">Management Access</p>
        <h1>{title}</h1>
        <p className="hero-copy">{description}</p>
        <form className="management-auth-form" onSubmit={handleLogin}>
          <label>
            <span>账号</span>
            <input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} />
          </label>
          <label>
            <span>密码</span>
            <input
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          <div className="button-row">
            <button className="primary-button" type="submit" disabled={submitting || !username.trim() || !password}>
              {submitting ? "登录中..." : "进入管理界面"}
            </button>
          </div>
        </form>
        <div className="result-box">{statusText}</div>
      </div>
    </section>
  );
}
