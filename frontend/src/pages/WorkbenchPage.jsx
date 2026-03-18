import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { requestJson } from "../api";
import PageLayout from "../components/PageLayout";

function buildStartupCheckText(payload) {
  if (!payload?.checks?.length) {
    return "暂无启动检查结果。";
  }
  return payload.checks
    .map((item) => `[${item.status}] ${item.name}: ${item.message}`)
    .join("\n");
}

function WorkbenchContent({ selectedProjectId }) {
  const [integration, setIntegration] = useState(null);
  const [systemConfigText, setSystemConfigText] = useState("");
  const [startupChecks, setStartupChecks] = useState(null);
  const [statusText, setStatusText] = useState("等待加载配置。");

  useEffect(() => {
    let alive = true;
    Promise.all([
      requestJson("/api/integration/config"),
      requestJson("/api/config"),
      requestJson("/api/startup-checks"),
    ])
      .then(([integrationPayload, configPayload, checksPayload]) => {
        if (!alive) {
          return;
        }
        setIntegration(integrationPayload);
        setSystemConfigText(JSON.stringify(configPayload, null, 2));
        setStartupChecks(checksPayload);
        setStatusText("配置已加载，可以直接修改并保存。");
      })
      .catch((error) => {
        if (alive) {
          setStatusText(error.message || "配置加载失败。");
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  function updateIntegration(key, value) {
    setIntegration((current) => ({ ...current, [key]: value }));
  }

  async function saveIntegration() {
    const payload = {
      ...integration,
      timeout: Number(integration.timeout || 20),
      use_iam: Boolean(integration.use_iam),
      verify_ssl: Boolean(integration.verify_ssl),
      ca_bundle_path: String(integration.ca_bundle_path || "").trim(),
    };
    const saved = await requestJson("/api/integration/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setIntegration(saved);
    setStatusText("远程接口配置已保存。");
  }

  async function refreshToken() {
    await saveIntegration();
    const result = await requestJson("/api/integration/refresh-token", { method: "POST" });
    setIntegration(result.config);
    setStatusText("Token 已刷新并写回配置。");
  }

  async function saveSystemConfig() {
    const payload = JSON.parse(systemConfigText);
    const saved = await requestJson("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setSystemConfigText(JSON.stringify(saved, null, 2));
    const checks = await requestJson("/api/startup-checks");
    setStartupChecks(checks);
    setStatusText("系统生成配置已保存。");
  }

  return (
    <>
      <header className="hero">
        <div>
          <p className="eyebrow">Configuration Center</p>
          <h1>管理配置页面</h1>
          <p className="hero-copy">
            这里用于维护系统配置、远程接口参数和启动检查结果，不再承载审批执行相关内容。
          </p>
        </div>
        <div className="hero-panel">
          <p className="panel-label">Context</p>
          <h2>当前上下文</h2>
          <p className="hero-copy">
            {selectedProjectId
              ? `来源项目 ID：${selectedProjectId}，可在维护配置后返回项目详情页继续操作。`
              : "当前未绑定具体项目，可直接维护全局配置。"}
          </p>
        </div>
      </header>

      <main className="grid">
        <section className="card span-2">
          <div className="section-head">
            <div>
              <p className="panel-label">Integration</p>
              <h2>远程接口配置</h2>
            </div>
            <div className="button-row">
              <button className="ghost-button" type="button" onClick={refreshToken}>
                刷新 Token
              </button>
              <button className="ghost-button" type="button" onClick={saveIntegration}>
                保存配置
              </button>
            </div>
          </div>
          {integration ? (
            <form className="config-form">
              <label>
                <span>Base URL</span>
                <input value={integration.base_url || ""} onChange={(event) => updateIntegration("base_url", event.target.value)} />
              </label>
              <label>
                <span>Bearer Token</span>
                <input value={integration.token || ""} onChange={(event) => updateIntegration("token", event.target.value)} />
              </label>
              <label>
                <span>JSESSIONID</span>
                <input value={integration.jsessionid || ""} onChange={(event) => updateIntegration("jsessionid", event.target.value)} />
              </label>
              <label>
                <span>超时（秒）</span>
                <input
                  type="number"
                  min="1"
                  value={integration.timeout || 20}
                  onChange={(event) => updateIntegration("timeout", Number(event.target.value || 20))}
                />
              </label>
              <label>
                <span>IAM 回调 URL</span>
                <input value={integration.iam_full_url || ""} onChange={(event) => updateIntegration("iam_full_url", event.target.value)} />
              </label>
              <label>
                <span>IAM Code</span>
                <input value={integration.iam_code || ""} onChange={(event) => updateIntegration("iam_code", event.target.value)} />
              </label>
              <label>
                <span>启用 IAM 刷新</span>
                <select value={String(Boolean(integration.use_iam))} onChange={(event) => updateIntegration("use_iam", event.target.value === "true")}>
                  <option value="false">否</option>
                  <option value="true">是</option>
                </select>
              </label>
              <label>
                <span>校验证书</span>
                <select
                  value={String(Boolean(integration.verify_ssl))}
                  onChange={(event) => updateIntegration("verify_ssl", event.target.value === "true")}
                >
                  <option value="false">否</option>
                  <option value="true">是</option>
                </select>
              </label>
              <label>
                <span>CA Bundle Path</span>
                <input
                  placeholder="留空则使用 requests 默认 CA"
                  value={integration.ca_bundle_path || ""}
                  onChange={(event) => updateIntegration("ca_bundle_path", event.target.value)}
                />
              </label>
            </form>
          ) : (
            <div className="result-box">加载中...</div>
          )}
        </section>

        <section className="card">
          <div className="section-head">
            <div>
              <p className="panel-label">Startup</p>
              <h2>启动检查</h2>
            </div>
          </div>
          <div className="result-box" style={{ whiteSpace: "pre-wrap" }}>
            {buildStartupCheckText(startupChecks)}
          </div>
        </section>

        <section className="card span-2">
          <div className="section-head">
            <div>
              <p className="panel-label">System Config</p>
              <h2>系统生成配置</h2>
            </div>
            <button className="ghost-button" type="button" onClick={saveSystemConfig}>
              保存配置
            </button>
          </div>
          <label className="textarea-field">
            <textarea spellCheck="false" value={systemConfigText} onChange={(event) => setSystemConfigText(event.target.value)} />
          </label>
        </section>

        <section className="card">
          <div className="section-head">
            <div>
              <p className="panel-label">Status</p>
              <h2>操作结果</h2>
            </div>
          </div>
          <div className="result-box" style={{ whiteSpace: "pre-wrap" }}>
            {statusText}
          </div>
        </section>
      </main>
    </>
  );
}

export default function WorkbenchPage() {
  const [searchParams] = useSearchParams();
  const selectedProjectId = searchParams.get("projectId") || "";

  return (
    <PageLayout>
      <WorkbenchContent selectedProjectId={selectedProjectId} />
    </PageLayout>
  );
}
