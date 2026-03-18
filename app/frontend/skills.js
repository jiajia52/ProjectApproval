const skillState = {
  config: null,
  rules: null,
  skills: [],
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
    throw new Error(payload?.detail || payload?.message || text || "请求失败");
  }
  return payload;
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function fillForm(config) {
  document.getElementById("generated_project_name").value = config.generation.generated_project_name;
  document.getElementById("ontology_namespace").value = config.generation.ontology_namespace;
  document.getElementById("output_dir").value = config.generation.output_dir;
  document.getElementById("rules_output").value = config.generation.rules_output;
}

function collectConfig() {
  return {
    ...skillState.config,
    generation: {
      ...skillState.config.generation,
      generated_project_name: document.getElementById("generated_project_name").value.trim(),
      ontology_namespace: document.getElementById("ontology_namespace").value.trim(),
      output_dir: document.getElementById("output_dir").value.trim(),
      rules_output: document.getElementById("rules_output").value.trim(),
      enabled_categories: Array.from(document.querySelectorAll("#category-list input:checked")).map((node) => node.value),
      enabled_skill_groups: Array.from(document.querySelectorAll("#skill-group-list input:checked")).map((node) => node.value),
    },
  };
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

function renderSummary(rules, skills, config) {
  const container = document.getElementById("skill-summary");
  container.innerHTML = "";
  const entries = [
    ["评审规则总数", rules.summary.rule_count],
    ["Skill 大类总数", Object.keys(rules.summary.by_review_point || {}).length],
    ["当前生成 Skill", skills.length],
    ["启用 Skill 大类", (config.generation.enabled_skill_groups || []).length],
  ];
  entries.forEach(([label, value]) => {
    const tile = document.createElement("div");
    tile.className = "summary-tile";
    tile.innerHTML = `<strong>${value}</strong><p>${label}</p>`;
    container.appendChild(tile);
  });
  setText("skill-grouping", "按评审大类分组");
  setText("skill-summary-text", `当前按 review_point 聚合生成 ${skills.length} 个审批大类 skill。`);
}

function renderSkillGroups(config, rules) {
  const enabled = new Set(config.generation.enabled_skill_groups || []);
  const container = document.getElementById("skill-group-list");
  container.innerHTML = "";
  Object.entries(rules.summary.by_review_point || {}).forEach(([reviewPoint, count]) => {
    const item = document.createElement("div");
    item.className = "category-item";
    item.innerHTML = `
      <label>
        <input type="checkbox" value="${reviewPoint}" ${enabled.has(reviewPoint) ? "checked" : ""}>
        <span>${reviewPoint}</span>
      </label>
      <div class="category-meta">
        <div>审批大类 Skill</div>
        <div>${count} 条子规则</div>
      </div>
    `;
    container.appendChild(item);
  });
}

function renderCategories(config, rules) {
  const enabled = new Set(config.generation.enabled_categories || []);
  const counter = rules.summary.by_category || {};
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

function renderSkillList(skills) {
  const container = document.getElementById("skill-list");
  container.innerHTML = "";
  skills.forEach((skill) => {
    const item = document.createElement("div");
    item.className = "output-item";
    item.innerHTML = `
      <strong>${skill.review_point || skill.name}</strong>
      <p>${skill.rule_count || 0} 条子规则</p>
      <p>${(skill.review_contents || []).slice(0, 8).join("、")}</p>
      <code>${skill.directory}</code>
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

async function saveConfig() {
  skillState.config = await requestJson("/api/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(collectConfig()),
  });
  document.getElementById("generation-result").textContent = "Skill 配置已保存。";
}

async function generateArtifacts() {
  const result = await requestJson("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  const skillSummary = result.approval_skills || result.approval_item_skills || {};
  const files = Object.entries(result.files).map(([key, value]) => `${key}: ${value}`);
  document.getElementById("generation-result").textContent = [
    ...files,
    "",
    `skills: ${skillSummary.generated_count || 0}`,
    `grouping: ${skillSummary.grouping_key || "review_point"}`,
  ].join("\n");
  await boot();
}

async function boot() {
  const [config, rules, skills, outputs] = await Promise.all([
    requestJson("/api/config"),
    requestJson("/api/rules"),
    requestJson("/api/skills"),
    requestJson("/api/outputs"),
  ]);
  skillState.config = config;
  skillState.rules = rules;
  skillState.skills = skills;
  fillForm(config);
  renderSources(config);
  renderSummary(rules, skills, config);
  renderSkillGroups(config, rules);
  renderCategories(config, rules);
  renderSkillList(skills);
  renderOutputs(outputs);
}

document.getElementById("save-button").addEventListener("click", async () => {
  try {
    await saveConfig();
    await boot();
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

boot().catch((error) => {
  document.getElementById("generation-result").textContent = error.message;
});
