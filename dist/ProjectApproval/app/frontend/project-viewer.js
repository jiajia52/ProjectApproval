const viewerState = {
  projectId: "",
  document: null,
  rules: null,
  activeSection: "project_content",
  activeTabs: {
    project_content: "background",
    project_value: "overview",
    milestones: "approval_plan",
    budget: "items",
    cost_change: "reason",
  },
};

const IMAGE_DOWNLOAD_PREFIX = "https://prod-itpm.faw.cn/itpmNew/gateway/sop-itpm-service/files/download/";

const SECTION_DEFINITIONS = [
  { key: "project_content", label: "项目内容" },
  { key: "project_value", label: "项目价值" },
  { key: "milestones", label: "项目里程碑" },
  { key: "budget", label: "预算信息" },
  { key: "cost_change", label: "费用变化点" },
];

const TAB_DEFINITIONS = {
  project_content: [
    { key: "background", label: "项目背景" },
    { key: "target", label: "项目目标" },
    { key: "scope", label: "项目范围" },
    { key: "solution", label: "项目方案" },
    { key: "panorama", label: "业务全景图" },
    { key: "annual_model", label: "年度管理模型" },
  ],
  project_value: [
    { key: "overview", label: "项目价值" },
    { key: "capability", label: "能力模型" },
    { key: "result", label: "结果模型" },
    { key: "management", label: "管理体系模型" },
  ],
  milestones: [
    { key: "approval_plan", label: "立项计划" },
    { key: "contract_plan", label: "合同计划" },
    { key: "target_plan", label: "目标计划" },
  ],
  budget: [
    { key: "items", label: "费用项清单" },
    { key: "summary", label: "预算汇总" },
  ],
  cost_change: [
    { key: "reason", label: "变化说明" },
    { key: "history", label: "历史投入分析" },
  ],
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
    throw new Error(payload?.detail || payload?.message || text || "请求失败。");
  }
  return payload;
}

function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name) || "";
}

function setApprovalResult(message) {
  document.getElementById("viewer-approval-result").textContent = message;
}

function setApprovalBusy(isBusy) {
  const button = document.getElementById("viewer-approve-button");
  const category = document.getElementById("viewer-category");
  button.disabled = isBusy;
  category.disabled = isBusy;
  button.textContent = isBusy ? "审批执行中..." : "执行远程审批";
}

function fillCategorySelect(rules) {
  const select = document.getElementById("viewer-category");
  const categoryFromQuery = getQueryParam("category");
  select.innerHTML = "";
  rules.categories.forEach((category, index) => {
    const option = document.createElement("option");
    option.value = category.name;
    option.textContent = `${category.name} / ${category.group}`;
    option.selected = category.name === categoryFromQuery || (!categoryFromQuery && index === 0);
    select.appendChild(option);
  });
}

function normalizeList(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => item !== null && item !== undefined && item !== "");
  }
  if (value && typeof value === "object") {
    return Object.values(value).filter((item) => item !== null && item !== undefined && item !== "");
  }
  return [];
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "object") {
    return escapeHtml(JSON.stringify(value, null, 2));
  }
  return escapeHtml(String(value));
}

function formatCurrency(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "0.00";
  }
  return number.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function firstMeaningful(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return "";
}

function renderKvGrid(elementId, items) {
  const container = document.getElementById(elementId);
  container.innerHTML = items
    .map(
      (item) => `
        <div class="viewer-kv-item">
          <p class="viewer-kv-label">${escapeHtml(item.label)}</p>
          <p class="viewer-kv-value">${formatValue(item.value)}</p>
        </div>
      `,
    )
    .join("");
}

function renderProjectBadges(summary) {
  const container = document.getElementById("viewer-project-badges");
  const badges = [
    summary.business_subcategory_name,
    summary.project_category_name,
    summary.project_type_name,
    summary.fixed_project_label,
  ].filter((item, index, list) => item && list.indexOf(item) === index).slice(0, 3);
  container.innerHTML = (badges.length ? badges : ["未识别分类"])
    .map((item, index) => `<span class="viewer-pill ${index === 0 && item === "未识别分类" ? "viewer-pill-muted" : ""}">${escapeHtml(item)}</span>`)
    .join("");
}

function buildBudgetSummary(documentPayload) {
  const summary = documentPayload.project_summary || {};
  const rawBudget = documentPayload.remote_snapshot?.endpoints?.budget?.data || {};
  const requestBudget = firstMeaningful(rawBudget.applyTotalBudget, rawBudget.applyBudgetYear, rawBudget.proBudgetYear, rawBudget.proBudget, summary.budget_year, 0);
  const acceptedBudget = firstMeaningful(rawBudget.acceptTotalBudget, rawBudget.acceptedTotalBudget, rawBudget.acceptBudget, rawBudget.acceptTotalMoney, rawBudget.acceptMoneyTotal, 0);
  const currentAcceptBudget = firstMeaningful(rawBudget.applyAcceptBudget, rawBudget.applyAcceptanceBudget, rawBudget.acceptApplyBudget, rawBudget.applyBudget, 0);
  const remainingBudget = firstMeaningful(
    rawBudget.remainBudget,
    rawBudget.remainingBudget,
    rawBudget.surplusBudget,
    Number(requestBudget || 0) - Number(acceptedBudget || 0),
  );
  return {
    budgetTypeName: firstMeaningful(rawBudget.budgetTypeName, summary.project_category_name, "预算"),
    requestBudget,
    acceptedBudget,
    currentAcceptBudget,
    remainingBudget,
  };
}

function renderBudgetGrid(documentPayload) {
  const summary = buildBudgetSummary(documentPayload);
  document.getElementById("viewer-budget-type").textContent = summary.budgetTypeName;
  document.getElementById("viewer-budget").innerHTML = `
    <div class="viewer-budget-item">
      <span>申请项目预算(元/不含税)</span>
      <strong>${formatCurrency(summary.requestBudget)}</strong>
    </div>
    <div class="viewer-budget-item">
      <span>累计验收金额(元/不含税)</span>
      <strong>${formatCurrency(summary.acceptedBudget)}</strong>
    </div>
    <div class="viewer-budget-item">
      <span>申请验收金额(元/不含税)</span>
      <strong>${formatCurrency(summary.currentAcceptBudget)}</strong>
    </div>
    <div class="viewer-budget-item">
      <span>剩余金额(元/不含税)</span>
      <strong>${formatCurrency(summary.remainingBudget)}</strong>
    </div>
  `;
}

function renderDefinitionPairs(items) {
  return `
    <dl class="viewer-detail-kv">
      ${items
        .map(
          (item) => `
            <div>
              <dt>${escapeHtml(item.label)}</dt>
              <dd>${formatValue(item.value)}</dd>
            </div>
          `,
        )
        .join("")}
    </dl>
  `;
}

function renderList(items) {
  if (!items.length) {
    return "<li>-</li>";
  }
  return items.map((item) => `<li>${formatValue(item)}</li>`).join("");
}

function buildImageUrl(rawValue) {
  const source = String(rawValue || "").trim();
  if (!source) {
    return "";
  }
  const normalized = /^https?:\/\//i.test(source)
    ? source
    : `${IMAGE_DOWNLOAD_PREFIX}${source.replace(/^\/+/, "")}`;
  return `/api/files/download?path=${encodeURIComponent(normalized)}`;
}

function imageLabel(item, index) {
  if (item && typeof item === "object") {
    return item.fileName || item.name || item.title || item.url || item.path || `图片 ${index + 1}`;
  }
  return `图片 ${index + 1}`;
}

function imageSource(item) {
  if (item && typeof item === "object") {
    return item.url || item.fileUrl || item.path || item.filePath || item.id || "";
  }
  return item;
}

function renderImageGallery(images) {
  if (!images.length) {
    return `<p class="viewer-empty">暂无图片</p>`;
  }
  return `
    <div class="viewer-image-grid">
      ${images
        .map((item, index) => {
          const source = imageSource(item);
          const url = buildImageUrl(source);
          if (!url) {
            return "";
          }
          return `
            <article class="viewer-image-shell">
              <button
                class="viewer-image-card"
                type="button"
                data-preview-image="${url}"
                data-preview-title="${escapeHtml(imageLabel(item, index))}"
              >
                <img src="${url}" alt="${escapeHtml(imageLabel(item, index))}">
                <span>${escapeHtml(imageLabel(item, index))}</span>
              </button>
              <a class="viewer-image-link" href="${url}" target="_blank" rel="noreferrer">新页打开</a>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function normalizeScopeRows(documentPayload) {
  return normalizeList(documentPayload.scope?.content_list).map((item, index) => {
    const row = item && typeof item === "object" ? item : {};
    return {
      id: row.id || `scope-${index}`,
      applicationParty: row.applicationParty || "-",
      resourceType: row.resourceType || "-",
      businessDescription: row.businessDescription || "-",
      subType: row.subType || "-",
      previousQuantity: row.previousQuantity ?? 0,
      previousCost: row.previousCost ?? 0,
      currentQuantity: row.currentQuantity ?? 0,
      quantityChange: row.quantityChange ?? "-",
      currentCost: row.currentCost ?? 0,
      costChange: row.costChange ?? "-",
      changeExplain: row.changeExplain || "-",
    };
  });
}

function renderScopeTable(rows) {
  if (!rows.length) {
    return '<p class="viewer-empty">暂无项目范围数据</p>';
  }
  return `
    <div class="viewer-scope-table-wrap">
      <table class="viewer-scope-table">
        <thead>
          <tr>
            <th rowspan="2">应用方</th>
            <th rowspan="2">资源类型</th>
            <th rowspan="2">业务描述</th>
            <th rowspan="2">子类型</th>
            <th colspan="2">2025年费用(元)</th>
            <th colspan="4">2026年费用(元)</th>
            <th rowspan="2">变化点说明</th>
          </tr>
          <tr>
            <th>数量</th>
            <th>费用</th>
            <th>数量</th>
            <th>数量变化(%)</th>
            <th>费用</th>
            <th>费用变化(%)</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${escapeHtml(row.applicationParty)}</td>
              <td>${escapeHtml(row.resourceType)}</td>
              <td>${escapeHtml(row.businessDescription)}</td>
              <td>${escapeHtml(row.subType)}</td>
              <td>${formatCurrency(row.previousQuantity)}</td>
              <td>${formatCurrency(row.previousCost)}</td>
              <td>${formatCurrency(row.currentQuantity)}</td>
              <td>${escapeHtml(row.quantityChange)}</td>
              <td>${formatCurrency(row.currentCost)}</td>
              <td>${escapeHtml(row.costChange)}</td>
              <td>${escapeHtml(row.changeExplain)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderProjectSolutionBlocks(section) {
  const items = normalizeList(section?.items);
  if (!items.length) {
    return '<p class="viewer-empty">暂无项目方案条目</p>';
  }
  return `
    <div class="viewer-solution-list">
      ${items.map((item, index) => `
        <article class="viewer-solution-card">
          <div class="viewer-solution-main">
            <label class="viewer-solution-field">
              <span>项目方案</span>
              <div class="viewer-solution-box">${escapeHtml(item.title || `方案 ${index + 1}`)}</div>
            </label>
            <label class="viewer-solution-field">
              <span>方案内容</span>
              <div class="viewer-solution-box viewer-solution-content">${escapeHtml(item.content || "暂无内容").replaceAll("\n", "<br>")}</div>
            </label>
          </div>
          <div class="viewer-solution-side">
            <p class="viewer-solution-side-title">添加图片</p>
            ${renderImageGallery(normalizeList(item.images))}
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function currentSectionTabs() {
  return TAB_DEFINITIONS[viewerState.activeSection] || [];
}

function getActiveSubTab() {
  const tabs = currentSectionTabs();
  const current = viewerState.activeTabs[viewerState.activeSection];
  if (tabs.some((tab) => tab.key === current)) {
    return current;
  }
  return tabs[0]?.key || "";
}

function renderSummaryStrip(documentPayload) {
  const strip = document.getElementById("viewer-summary-strip");
  const summaryItems = [
    { key: "project_content", label: "项目内容", value: documentPayload.project_content?.background?.title ? "已填写" : "待补充" },
    { key: "project_value", label: "项目价值", value: documentPayload.project_value ? "已填写" : "待补充" },
    { key: "milestones", label: "项目里程碑", value: documentPayload.milestones?.approval_plan?.start ? "已填写" : "待补充" },
    { key: "budget", label: "预算信息", value: (documentPayload.budget?.cost_items || []).length ? "已填写" : "待补充" },
    { key: "cost_change", label: "费用变化点", value: documentPayload.cost_change?.reason ? "已填写" : "待补充" },
  ];
  strip.innerHTML = summaryItems
    .map(
      (item) => `
        <button
          class="summary-tile viewer-summary-item ${viewerState.activeSection === item.key ? "active" : ""}"
          data-section="${item.key}"
          type="button"
        >
          <p class="viewer-summary-label">${item.label}</p>
          <strong>${item.value}</strong>
        </button>
      `,
    )
    .join("");
}

function renderTabBar() {
  const bar = document.getElementById("viewer-tab-bar");
  const activeSubTab = getActiveSubTab();
  const tabs = currentSectionTabs();
  bar.classList.toggle("is-hidden", tabs.length === 0);
  bar.innerHTML = tabs
    .map((tab) => `<button class="viewer-tab ${tab.key === activeSubTab ? "active" : ""}" data-tab="${tab.key}" type="button">${tab.label}</button>`)
    .join("");
}

function renderProjectContent(documentPayload) {
  const content = document.getElementById("viewer-content-panel");
  const side = document.getElementById("viewer-side-panel");
  const layout = content.parentElement;
  const activeTab = getActiveSubTab();

  if (activeTab === "scope") {
    const scopeRows = normalizeScopeRows(documentPayload);
    layout?.classList.add("viewer-layout-scope");
    content.innerHTML = `
      <p class="category-meta">项目范围</p>
      ${renderScopeTable(scopeRows)}
    `;
    side.innerHTML = "";
    side.classList.add("viewer-side-panel-hidden");
    content.classList.add("viewer-content-panel-wide");
    return;
  }

  if (activeTab === "solution") {
    const section = documentPayload.project_content?.[activeTab] || {};
    layout?.classList.add("viewer-layout-scope");
    content.innerHTML = renderProjectSolutionBlocks(section);
    side.innerHTML = "";
    side.classList.add("viewer-side-panel-hidden");
    content.classList.add("viewer-content-panel-wide");
    return;
  }

  layout?.classList.remove("viewer-layout-scope");
  side.classList.remove("viewer-side-panel-hidden");
  content.classList.remove("viewer-content-panel-wide");

  if (activeTab === "scope") {
    const businessProcesses = normalizeList(documentPayload.scope?.business_processes);
    const contentList = normalizeList(documentPayload.scope?.content_list);
    content.innerHTML = `
      <p class="category-meta">业务流程</p>
      <ul>${renderList(businessProcesses)}</ul>
    `;
    side.innerHTML = `
      <p class="category-meta">范围清单</p>
      <ul>${renderList(contentList)}</ul>
    `;
    return;
  }

  const section = documentPayload.project_content?.[activeTab] || {};
  const items = normalizeList(section.items);
  const images = normalizeList(section.images);

  content.innerHTML = `
    <p class="category-meta">标题</p>
    <h2>${escapeHtml(section.title || "未填写")}</h2>
    <div class="viewer-article">${escapeHtml(section.content || "暂无说明").replaceAll("\n", "<br>")}</div>
  `;

  side.innerHTML = `
    <p class="category-meta">结构化条目</p>
    <ul>${renderList(items.map((item) => item.title || item.content || item.order || "-"))}</ul>
    <p class="category-meta" style="margin-top: 16px;">附件与图片</p>
    ${renderImageGallery(images)}
  `;
}

function renderMetricCards(title, metrics) {
  if (!metrics.length) {
    return `
      <p class="category-meta">${title}</p>
      <p class="viewer-empty">暂无数据</p>
    `;
  }
  return `
    <p class="category-meta">${title}</p>
    <div class="viewer-detail-list">
      ${metrics
        .map(
          (item) => `
            <article class="viewer-detail-card">
              <h3>${escapeHtml(item.title || item.name || "未命名")}</h3>
              <dl class="viewer-mini-kv">
                <div><dt>现状</dt><dd>${formatValue(item.current_state || item.currentState)}</dd></div>
                <div><dt>受益部门</dt><dd>${formatValue(item.benefit_department || item.benefitDepartment)}</dd></div>
                <div><dt>目标</dt><dd>${formatValue(item.target_3y || item.target3y || item.target)}</dd></div>
                <div><dt>测算依据</dt><dd>${formatValue(item.calculation_basis || item.calculationBasis)}</dd></div>
              </dl>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderProjectValue(documentPayload) {
  const content = document.getElementById("viewer-content-panel");
  const side = document.getElementById("viewer-side-panel");
  const tamModels = documentPayload.tam_models || {};
  const activeTab = getActiveSubTab();

  if (activeTab === "capability") {
    content.innerHTML = renderMetricCards("能力模型", normalizeList(tamModels.capability));
  } else if (activeTab === "result") {
    content.innerHTML = renderMetricCards("结果模型", normalizeList(tamModels.result));
  } else if (activeTab === "management") {
    content.innerHTML = renderMetricCards("管理体系模型", normalizeList(tamModels.management));
  } else {
    content.innerHTML = `
      <p class="category-meta">项目价值说明</p>
      <div class="viewer-article">${escapeHtml(documentPayload.project_value || "暂无项目价值说明").replaceAll("\n", "<br>")}</div>
    `;
  }

  side.innerHTML = renderDefinitionPairs([
    { label: "能力模型数量", value: normalizeList(tamModels.capability).length },
    { label: "结果模型数量", value: normalizeList(tamModels.result).length },
    { label: "管理体系模型数量", value: normalizeList(tamModels.management).length },
  ]);
}

function renderMilestones(documentPayload) {
  const content = document.getElementById("viewer-content-panel");
  const side = document.getElementById("viewer-side-panel");
  const milestones = documentPayload.milestones || {};
  const activeTab = getActiveSubTab();
  const mapping = {
    approval_plan: { label: "立项计划", value: milestones.approval_plan },
    contract_plan: { label: "合同计划", value: milestones.contract_plan },
    target_plan: { label: "目标计划", value: milestones.target_plan },
  };
  const current = mapping[activeTab] || mapping.approval_plan;

  content.innerHTML = `
    <p class="category-meta">${current.label}</p>
    ${renderDefinitionPairs([
      { label: "开始时间", value: current.value?.start },
      { label: "结束时间", value: current.value?.end },
    ])}
  `;

  side.innerHTML = `
    <p class="category-meta">OKR 时间信息</p>
    ${renderDefinitionPairs([
      { label: "目标开始", value: documentPayload.okr?.time_range?.start },
      { label: "目标结束", value: documentPayload.okr?.time_range?.end },
      { label: "关键结果数量", value: normalizeList(documentPayload.okr?.key_results).length },
    ])}
  `;
}

function renderBudget(documentPayload) {
  const content = document.getElementById("viewer-content-panel");
  const side = document.getElementById("viewer-side-panel");
  const items = normalizeList(documentPayload.budget?.cost_items);
  const activeTab = getActiveSubTab();

  if (activeTab === "summary") {
    content.innerHTML = `
      <p class="category-meta">预算汇总</p>
      ${renderDefinitionPairs([
        { label: "费用项数量", value: items.length },
        { label: "年度预算", value: documentPayload.project_summary?.budget_year },
        { label: "固定项目", value: documentPayload.project_summary?.fixed_project_label },
      ])}
    `;
    side.innerHTML = `
      <p class="category-meta">预算科目列表</p>
      <ul>${renderList(items.map((item) => item.budget_subject || item.name || "-"))}</ul>
    `;
    return;
  }

  content.innerHTML = `
    <p class="category-meta">费用项清单</p>
    <div class="viewer-detail-list">
      ${
        items.length
          ? items
              .map(
                (item, index) => `
                  <article class="viewer-detail-card">
                    <h3>${index + 1}. ${escapeHtml(item.name || "未命名费用项")}</h3>
                    <dl class="viewer-mini-kv">
                      <div><dt>金额</dt><dd>${formatValue(item.amount)}</dd></div>
                      <div><dt>预算科目</dt><dd>${formatValue(item.budget_subject)}</dd></div>
                      <div><dt>测算依据</dt><dd>${formatValue(item.calculation)}</dd></div>
                      <div><dt>采购方式</dt><dd>${formatValue(item.purchase_mode)}</dd></div>
                    </dl>
                  </article>
                `,
              )
              .join("")
          : '<p class="viewer-empty">暂无预算信息</p>'
      }
    </div>
  `;

  side.innerHTML = renderDefinitionPairs([
    { label: "费用项数量", value: items.length },
    { label: "年度预算", value: documentPayload.project_summary?.budget_year },
    { label: "固定项目", value: documentPayload.project_summary?.fixed_project_label },
  ]);
}

function renderCostChange(documentPayload) {
  const content = document.getElementById("viewer-content-panel");
  const side = document.getElementById("viewer-side-panel");
  const costChange = documentPayload.cost_change || {};
  const activeTab = getActiveSubTab();

  if (activeTab === "history") {
    content.innerHTML = `
      <p class="category-meta">历史投入分析</p>
      ${renderDefinitionPairs([
        { label: "固定项目", value: costChange.fixed_project ? "是" : "否" },
        { label: "历史分析", value: costChange.history_analysis || "暂无说明" },
      ])}
    `;
  } else {
    content.innerHTML = `
      <p class="category-meta">变化说明</p>
      ${renderDefinitionPairs([
        { label: "固定项目", value: costChange.fixed_project ? "是" : "否" },
        { label: "变化原因", value: costChange.reason || "暂无说明" },
      ])}
    `;
  }

  side.innerHTML = renderDefinitionPairs([
    { label: "项目状态", value: documentPayload.project_summary?.project_status_name },
    { label: "流程状态", value: documentPayload.project_summary?.flow_status_name },
    { label: "项目类别", value: documentPayload.project_summary?.project_category_name },
  ]);
}

function renderActiveSection() {
  const documentPayload = viewerState.document;
  const title = document.getElementById("viewer-section-title");
  if (!documentPayload) {
    document.getElementById("viewer-content-panel").innerHTML = '<p class="viewer-empty">暂无数据</p>';
    document.getElementById("viewer-side-panel").innerHTML = '<p class="viewer-empty">暂无数据</p>';
    title.textContent = "项目内容";
    return;
  }

  const section = SECTION_DEFINITIONS.find((item) => item.key === viewerState.activeSection) || SECTION_DEFINITIONS[0];
  title.textContent = section.label;

  if (viewerState.activeSection === "project_content") {
    renderProjectContent(documentPayload);
    return;
  }
  if (viewerState.activeSection === "project_value") {
    renderProjectValue(documentPayload);
    return;
  }
  if (viewerState.activeSection === "milestones") {
    renderMilestones(documentPayload);
    return;
  }
  if (viewerState.activeSection === "budget") {
    renderBudget(documentPayload);
    return;
  }
  renderCostChange(documentPayload);
}

function renderDocument(documentPayload) {
  const summary = documentPayload.project_summary || {};

  document.getElementById("viewer-project-name").textContent =
    summary.project_name || documentPayload.project_name || viewerState.projectId;
  document.getElementById("viewer-project-subtitle").textContent =
    `${summary.project_status_name || "-"} / ${summary.flow_status_name || "-"} / ${summary.project_type_name || "-"}`;
  renderProjectBadges(summary);

  renderKvGrid("viewer-ownership", [
    { label: "项目编码", value: summary.project_code },
    { label: "项目经理", value: summary.project_manager_name },
    { label: "业务部门", value: summary.department_name },
    { label: "归属领域", value: summary.domain_name },
  ]);

  renderKvGrid("viewer-classification", [
    { label: "项目类型", value: summary.project_type_name },
    { label: "项目类别", value: summary.project_category_name },
    { label: "项目状态", value: summary.project_status_name },
    { label: "流程状态", value: summary.flow_status_name },
  ]);

  renderKvGrid("viewer-budget", [
    { label: "项目等级", value: summary.project_level_name },
    { label: "固定项目", value: summary.fixed_project_label },
    { label: "年度预算", value: summary.budget_year },
    { label: "项目 ID", value: documentPayload.project_id },
  ]);

  renderBudgetGrid(documentPayload);
  renderSummaryStrip(documentPayload);
  renderTabBar();
  renderActiveSection();
}

function formatApprovalResult(result) {
  const lines = [
    `项目: ${result.project_name}`,
    `品类: ${result.category}`,
    `结论: ${result.decision}`,
  ];
  if (result.summary) {
    lines.push(`摘要: ${result.summary}`);
  }
  if (result.run_dir) {
    lines.push(`审批落盘: ${result.run_dir}`);
  }
  lines.push("");
  lines.push("风险摘要:");
  if ((result.risks || []).length) {
    (result.risks || []).slice(0, 8).forEach((item) => lines.push(`- ${item}`));
  } else {
    lines.push("- 无");
  }
  return lines.join("\n");
}

function openImageModal(url, title) {
  const modal = document.getElementById("viewer-image-modal");
  const image = document.getElementById("viewer-image-modal-img");
  const link = document.getElementById("viewer-image-modal-link");
  const heading = document.getElementById("viewer-image-modal-title");
  image.src = url;
  image.alt = title || "图片预览";
  link.href = url;
  heading.textContent = title || "图片预览";
  modal.hidden = false;
  document.body.classList.add("viewer-modal-open");
}

function closeImageModal() {
  const modal = document.getElementById("viewer-image-modal");
  const image = document.getElementById("viewer-image-modal-img");
  const link = document.getElementById("viewer-image-modal-link");
  modal.hidden = true;
  image.src = "";
  link.href = "#";
  document.body.classList.remove("viewer-modal-open");
}

async function loadDocument() {
  const category = document.getElementById("viewer-category").value;
  const documentPayload = await requestJson(`/api/projects/${encodeURIComponent(viewerState.projectId)}/document?category=${encodeURIComponent(category)}`);
  viewerState.document = documentPayload;
  renderDocument(documentPayload);
}

async function runApproval() {
  const category = document.getElementById("viewer-category").value;
  const result = await requestJson("/api/approve/remote-project", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      projectId: viewerState.projectId,
      category,
    }),
  });
  setApprovalResult(formatApprovalResult(result));
}

async function boot() {
  viewerState.projectId = getQueryParam("projectId");
  if (!viewerState.projectId) {
    throw new Error("缺少 projectId 参数。");
  }
  viewerState.rules = await requestJson("/api/rules");
  fillCategorySelect(viewerState.rules);
  await loadDocument();
}

document.getElementById("viewer-tab-bar").addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const tab = target.dataset.tab;
  if (!tab) {
    return;
  }
  viewerState.activeTabs[viewerState.activeSection] = tab;
  renderTabBar();
  renderActiveSection();
});

document.getElementById("viewer-summary-strip").addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const trigger = target.closest("[data-section]");
  if (!(trigger instanceof HTMLElement)) {
    return;
  }
  const section = trigger.dataset.section;
  if (!section) {
    return;
  }
  viewerState.activeSection = section;
  renderSummaryStrip(viewerState.document || {});
  renderTabBar();
  renderActiveSection();
});

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  const previewTrigger = target.closest("[data-preview-image]");
  if (previewTrigger instanceof HTMLElement) {
    openImageModal(previewTrigger.dataset.previewImage || "", previewTrigger.dataset.previewTitle || "图片预览");
    return;
  }
  if (target.id === "viewer-image-modal-close" || target.dataset.closeImageModal === "true") {
    closeImageModal();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeImageModal();
  }
});

document.getElementById("viewer-category").addEventListener("change", async () => {
  try {
    setApprovalBusy(true);
    await loadDocument();
    setApprovalResult("已切换审批品类。");
  } catch (error) {
    setApprovalResult(error.message);
  } finally {
    setApprovalBusy(false);
  }
});

document.getElementById("viewer-approve-button").addEventListener("click", async () => {
  try {
    setApprovalBusy(true);
    setApprovalResult(`正在执行远程审批，请稍候。\n接口记录目录: runtime/api_result/projects/${viewerState.projectId}/`);
    await runApproval();
  } catch (error) {
    setApprovalResult(error.message);
  } finally {
    setApprovalBusy(false);
  }
});

boot().catch((error) => {
  setApprovalResult(error.message);
});
