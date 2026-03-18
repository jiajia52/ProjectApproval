const workbenchState = {
  integration: null,
  rules: null,
  selectedProjectId: "",
};

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) {
    const message = payload?.detail || payload?.message || text || "请求失败。";
    throw new Error(message);
  }
  return payload;
}

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function setResult(message) {
  document.getElementById("approval-result").textContent = message;
}

function fillCategorySelect(rules) {
  const select = document.getElementById("approval-category");
  const queryCategory = getQueryParam("category");
  select.innerHTML = "";
  rules.categories.forEach((category, index) => {
    const option = document.createElement("option");
    option.value = category.name;
    option.textContent = `${category.name} / ${category.group}`;
    option.selected = category.name === queryCategory || (!queryCategory && index === 0);
    select.appendChild(option);
  });
}

function fillIntegration(config) {
  document.getElementById("integration_base_url").value = config.base_url || "";
  document.getElementById("integration_token").value = config.token || "";
  document.getElementById("integration_jsessionid").value = config.jsessionid || "";
  document.getElementById("integration_timeout").value = config.timeout || 20;
  document.getElementById("integration_iam_full_url").value = config.iam_full_url || "";
  document.getElementById("integration_iam_code").value = config.iam_code || "";
  document.getElementById("integration_use_iam").value = String(Boolean(config.use_iam));
  document.getElementById("integration_verify_ssl").value = String(Boolean(config.verify_ssl));
  document.getElementById("integration_ca_bundle_path").value = config.ca_bundle_path || "";
}

function collectIntegration() {
  return {
    ...workbenchState.integration,
    base_url: document.getElementById("integration_base_url").value.trim(),
    token: document.getElementById("integration_token").value.trim(),
    jsessionid: document.getElementById("integration_jsessionid").value.trim(),
    timeout: Number(document.getElementById("integration_timeout").value || 20),
    iam_full_url: document.getElementById("integration_iam_full_url").value.trim(),
    iam_code: document.getElementById("integration_iam_code").value.trim(),
    use_iam: document.getElementById("integration_use_iam").value === "true",
    verify_ssl: document.getElementById("integration_verify_ssl").value === "true",
    ca_bundle_path: document.getElementById("integration_ca_bundle_path").value.trim(),
  };
}

function formatApprovalResult(result) {
  if (result.baseline) {
    const risks = (result.risks || []).slice(0, 8).map((item) => `- ${item}`);
    const runDir = result.run_dir ? [`审批落盘: ${result.run_dir}`] : [];
    return [
      `项目: ${result.project_name}`,
      `品类: ${result.category}`,
      `结论: ${result.decision}`,
      ...runDir,
      "",
      "风险摘要:",
      ...(risks.length ? risks : ["- 无"]),
    ].join("\n");
  }

  const head = [
    `项目: ${result.project_name}`,
    `品类: ${result.category}`,
    `结论: ${result.decision}`,
    `评分: ${result.score}`,
    `失败规则: ${result.statistics.failed_rules}`,
  ];
  const findings = result.findings
    .slice(0, 10)
    .map((item) => `- [${item.severity}] ${item.review_point}/${item.review_content}: ${item.message}`);
  return [...head, "", "问题摘要:", ...findings].join("\n");
}

function syncSelectedProjectMeta() {
  const label = workbenchState.selectedProjectId
    ? `当前项目 ID: ${workbenchState.selectedProjectId}\n接口记录目录: runtime/api_result/projects/${workbenchState.selectedProjectId}/`
    : "未指定远程项目。";
  document.getElementById("selected-project-meta").textContent = label;
}

async function saveIntegration() {
  workbenchState.integration = await requestJson("/api/integration/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectIntegration()),
  });
  fillIntegration(workbenchState.integration);
  setResult("远程接口配置已保存。");
}

async function refreshToken() {
  await saveIntegration();
  const result = await requestJson("/api/integration/refresh-token", { method: "POST" });
  workbenchState.integration = result.config;
  fillIntegration(result.config);
  setResult("Token 已刷新并写回配置。");
}

async function loadSample() {
  const sample = await requestJson("/api/approval/sample");
  document.getElementById("approval-category").value = sample.category;
  document.getElementById("approval-payload").value = JSON.stringify(sample, null, 2);
  setResult("已加载审批样例。");
}

async function loadRemoteProject() {
  if (!workbenchState.selectedProjectId) {
    throw new Error("缺少 projectId，请从项目详情页或项目列表页进入。");
  }
  const category = document.getElementById("approval-category").value;
  const documentPayload = await requestJson(`/api/projects/${encodeURIComponent(workbenchState.selectedProjectId)}/document?category=${encodeURIComponent(category)}`);
  document.getElementById("approval-payload").value = JSON.stringify(documentPayload, null, 2);
  setResult(`已载入远程项目，并映射为审批 JSON。\n接口记录目录: runtime/api_result/projects/${workbenchState.selectedProjectId}/`);
}

async function approveCurrentPayload() {
  const category = document.getElementById("approval-category").value;
  const documentPayload = JSON.parse(document.getElementById("approval-payload").value);
  const result = await requestJson("/api/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, document: documentPayload }),
  });
  setResult(formatApprovalResult(result));
}

async function approveGeneratedProject() {
  const category = document.getElementById("approval-category").value;
  const result = await requestJson("/api/approve/generated-project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category }),
  });
  setResult(formatApprovalResult(result));
}

async function approveRemoteProject() {
  if (!workbenchState.selectedProjectId) {
    throw new Error("缺少 projectId，请从项目详情页或项目列表页进入。");
  }
  const result = await requestJson("/api/approve/remote-project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      projectId: workbenchState.selectedProjectId,
      category: document.getElementById("approval-category").value,
    }),
  });
  setResult(formatApprovalResult(result));
}

async function boot() {
  workbenchState.selectedProjectId = getQueryParam("projectId");
  syncSelectedProjectMeta();
  const [integration, rules] = await Promise.all([
    requestJson("/api/integration/config"),
    requestJson("/api/rules"),
  ]);
  workbenchState.integration = integration;
  workbenchState.rules = rules;
  fillIntegration(integration);
  fillCategorySelect(rules);
  await loadSample();
}

document.getElementById("save-integration-button").addEventListener("click", async () => {
  try {
    await saveIntegration();
  } catch (error) {
    setResult(error.message);
  }
});

document.getElementById("refresh-token-button").addEventListener("click", async () => {
  try {
    await refreshToken();
  } catch (error) {
    setResult(error.message);
  }
});

document.getElementById("load-sample-button").addEventListener("click", async () => {
  try {
    await loadSample();
  } catch (error) {
    setResult(error.message);
  }
});

document.getElementById("load-remote-button").addEventListener("click", async () => {
  try {
    await loadRemoteProject();
  } catch (error) {
    setResult(error.message);
  }
});

document.getElementById("approve-button").addEventListener("click", async () => {
  try {
    await approveCurrentPayload();
  } catch (error) {
    setResult(error.message);
  }
});

document.getElementById("approve-generated-button").addEventListener("click", async () => {
  try {
    await approveGeneratedProject();
  } catch (error) {
    setResult(error.message);
  }
});

document.getElementById("approve-remote-button").addEventListener("click", async () => {
  try {
    setResult("正在执行远程项目审批，请稍候。");
    await approveRemoteProject();
  } catch (error) {
    setResult(error.message);
  }
});

boot().catch((error) => {
  setResult(error.message);
});
