const state = {
  config: null,
  rules: null,
  skills: null,
};

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function renderSkill(skills) {
  const skill = skills[0];
  if (!skill) {
    setText("skill-name", "未注册");
    setText("skill-description", "当前没有从 AgentScope 读取到技能。");
    return;
  }
  setText("skill-name", skill.name);
  setText("skill-description", `${skill.description}\n目录：${skill.directory}`);
}

function renderSources(config) {
  const container = document.getElementById("source-list");
  container.innerHTML = "";
  Object.entries(config.sources).forEach(([key, value]) => {
    const item = document.createElement("div");
    item.className = "source-item";
    item.innerHTML = `<strong>${key}</strong><code>${value}</code>`;
    container.appendChild(item);
  });
}

function renderSummary(rules) {
  const container = document.getElementById("rule-summary");
  container.innerHTML = "";
  const entries = [
    ["规则总数", rules.summary.rule_count],
    ["品类数量", rules.summary.category_count],
    ["评审点数量", Object.keys(rules.summary.by_review_point).length],
    ["模型维度数量", Object.keys(rules.summary.by_model_dimension).length],
  ];
  entries.forEach(([label, value]) => {
    const tile = document.createElement("div");
    tile.className = "summary-tile";
    tile.innerHTML = `<strong>${value}</strong><p>${label}</p>`;
    container.appendChild(tile);
  });
}

function renderCategories(config, rules) {
  const enabled = new Set(config.generation.enabled_categories);
  const counter = rules.summary.by_category;
  const container = document.getElementById("category-list");
  container.innerHTML = "";

  rules.categories.forEach((category) => {
    const item = document.createElement("div");
    item.className = "category-item";
    item.innerHTML = `
      <label>
        <input type="checkbox" value="${category.name}" ${enabled.has(category.name) ? "checked" : ""}>
        <span>${category.name}</span>
      </label>
      <div class="category-meta">
        <div>${category.group}</div>
        <div>${counter[category.name] || 0} 条规则</div>
      </div>
    `;
    container.appendChild(item);
  });
}

function renderOutputs(outputs) {
  const container = document.getElementById("output-list");
  container.innerHTML = "";
  outputs.forEach((output) => {
    const item = document.createElement("div");
    item.className = "output-item";
    item.innerHTML = `<strong>${output.name}</strong><p>${output.modified_at}</p><code>${output.path}</code>`;
    container.appendChild(item);
  });
}

function renderCategorySelect(config, rules) {
  const select = document.getElementById("approval-category");
  const current = config.generation.enabled_categories[0];
  select.innerHTML = "";
  rules.categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category.name;
    option.textContent = `${category.name} / ${category.group}`;
    if (category.name === current) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

function collectConfig() {
  return {
    ...state.config,
    generation: {
      ...state.config.generation,
      generated_project_name: document.getElementById("generated_project_name").value.trim(),
      ontology_namespace: document.getElementById("ontology_namespace").value.trim(),
      output_dir: document.getElementById("output_dir").value.trim(),
      rules_output: document.getElementById("rules_output").value.trim(),
      enabled_categories: Array.from(document.querySelectorAll("#category-list input:checked")).map((node) => node.value),
    },
  };
}

function fillForm(config) {
  document.getElementById("generated_project_name").value = config.generation.generated_project_name;
  document.getElementById("ontology_namespace").value = config.generation.ontology_namespace;
  document.getElementById("output_dir").value = config.generation.output_dir;
  document.getElementById("rules_output").value = config.generation.rules_output;
}

async function loadPage() {
  const [skills, config, rules, outputs] = await Promise.all([
    requestJson("/api/skills"),
    requestJson("/api/config"),
    requestJson("/api/rules"),
    requestJson("/api/outputs"),
  ]);

  state.skills = skills;
  state.config = config;
  state.rules = rules;

  renderSkill(skills);
  fillForm(config);
  renderSources(config);
  renderSummary(rules);
  renderCategories(config, rules);
  renderCategorySelect(config, rules);
  renderOutputs(outputs);
}

async function saveConfig() {
  const payload = collectConfig();
  state.config = await requestJson("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  renderCategories(state.config, state.rules);
  renderSources(state.config);
  document.getElementById("generation-result").textContent = "配置已保存。";
}

async function generateArtifacts() {
  document.getElementById("generation-result").textContent = "正在生成...";
  const result = await requestJson("/api/generate", { method: "POST" });
  const lines = Object.entries(result.files).map(([key, value]) => `${key}: ${value}`);
  document.getElementById("generation-result").textContent = lines.join("\n");
  renderOutputs(await requestJson("/api/outputs"));
}

async function loadApprovalSample() {
  const sample = await requestJson("/api/approval/sample");
  document.getElementById("approval-category").value = sample.category;
  document.getElementById("approval-payload").value = JSON.stringify(sample, null, 2);
  document.getElementById("approval-result").textContent = "已加载样例输入。";
}

function formatApprovalResult(result) {
  const head = [
    `项目: ${result.project_name}`,
    `品类: ${result.category}`,
    `结论: ${result.decision}`,
    `评分: ${result.score}`,
    `失败规则: ${result.statistics.failed_rules}`,
  ];
  const findings = result.findings.slice(0, 8).map((item) => {
    return `- [${item.severity}] ${item.review_point}/${item.review_content}: ${item.message}`;
  });
  return [...head, "", "问题摘要:", ...findings].join("\n");
}

async function approvePayload() {
  const category = document.getElementById("approval-category").value;
  const documentPayload = JSON.parse(document.getElementById("approval-payload").value);
  const result = await requestJson("/api/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, document: documentPayload }),
  });
  document.getElementById("approval-result").textContent = formatApprovalResult(result);
  renderOutputs(await requestJson("/api/outputs"));
}

async function approveGeneratedProject() {
  const category = document.getElementById("approval-category").value;
  const result = await requestJson("/api/approve/generated-project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category }),
  });
  document.getElementById("approval-result").textContent = formatApprovalResult(result);
  renderOutputs(await requestJson("/api/outputs"));
}

document.getElementById("save-button").addEventListener("click", async () => {
  try {
    await saveConfig();
  } catch (error) {
    document.getElementById("generation-result").textContent = error.message;
  }
});

document.getElementById("generate-button").addEventListener("click", async () => {
  try {
    await saveConfig();
    await generateArtifacts();
  } catch (error) {
    document.getElementById("generation-result").textContent = error.message;
  }
});

document.getElementById("load-sample-button").addEventListener("click", async () => {
  try {
    await loadApprovalSample();
  } catch (error) {
    document.getElementById("approval-result").textContent = error.message;
  }
});

document.getElementById("approve-button").addEventListener("click", async () => {
  try {
    await approvePayload();
  } catch (error) {
    document.getElementById("approval-result").textContent = error.message;
  }
});

document.getElementById("approve-generated-button").addEventListener("click", async () => {
  try {
    await approveGeneratedProject();
  } catch (error) {
    document.getElementById("approval-result").textContent = error.message;
  }
});

loadPage().catch((error) => {
  document.getElementById("generation-result").textContent = error.message;
});
