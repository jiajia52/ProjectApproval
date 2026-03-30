import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import PageLayout from "../../components/PageLayout";
import { normalizeScene, requestJson } from "../../api";

const IMAGE_DOWNLOAD_PREFIX = "https://prod-itpm.faw.cn/itpmNew/gateway/sop-itpm-service/files/download/";

const INITIATION_SECTIONS = [
  { key: "project_content", label: "项目内容" },
  { key: "project_value", label: "项目价值" },
  { key: "architecture_review", label: "专业领域评审" },
  { key: "tam_models", label: "TAM模型" },
  { key: "organization", label: "组织" },
  { key: "milestones", label: "里程碑" },
  { key: "budget", label: "预算" },
  { key: "cost_change", label: "费用变化点" },
];

const ACCEPTANCE_SECTIONS = [
  { key: "project_review", label: "项目回顾" },
  { key: "architecture_review", label: "专业领域评审" },
  { key: "tam_models", label: "TAM模型评审" },
  { key: "acceptance_scope", label: "验收范围" },
  { key: "acceptance_stage", label: "验收阶段" },
  { key: "acceptance_detail", label: "验收明细" },
  { key: "acceptance_deliverables", label: "上传备证" },
];

const TASK_ORDER_PHASE = "task_order";
const TASK_ORDER_SECTIONS = [
  { key: "basic_info", label: "基本信息" },
  { key: "business_architecture", label: "业务架构" },
  { key: "task_assignment", label: "任务填写" },
  { key: "staffing", label: "人员配置" },
  { key: "cost_estimation", label: "费用评估" },
  { key: "technical_requirements", label: "技术要求" },
];

const ACCEPTANCE_SECTION_RULE_TABS = {
  project_review: "项目回顾",
  architecture_review: "专业领域评审（阶段验收无此tab）",
  tam_models: "TAM模型评审（阶段验收无此tab）",
  acceptance_scope: "验收范围",
  acceptance_stage: "验收阶段（提前发起终验无此tab）",
  acceptance_detail: "验收明细（提前发起终验无此tab）",
  acceptance_deliverables: "上传备证",
};

const ACCEPTANCE_REVIEW_POINT_TO_TAB_KEY = {
  项目背景: "background",
  项目目标: "target",
  项目OKR: "okr",
  项目范围: "scope",
  系统范围: "system_scope",
  项目方案: "solution",
  业务全景图: "panorama",
  年度管理模型: "annual_model",
  "验收方案（非必填）": "acceptance_plan",
};

const ACCEPTANCE_TAM_POINT_TO_TAB_KEY = {
  "能力（竞争）模型": "capability",
  "结果（财务/客户）模型": "result",
  管理体系模型: "management",
};

const COMMON_REVIEW_TABS = [
  { key: "background", label: "项目背景" },
  { key: "target", label: "项目目标" },
  { key: "okr", label: "项目OKR" },
  { key: "scope", label: "项目范围" },
  { key: "system_scope", label: "系统范围" },
  { key: "solution", label: "项目方案" },
  { key: "panorama", label: "业务全景图" },
  { key: "annual_model", label: "年度管理模型" },
  { key: "acceptance_plan", label: "验收方案" },
];

const ACCEPTANCE_PROJECT_REVIEW_TAB_KEYS = new Set(["background", "okr", "scope", "system_scope", "solution", "acceptance_plan"]);
const ACCEPTANCE_PROJECT_REVIEW_TABS = COMMON_REVIEW_TABS.filter((tab) => ACCEPTANCE_PROJECT_REVIEW_TAB_KEYS.has(tab.key));

const TAM_TABS = [
  { key: "capability", label: "能力模型" },
  { key: "result", label: "结果模型" },
  { key: "management", label: "管理模型" },
];

const SECTION_TABS = {
  project_content: COMMON_REVIEW_TABS,
  project_review: COMMON_REVIEW_TABS,
  project_value: [{ key: "overview", label: "价值说明" }],
  tam_models: TAM_TABS,
  milestones: [
    { key: "approval_plan", label: "立项计划" },
    { key: "contract_plan", label: "合同计划" },
    { key: "target_plan", label: "目标计划" },
  ],
  budget: [
    { key: "items", label: "费用明细" },
    { key: "summary", label: "预算汇总" },
  ],
  cost_change: [
    { key: "reason", label: "变化说明" },
    { key: "history", label: "历史投入" },
  ],
  acceptance_scope: [
    { key: "tasks", label: "任务单" },
    { key: "contracts", label: "合同" },
  ],
  acceptance_detail: [
    { key: "task_acceptance", label: "任务单验收" },
    { key: "contract_acceptance", label: "合同验收" },
  ],
};

const ACCEPTANCE_ORDER_SECTIONS = new Set([
  "acceptance_scope",
  "acceptance_detail",
  "acceptance_deliverables",
]);

function definitionKey(item) {
  if (typeof item === "string") {
    return item;
  }
  return String(item?.key || "").trim();
}

function filterDefinitionsByKeys(definitions, keys) {
  const allowed = new Set(
    normalizeList(keys)
      .map((item) => definitionKey(item))
      .filter(Boolean),
  );
  if (!allowed.size) {
    return [];
  }
  return definitions.filter((item) => allowed.has(item.key));
}

function orderDefinitionsByKeys(definitions, keys) {
  const orderedKeys = normalizeList(keys)
    .map((item) => definitionKey(item))
    .filter(Boolean);
  if (!orderedKeys.length) {
    return [];
  }
  const definitionMap = new Map(definitions.map((item) => [item.key, item]));
  const ordered = [];
  orderedKeys.forEach((key) => {
    const matched = definitionMap.get(key);
    if (matched && !ordered.some((item) => item.key === key)) {
      ordered.push(matched);
    }
  });
  return ordered;
}

function normalizeList(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (!value || typeof value !== "object") {
    return [];
  }
  for (const key of ["dataList", "list", "rows", "records", "items", "partInfos"]) {
    if (Array.isArray(value[key])) {
      return value[key];
    }
  }
  return Object.keys(value).length ? [value] : [];
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (Array.isArray(value)) {
    return value.map((item) => formatValue(item)).filter((item) => item !== "-").join(" / ") || "-";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function formatCurrency(value) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount) || amount === 0) {
    return "-";
  }
  return amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatCurrencyAllowZero(value) {
  const amount = Number(value || 0);
  if (!Number.isFinite(amount)) {
    return "-";
  }
  return amount.toLocaleString("zh-CN", { maximumFractionDigits: 2 });
}

function formatPercent(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "-";
  }
  if (text.includes("%")) {
    return text;
  }
  const amount = Number(text);
  if (!Number.isFinite(amount)) {
    return text;
  }
  return `${amount}%`;
}

function formatCompactDate(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "";
  }
  const match = text.match(/\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : text;
}

function formatCurrencyWithUnit(value) {
  const text = formatCurrency(value);
  return text === "-" ? text : `${text}元`;
}

function approvalToneClass(decision) {
  const normalized = String(decision || "").trim();
  if (normalized === "通过") {
    return "is-pass";
  }
  if (normalized === "驳回") {
    return "is-reject";
  }
  return "is-warning";
}

function formatApprovalItemStatus(status) {
  const normalized = String(status || "").trim();
  if (normalized === "pass") {
    return "通过";
  }
  if (normalized === "fail") {
    return "不通过";
  }
  if (normalized === "needs_more_info") {
    return "需更多信息";
  }
  return normalized || "-";
}

function detailStatusTone(status) {
  if (status === "通过") {
    return "is-pass";
  }
  if (status === "不通过") {
    return "is-reject";
  }
  if (status === "需更多信息") {
    return "is-warning";
  }
  return "is-pending";
}

function normalizeApprovalDetailItems(approvalDetails) {
  const baselineItems = approvalDetails?.baseline?.rule_results || [];
  if (baselineItems.length) {
    return baselineItems.map((item, index) => ({
      id: item.rule_id || `rule-${index}`,
      ruleId: item.rule_id || "-",
      checkPoint: [item.review_point, item.review_content].filter(Boolean).join(" / ") || "-",
      status: formatApprovalItemStatus(item.status),
      severity: item.severity || "",
      resultText: item.message || "",
      suggestion: item.suggestion || "",
      evidence: Array.isArray(item.evidence) ? item.evidence.join("\n") : item.evidence || "",
    }));
  }

  return (approvalDetails?.item_results || []).map((item, index) => ({
    id: item.rule_id || `item-${index}`,
    ruleId: item.rule_id || "-",
    checkPoint: item.review_content || item.review_point || item.rule_id || "-",
    status: formatApprovalItemStatus(item.status),
    severity: item.severity || "",
    resultText: item.reason || item.message || "",
    suggestion: item.suggestion || "",
    evidence: Array.isArray(item.evidence) ? item.evidence.join("\n") : item.evidence || "",
  }));
}

function firstMeaningful(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && String(value).trim() !== "") {
      return value;
    }
  }
  return "";
}

function imageUrlOf(value) {
  const text = String(value || "").trim();
  if (!text) {
    return "";
  }
  if (/^https?:\/\//i.test(text)) {
    return text;
  }
  return `${IMAGE_DOWNLOAD_PREFIX}${text.replace(/^\/+/, "")}`;
}

function hasUploadSectionContent(section) {
  if (!section || typeof section !== "object") {
    return false;
  }
  return Boolean(
    String(section.title || "").trim() ||
      String(section.content || "").trim() ||
      normalizeList(section.images).length ||
      normalizeList(section.items).length,
  );
}

function hasObjectContent(value) {
  if (!value || typeof value !== "object") {
    return false;
  }
  return Object.values(value).some((item) => {
    if (Array.isArray(item)) {
      return item.length > 0;
    }
    if (item && typeof item === "object") {
      return Object.keys(item).length > 0;
    }
    return String(item || "").trim() !== "";
  });
}

function hasReviewTabContent(documentPayload, tabKey) {
  const projectContent = documentPayload?.project_content || {};
  const okr = documentPayload?.okr || {};
  const scope = documentPayload?.scope || {};
  if (["background", "target", "solution", "panorama", "acceptance_plan", "annual_model"].includes(tabKey)) {
    return hasUploadSectionContent(projectContent[tabKey]);
  }
  if (tabKey === "okr") {
    return hasObjectContent(okr);
  }
  if (tabKey === "scope") {
    return normalizeList(scope.business_processes).length || normalizeList(scope.content_list).length;
  }
  if (tabKey === "system_scope") {
    return normalizeList(scope.microservices).length || normalizeList(scope.microapps).length;
  }
  if (tabKey === "annual_model") {
    return (
      hasUploadSectionContent(projectContent.annual_model)
      || normalizeList(scope.business_processes).length
      || normalizeList(scope.content_list).length
    );
  }
  return false;
}

function hasArchitectureReviewContent(documentPayload, architecturePayload) {
  const groups = normalizeList(architecturePayload?.groups || documentPayload?.architecture_review_details);
  if (groups.some((group) => normalizeList(group?.items).length)) {
    return true;
  }
  const architectureReviews = documentPayload?.architecture_reviews || {};
  return Object.values(architectureReviews).some((group) => {
    if (!group || typeof group !== "object") {
      return false;
    }
    return (
      normalizeList(group?.items).length
      || Object.keys(group?.summary || {}).length
      || String(group?.message || "").trim() !== ""
    );
  });
}

function sectionStatus(documentPayload, architecturePayload, scene, sectionKey) {
  const acceptance = documentPayload?.acceptance || {};
  const acceptanceInfoList = normalizeList(acceptance.info_list);
  const statusMap = {
    project_content: COMMON_REVIEW_TABS.some((tab) => hasReviewTabContent(documentPayload, tab.key)),
    project_review: COMMON_REVIEW_TABS.some((tab) => hasReviewTabContent(documentPayload, tab.key)),
    project_value: Boolean(String(documentPayload?.project_value || "").trim()),
    architecture_review: hasArchitectureReviewContent(documentPayload, architecturePayload),
    tam_models: TAM_TABS.some((tab) => normalizeList(documentPayload?.tam_models?.[tab.key]).length),
    organization: normalizeList(documentPayload?.organization?.members).length || normalizeList(documentPayload?.organization?.teams).length,
    milestones: Object.values(documentPayload?.milestones || {}).some((value) => normalizeList(value).length || (value && typeof value === "object" && Object.keys(value).length)),
    budget: normalizeList(documentPayload?.budget?.cost_items).length || Boolean(documentPayload?.budget?.summary),
    cost_change: Boolean(String(documentPayload?.cost_change?.reason || "").trim()) || normalizeList(documentPayload?.cost_change?.history_items).length,
    acceptance_scope:
      normalizeList(acceptance.task_list).length ||
      normalizeList(acceptance.task_acceptance_list).length ||
      normalizeList(acceptance.contract_list).length,
    acceptance_stage:
      acceptanceInfoList.length ||
      normalizeList(acceptance.acceptance_ids).length ||
      normalizeList(acceptance.task_acceptance_list).length ||
      normalizeList(acceptance.contract_acceptance_list).length,
    acceptance_detail: normalizeList(acceptance.task_acceptance_list).length || normalizeList(acceptance.contract_acceptance_list).length,
    acceptance_deliverables: normalizeList(acceptance.deliverables).length,
  };
  return statusMap[sectionKey] ? "已填充" : scene === "acceptance" ? "待补充" : "待补充";
}

function buildProjectBadges(summary) {
  return [summary?.project_type_name, summary?.business_category_name, summary?.project_status_name].filter(Boolean);
}

function acceptanceSectionTitle(sectionKey, fallback) {
  if (sectionKey === "project_review") {
    return "项目内容";
  }
  if (sectionKey === "architecture_review") {
    return "专业技术领域评审";
  }
  if (sectionKey === "tam_models") {
    return "TAM模型评审";
  }
  return fallback || "验收内容";
}

function matchesAcceptanceCategory(rule, category) {
  if (!category) {
    return true;
  }
  return normalizeList(rule?.applicable_categories).some((item) => item?.category === category);
}

function buildAcceptanceVisibility(rulesBundle, category) {
  const explicitSections = orderDefinitionsByKeys(ACCEPTANCE_SECTIONS, rulesBundle?.sections);
  const explicitProjectReviewTabs = orderDefinitionsByKeys(COMMON_REVIEW_TABS, rulesBundle?.project_review_tabs);
  const explicitTamTabs = orderDefinitionsByKeys(TAM_TABS, rulesBundle?.tam_tabs);
  if (explicitSections.length || explicitProjectReviewTabs.length || explicitTamTabs.length) {
    return {
      visibleSections: explicitSections.length ? explicitSections : ACCEPTANCE_SECTIONS,
      visibleProjectReviewTabs: explicitProjectReviewTabs.length ? explicitProjectReviewTabs : COMMON_REVIEW_TABS,
      visibleTamTabs: explicitTamTabs.length ? explicitTamTabs : TAM_TABS,
    };
  }

  const sourceRules = normalizeList(rulesBundle?.rules);
  if (!sourceRules.length) {
    return {
      visibleSections: ACCEPTANCE_SECTIONS,
      visibleProjectReviewTabs: COMMON_REVIEW_TABS,
      visibleTamTabs: TAM_TABS,
    };
  }

  const matchedRules = sourceRules.filter((rule) => matchesAcceptanceCategory(rule, category));
  const visibleRuleTabs = new Set(matchedRules.map((rule) => String(rule?.tab || "").trim()).filter(Boolean));
  const visibleReviewPoints = new Set(matchedRules.map((rule) => String(rule?.review_point || "").trim()).filter(Boolean));

  const visibleSections = ACCEPTANCE_SECTIONS.filter((section) => visibleRuleTabs.has(ACCEPTANCE_SECTION_RULE_TABS[section.key]));
  const visibleProjectReviewTabs = COMMON_REVIEW_TABS.filter((tab) =>
    Object.entries(ACCEPTANCE_REVIEW_POINT_TO_TAB_KEY).some(([point, key]) => key === tab.key && visibleReviewPoints.has(point)),
  );
  const visibleTamTabs = TAM_TABS.filter((tab) =>
    Object.entries(ACCEPTANCE_TAM_POINT_TO_TAB_KEY).some(([point, key]) => key === tab.key && visibleReviewPoints.has(point)),
  );

  return {
    visibleSections: visibleSections.length ? visibleSections : ACCEPTANCE_SECTIONS,
    visibleProjectReviewTabs: visibleProjectReviewTabs.length ? visibleProjectReviewTabs : COMMON_REVIEW_TABS,
    visibleTamTabs: visibleTamTabs.length ? visibleTamTabs : [],
  };
}

function normalizeNumber(value) {
  const numeric = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(numeric) ? numeric : 0;
}

function toTextItems(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim())
      .filter(Boolean);
  }
  const text = String(value || "").trim();
  if (!text) {
    return [];
  }
  return text
    .split(/\r?\n+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function countFilled(values) {
  return values.filter((value) => {
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    return String(value ?? "").trim() !== "";
  }).length;
}

function isTruthyFlag(value) {
  return value === true || value === 1 || value === "1" || value === "true" || value === "yes";
}

function acceptanceScopeTaskStatus(row) {
  const explicit = firstMeaningful(row?.taskStatusName, row?.statusName, row?.status);
  if (explicit && !/^\d+$/.test(String(explicit))) {
    return explicit;
  }
  if (String(row?.settleStatus ?? row?.newTaskStatus ?? row?.fullAcceptStatus ?? "").trim() === "24") {
    return "结算完成";
  }
  if (String(row?.taskStatus ?? "").trim() === "26") {
    return "已完成";
  }
  return explicit || "-";
}

function buildTaskOrderDrawerReasonOptions(taskOrderView) {
  const basicInfo = taskOrderView?.basic_info || {};
  const reasonText = `${firstMeaningful(basicInfo.supplier_reason)} ${firstMeaningful(basicInfo.procurement_note)}`.toLowerCase();
  const options = [
    {
      key: "capability",
      label: "该供应商能力优势领域契合该任务单工作内容，能够提供不可替代的角色或角色能力",
      keywords: ["优势", "能力", "不可替代", "专业", "契合"],
    },
    {
      key: "cost",
      label: "在提供相同人员角色及角色能力的前提下，该供应商的费用成本最优",
      keywords: ["成本", "最优", "费用", "价格", "报价"],
    },
    {
      key: "continuity",
      label: "该任务单为现有系统延续开发，为了满足系统角色能力与原来角色能力一致或配套的要求，需从该供应商处延续采购",
      keywords: ["延续", "现有", "一致", "配套", "原来", "继续"],
    },
  ];
  const matched = options.some((item) => item.keywords.some((keyword) => reasonText.includes(keyword)));
  return options.map((item, index) => ({
    ...item,
    checked: item.keywords.some((keyword) => reasonText.includes(keyword)) || (index === 2 && reasonText && !matched),
  }));
}

function buildTaskOrderDrawerWorkItems(taskOrderView) {
  const taskRows = normalizeList(taskOrderView?.task_assignment?.task_rows);
  if (taskRows.length) {
    return taskRows.map((item, index) => {
      const taskName = firstMeaningful(item?.task_name, item?.taskName, item?.name, `子任务${index + 1}`);
      const detail = firstMeaningful(item?.deliverable, item?.output, item?.complete_standard);
      return `${index + 1}. ${taskName}${detail ? `：${detail}` : ""}`;
    });
  }
  return toTextItems(firstMeaningful(taskOrderView?.basic_info?.task_description, taskOrderView?.technical_requirements?.system_function));
}

function buildTaskOrderDrawerCriteriaItems(taskOrderView) {
  const taskCriteria = normalizeList(taskOrderView?.task_assignment?.task_rows)
    .map((item) => firstMeaningful(item?.complete_standard, item?.acceptStandard))
    .filter((item) => String(item || "").trim() !== "");
  if (taskCriteria.length) {
    return taskCriteria.map((item, index) => `${index + 1}. ${item}`);
  }
  return toTextItems(
    firstMeaningful(
      taskOrderView?.basic_info?.acceptance_criteria,
      taskOrderView?.technical_requirements?.acceptance_criteria,
    ),
  );
}

function buildTaskOrderDrawerEvaluationRows(taskOrderView) {
  const taskRows = normalizeList(taskOrderView?.task_assignment?.task_rows);
  const startDate = formatCompactDate(firstMeaningful(taskOrderView?.start_date, taskOrderView?.basic_info?.start_date));
  const endDate = formatCompactDate(firstMeaningful(taskOrderView?.end_date, taskOrderView?.basic_info?.end_date));
  if (taskRows.length) {
    return taskRows.map((item, index) => ({
      id: item?.id || `evaluation-${index + 1}`,
      task_name: firstMeaningful(item?.task_name, item?.taskName, item?.name, `子任务${index + 1}`),
      start_date: formatCompactDate(firstMeaningful(item?.start_date, item?.startTime, startDate)),
      end_date: formatCompactDate(firstMeaningful(item?.end_date, item?.endTime, endDate)),
    }));
  }
  return [
    {
      id: "evaluation-default",
      task_name: firstMeaningful(taskOrderView?.task_name, taskOrderView?.basic_info?.task_name, "任务单"),
      start_date: startDate,
      end_date: endDate,
    },
  ];
}

function buildTaskOrderDrawerStaffingMatrix(taskOrderView) {
  const rows = normalizeList(taskOrderView?.staffing?.rows);
  if (!rows.length) {
    return [];
  }
  const grouped = new Map();
  rows.forEach((item, index) => {
    const key = firstMeaningful(item?.level_name, item?.post_name, `岗位${index + 1}`);
    const current = grouped.get(key) || { key, people: 0, days: 0 };
    current.people += 1;
    current.days += normalizeNumber(firstMeaningful(item?.expected_days, item?.planDays, item?.workDays));
    grouped.set(key, current);
  });
  return Array.from(grouped.values());
}

function acceptanceMemberPartyLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "1") {
    return "三方";
  }
  if (normalized === "0") {
    return "自有";
  }
  if (normalized === "third") {
    return "三方";
  }
  if (normalized === "own") {
    return "自有";
  }
  return "--";
}

function buildAcceptanceDetailProcessRows(taskRow, taskOrderView, documentPayload, deliverableRow) {
  const taskAssignment = taskOrderView?.task_assignment || {};
  const scopeProcesses = normalizeList(documentPayload?.scope?.business_processes);
  const processRows = flattenTaskDetailObjects(taskAssignment.process_rows);
  const sourceRows = processRows.length
    ? processRows
    : scopeProcesses;
  const totalTaskCount = firstMeaningful(
    deliverableRow?.taskTargetNumNew,
    deliverableRow?.taskTargetNum,
    normalizeList(taskAssignment.task_rows).length,
    0,
  );
  const completedTaskCount = firstMeaningful(
    deliverableRow?.taskFactNumNew,
    deliverableRow?.taskFactNum,
    normalizeList(taskAssignment.task_rows).length,
    0,
  );
  const developCategory = firstMeaningful(
    taskRow?.taskTypeName,
    taskRow?.taskType,
    String(documentPayload?.project_summary?.project_type_name || "").includes("优化") ? "迭代优化" : "",
    documentPayload?.project_summary?.business_subcategory_name,
    "迭代优化",
  );
  return sourceRows.map((item, index) => {
    const processCode = firstMeaningful(item?.process_code, item?.processCode, item?.code, item?.processId, item?.businessUnitCode);
    const scopeProcess = scopeProcesses.find((scopeItem) => firstMeaningful(scopeItem?.code, scopeItem?.processCode) === processCode) || {};
    return {
      id: item?.id || `process-detail-${index + 1}`,
      process_code: processCode,
      process_name: firstMeaningful(item?.process_name, item?.processName, item?.name, item?.businessFlow, scopeProcess?.name),
      process_level: firstMeaningful(item?.level, item?.processLevel, item?.level_name, scopeProcess?.level),
      process_role: firstMeaningful(item?.roleName, item?.businessRole, item?.owner, "--"),
      total_task_count: totalTaskCount,
      completed_task_count: completedTaskCount,
      created_at: formatCompactDate(firstMeaningful(item?.created, item?.createTime, item?.start_date, item?.startTime, taskRow?.taskStartTime)),
      develop_category: developCategory,
    };
  });
}

function buildAcceptanceDetailMemberRows(taskOrderView) {
  const basicInfo = taskOrderView?.basic_info || {};
  const rows = normalizeList(taskOrderView?.staffing?.rows);
  return rows.map((item, index) => ({
    id: item?.id || `member-detail-${index + 1}`,
    name: firstMeaningful(item?.name, item?.userName, item?.employeeName, `成员${index + 1}`),
    ownership: acceptanceMemberPartyLabel(firstMeaningful(item?.party_type, item?.peopleFlag)),
    position: firstMeaningful(item?.post_name, item?.postName, item?.roleName, item?.jobName),
    level: firstMeaningful(item?.level, item?.level_name, item?.levelName, item?.gradeName),
    department: firstMeaningful(item?.department_name, item?.departmentName, basicInfo.supplier_name, taskOrderView?.supplier_name),
    efficiency_score: firstMeaningful(item?.efficiency_score, item?.score, 0),
  }));
}

function buildTaskOrders(documentPayload) {
  if (!documentPayload) {
    return [];
  }

  const summary = documentPayload?.project_summary || {};
  const milestones = documentPayload?.milestones || {};
  const scope = documentPayload?.scope || {};
  const organization = documentPayload?.organization || {};
  const projectContent = documentPayload?.project_content || {};
  const relatedProducts = normalizeList(documentPayload?.okr?.related_products)
    .map((item) => firstMeaningful(item?.productName, item?.productFullName, item?.name, item?.label, item))
    .filter(Boolean);
  const keyResults = normalizeList(documentPayload?.okr?.key_results)
    .map((item) => firstMeaningful(item?.krName, item?.name, item?.title, item?.description, item))
    .filter(Boolean);
  const projectGoals = [documentPayload?.okr?.objective, ...keyResults].filter((item) => String(item || "").trim() !== "");
  const startDate = firstMeaningful(milestones?.target_plan?.start, milestones?.approval_plan?.start, milestones?.contract_plan?.start);
  const endDate = firstMeaningful(milestones?.target_plan?.end, milestones?.approval_plan?.end, milestones?.contract_plan?.end);
  const supplierName = firstMeaningful(
    normalizeList(organization.members).find((item) => item?.party_type === "third")?.name,
    normalizeList(organization.members)[0]?.name,
    summary.project_manager_name,
  );
  const contractName = firstMeaningful(
    normalizeList(documentPayload?.budget?.cost_items)[0]?.name,
    `${summary.project_name || documentPayload?.project_name || "项目"}任务执行合同`,
  );
  const contractNo = firstMeaningful(summary.project_code, documentPayload?.project_id, "TASK-CONTRACT");
  const businessUnits = normalizeList(scope.content_list)
    .slice(0, 8)
    .map((item, index) => ({
      id: item?.id || `business-unit-${index + 1}`,
      business_object: firstMeaningful(item?.businessObjectName, item?.businessObject, item?.name, item?.systemName, `业务对象${index + 1}`),
      business_unit: firstMeaningful(item?.businessUnitName, item?.lineName, item?.typeName, item?.categoryName, `业务单元${index + 1}`),
      business_process: firstMeaningful(item?.processName, item?.flowName, item?.content, item?.description, item?.name, `业务流程${index + 1}`),
    }));
  const approvalNodes = [
    {
      id: "approval-business",
      function_name: "业务架构核对",
      removed_nodes: normalizeList(scope.business_processes).length ? 1 : 0,
      description: normalizeList(scope.business_processes).length ? "已识别业务过程，可沉淀标准任务流。" : "待补充业务过程后生成审批优化建议。",
    },
    {
      id: "approval-data",
      function_name: "数据与系统核对",
      removed_nodes: normalizeList(scope.microservices).length ? 1 : 0,
      description: normalizeList(scope.microservices).length ? "已识别系统范围，可收敛人工确认节点。" : "待补充系统范围与接口要求。",
    },
  ];
  const processRows = normalizeList(scope.business_processes)
    .slice(0, 8)
    .map((item, index) => ({
      id: item?.id || `process-${index + 1}`,
      process_name: firstMeaningful(item?.name, item?.processName, item?.code, `业务流程${index + 1}`),
      process_code: firstMeaningful(item?.code, item?.processCode, item?.id, `P-${index + 1}`),
      owner: firstMeaningful(summary.project_manager_name, supplierName, "待补充"),
      output: firstMeaningful(item?.futureTime, item?.actualTime, item?.type, "阶段输出"),
    }));
  const taskRows = (processRows.length ? processRows : businessUnits)
    .slice(0, 6)
    .map((item, index) => ({
      id: item?.id || `task-${index + 1}`,
      task_name: firstMeaningful(item?.process_name, item?.business_process, item?.business_object, `任务${index + 1}`),
      task_owner: firstMeaningful(summary.project_manager_name, supplierName, "待补充"),
      deliverable: firstMeaningful(item?.output, item?.business_unit, "任务交付物"),
      complete_standard: keyResults[index] || "完成任务范围并通过阶段确认",
    }));
  const metricRows = keyResults.map((item, index) => ({
    id: `metric-${index + 1}`,
    metric_name: item,
    metric_type: "项目指标",
    target_value: "达成",
  }));
  const staffingRows = normalizeList(organization.members).map((member, index) => {
    const estimatedDays = normalizeNumber(member?.workload);
    const unitPrice = member?.party_type === "third" ? 1800 : 1200;
    return {
      id: member?.employee_id || `${member?.name || "member"}-${index + 1}`,
      name: member?.name || `成员${index + 1}`,
      post_name: member?.role || "实施角色",
      level_name: member?.level || "待补充",
      expected_days: estimatedDays || "",
      unit_price: unitPrice,
      estimated_cost: estimatedDays ? estimatedDays * unitPrice : "",
      department_name: member?.department || summary.department_name || "",
      start_date: member?.plan_start_date || startDate,
      end_date: member?.plan_end_date || endDate,
    };
  });
  const currentCostRows = staffingRows.map((item) => ({
    id: `cost-${item.id}`,
    post_name: item.post_name,
    level_name: item.level_name,
    expected_days: item.expected_days,
    unit_price: item.unit_price,
    estimated_cost: item.estimated_cost,
  }));
  const historyCostRows = normalizeList(documentPayload?.cost_change?.history_items).map((item, index) => ({
    id: item?.projectCode || item?.projectName || `history-${index + 1}`,
    task_name: firstMeaningful(item?.projectName, item?.taskName, item?.name, `历史任务单${index + 1}`),
    task_code: firstMeaningful(item?.projectCode, item?.taskNo, item?.code, `H-${index + 1}`),
    total_cost: firstMeaningful(item?.totalCost, item?.amount, item?.cost, ""),
    status: firstMeaningful(item?.status, item?.projectStatusName, "已完成"),
  }));
  const totalDays = staffingRows.reduce((sum, item) => sum + normalizeNumber(item.expected_days), 0);
  const totalCost = currentCostRows.reduce((sum, item) => sum + normalizeNumber(item.estimated_cost), 0);
  const historyTotalCost = historyCostRows.reduce((sum, item) => sum + normalizeNumber(item.total_cost), 0);
  const projectBudgetAmount = totalCost || normalizeNumber(normalizeList(documentPayload?.budget?.cost_items)[0]?.amount);
  const technicalRequirements = {
    system_function: firstMeaningful(projectContent?.solution?.content, documentPayload?.project_value, documentPayload?.okr?.objective),
    system_architecture: firstMeaningful(documentPayload?.architecture_reviews?.technology, documentPayload?.architecture_reviews?.business),
    integration_requirements: normalizeList(scope.microservices).length
      ? `需对接 ${normalizeList(scope.microservices).length} 个系统/微应用对象。`
      : "",
    database_requirements: firstMeaningful(documentPayload?.architecture_reviews?.data, normalizeList(documentPayload?.budget?.cost_items)[0]?.budget_subject),
    performance_requirements: startDate && endDate ? `需在 ${startDate} 至 ${endDate} 内完成交付。` : "",
    security_requirements: firstMeaningful(documentPayload?.architecture_reviews?.security, projectContent?.acceptance_plan?.content),
    scalability_requirements: normalizeList(scope.content_list).length ? `已识别 ${normalizeList(scope.content_list).length} 条范围内容，需保留扩展余量。` : "",
    tech_stack_requirements: firstMeaningful(summary.project_type_name, summary.business_subcategory_name),
    frontend_requirements: firstMeaningful(projectContent?.panorama?.content, projectContent?.solution?.content),
    compatibility_requirements: normalizeList(scope.microapps).length ? "需兼容现有微应用和系统范围。" : "",
    quality_requirements: normalizeList(taskRows).length ? `当前任务拆分 ${normalizeList(taskRows).length} 项，需逐项验收闭环。` : "",
    schedule_requirements: firstMeaningful(milestones?.target_plan?.title, milestones?.approval_plan?.title),
    handover_requirements: firstMeaningful(projectContent?.target?.content, documentPayload?.cost_change?.reason),
    handover_items: relatedProducts.join("、"),
    acceptance_criteria: projectGoals.join("；"),
  };

  const taskId = firstMeaningful(summary.project_code, documentPayload?.project_id, "TASK").replace(/\s+/g, "-");
  return [
    {
      id: `${taskId}-001`,
      task_no: `${taskId}-001`,
      task_name: `${summary.project_name || documentPayload?.project_name || "项目"}任务单`,
      supplier_name: supplierName || "待补充",
      project_name: summary.project_name || documentPayload?.project_name || documentPayload?.project_id,
      domain_name: summary.domain_name || "待补充",
      request_budget: projectBudgetAmount,
      annual_budget: projectBudgetAmount,
      start_date: startDate,
      end_date: endDate,
      approved_at: firstMeaningful(milestones?.approval_plan?.end, milestones?.target_plan?.start),
      project_ownership: {
        project_code: summary.project_code,
        project_manager: summary.project_manager_name,
        department_name: summary.department_name,
        domain_name: summary.domain_name,
      },
      classification: {
        project_category_name: summary.project_category_name || summary.project_type_name,
        business_category_name: summary.business_category_name,
        business_subcategory_name: summary.business_subcategory_name,
        project_level_name: summary.project_level_name,
      },
      budget_overview: {
        project_budget: projectBudgetAmount,
        project_year_budget: projectBudgetAmount,
        project_used_budget: totalCost,
        project_remaining_budget: Math.max(projectBudgetAmount - totalCost, 0),
      },
      basic_info: {
        task_name: `${summary.project_name || documentPayload?.project_name || "项目"}任务单`,
        task_no: `${taskId}-001`,
        start_date: startDate,
        end_date: endDate,
        supplier_name: supplierName,
        contract_name: contractName,
        contract_no: contractNo,
        target_list: projectGoals,
        related_products: relatedProducts,
        supplier_reason: firstMeaningful(documentPayload?.cost_change?.reason, documentPayload?.project_value),
        procurement_note: firstMeaningful(projectContent?.solution?.content, projectContent?.target?.content),
      },
      business_architecture: {
        business_units: businessUnits,
        approval_nodes: approvalNodes,
      },
      task_assignment: {
        process_rows: processRows,
        task_rows: taskRows,
        metric_rows: metricRows,
      },
      staffing: {
        rows: staffingRows,
        total_days: totalDays,
        total_cost: totalCost,
        development_mode: organization?.development_mode || "待补充",
      },
      cost_estimation: {
        current_rows: currentCostRows,
        total_cost: totalCost,
        history_rows: historyCostRows,
        history_total_cost: historyTotalCost || normalizeNumber(documentPayload?.cost_change?.history_total_cost),
      },
      technical_requirements: technicalRequirements,
    },
  ];
}

function flattenTaskDetailObjects(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => item && typeof item === "object");
  }
  if (!value || typeof value !== "object") {
    return [];
  }
  const nestedRows = [
    ...normalizeList(value?.flowListFromProject),
    ...normalizeList(value?.flowListAll),
    ...normalizeList(value?.dataList),
    ...normalizeList(value?.list),
    ...normalizeList(value?.rows),
    ...normalizeList(value?.records),
    ...normalizeList(value?.items),
    ...normalizeList(value?.partInfos),
  ].filter((item) => item && typeof item === "object");
  if (nestedRows.length) {
    return nestedRows;
  }
  return [value];
}

function flattenTaskSpecText(rows, keywords = []) {
  const loweredKeywords = keywords.map((item) => String(item || "").toLowerCase());
  const candidates = flattenTaskDetailObjects(rows);
  for (const row of candidates) {
    const haystack = Object.values(row).map((item) => String(item ?? "")).join(" ").toLowerCase();
    if (loweredKeywords.length && !loweredKeywords.every((keyword) => haystack.includes(keyword))) {
      continue;
    }
    const value = firstMeaningful(
      row.requirementContent,
      row.requireContent,
      row.specContent,
      row.content,
      row.remark,
      row.description,
      row.requirementDesc,
      row.requireDesc,
      row.demandContent,
    );
    if (String(value || "").trim()) {
      return value;
    }
  }
  return "";
}

function buildTaskOrderViewModel(taskOrderSummary, taskOrderDetail, documentPayload) {
  const fallback = buildTaskOrders(documentPayload)[0] || null;
  if (!taskOrderSummary && !fallback) {
    return null;
  }
  if (!taskOrderSummary) {
    return fallback;
  }

  const summary = taskOrderSummary || {};
  const baseRows = flattenTaskDetailObjects(taskOrderDetail?.base_detail);
  const baseInfo = baseRows[0] || {};
  const businessUnitsPayload = taskOrderDetail?.business_units;
  const approvalNodesPayload = taskOrderDetail?.approval_nodes;
  const businessUnits = flattenTaskDetailObjects(businessUnitsPayload?.objList || businessUnitsPayload);
  const approvalNodes = flattenTaskDetailObjects(
    approvalNodesPayload?.firstNodeList?.length || approvalNodesPayload?.secondNodeList?.length
      ? [...normalizeList(approvalNodesPayload?.firstNodeList), ...normalizeList(approvalNodesPayload?.secondNodeList)]
      : approvalNodesPayload,
  );
  const processRows = flattenTaskDetailObjects(taskOrderDetail?.process_rows);
  const matrixRows = flattenTaskDetailObjects(taskOrderDetail?.matrix_rows);
  const historyRows = flattenTaskDetailObjects(taskOrderDetail?.history_rows);
  const specRows = flattenTaskDetailObjects(taskOrderDetail?.spec_rows);
  const fallbackInfo = fallback?.basic_info || {};
  const fallbackStaffing = fallback?.staffing || {};
  const fallbackCost = fallback?.cost_estimation || {};
  const fallbackTech = fallback?.technical_requirements || {};
  const supplierReasonText = firstMeaningful(baseInfo.supplierReason, baseInfo.reason, fallbackInfo.supplier_reason);
  const procurementNoteText = firstMeaningful(baseInfo.procurementNote, baseInfo.purchaseRemark, baseInfo.buyRemark, fallbackInfo.procurement_note);
  const taskDescriptionText = firstMeaningful(
    baseInfo.taskDescription,
    baseInfo.taskContent,
    baseInfo.workTask,
    baseInfo.workContent,
    baseInfo.description,
    summary.taskDescription,
    summary.taskDesc,
    fallbackInfo.task_description,
  );
  const acceptanceCriteriaText = firstMeaningful(
    baseInfo.acceptStandard,
    baseInfo.acceptanceCriteria,
    baseInfo.acceptCriteria,
    baseInfo.acceptContent,
    summary.acceptStandard,
    fallbackInfo.acceptance_criteria,
  );

  const normalizedTaskRows = processRows.length
    ? processRows.map((item, index) => ({
        ...item,
        id: item.id || item.taskId || `process-task-${index + 1}`,
        task_name: firstMeaningful(item.task_name, item.taskName, item.processName, item.process_name, item.name, `任务${index + 1}`),
        task_owner: firstMeaningful(item.task_owner, item.ownerName, item.owner, item.createUser, "待补充"),
        deliverable: firstMeaningful(item.deliverable, item.output, item.outPut, item.resultName, item.result, "任务交付物"),
        complete_standard: firstMeaningful(item.complete_standard, item.standard, item.acceptStandard, item.remark, "完成任务范围并通过阶段确认"),
      }))
    : normalizeList(fallback?.task_assignment?.task_rows);

  const normalizedMatrixRows = matrixRows.length
      ? matrixRows.map((item, index) => ({
        ...item,
        id: item.id || item.userId || item.employeeId || `matrix-${index + 1}`,
        name: firstMeaningful(item.name, item.userName, item.employeeName, item.memberName, item.personName, item.realName),
        post_name: firstMeaningful(item.post_name, item.postName, item.roleName, item.jobName, item.positionName, item.stationName),
        level_name: firstMeaningful(item.level, item.level_name, item.levelName, item.gradeName, item.rankName, item.userLevelName),
        level: firstMeaningful(item.level, item.level_name, item.levelName, item.gradeName, item.rankName, item.userLevelName),
        expected_days: firstMeaningful(item.expected_days, item.expectedDays, item.planDays, item.taskCostDay, item.workDays, item.days, item.manDay, item.workload),
        unit_price: firstMeaningful(item.unit_price, item.unitPrice, item.price, item.dayPrice, item.personDayPrice),
        estimated_cost: firstMeaningful(item.estimated_cost, item.estimatedCost, item.totalCost, item.cost, item.amount),
        department_name: firstMeaningful(item.department_name, item.departmentName, item.deptName, item.orgName, item.supplierName, item.vendorName),
        party_type: firstMeaningful(item.party_type, item.partyType, item.peopleFlag, item.sourceType, item.memberType, item.userType),
        peopleFlag: firstMeaningful(item.peopleFlag, item.party_type, item.partyType),
        efficiency_score: firstMeaningful(item.efficiency_score, item.efficiencyScore, item.aiEfficiencyScore, item.bigScreenEfficiencyScore, item.taskScore, item.score, item.kpiScore, item.performanceScore),
      }))
    : normalizeList(fallbackStaffing.rows);

  const normalizedHistoryRows = historyRows.length
    ? historyRows.map((item, index) => ({
        ...item,
        id: item.id || item.taskId || item.projectId || `history-${index + 1}`,
        task_name: firstMeaningful(item.task_name, item.taskName, item.projectName, item.name, `历史任务单${index + 1}`),
        task_code: firstMeaningful(item.task_code, item.taskCode, item.taskNo, item.projectCode, item.code),
        total_cost: firstMeaningful(item.total_cost, item.totalCost, item.amount, item.cost),
        status: firstMeaningful(item.status, item.statusName, item.taskStatusName, item.projectStatusName),
      }))
    : normalizeList(fallbackCost.history_rows);

  const totalDays = firstMeaningful(
    summary.taskTotalManday,
    summary.taskCostDay,
    normalizedMatrixRows.reduce((sum, item) => sum + normalizeNumber(item.expected_days), 0),
    fallbackStaffing.total_days,
  );
  const totalCost = firstMeaningful(
    summary.issueAmountNoTax,
    summary.issueAmountTax,
    normalizedMatrixRows.reduce((sum, item) => sum + normalizeNumber(item.estimated_cost), 0),
    fallbackCost.total_cost,
  );

  return {
    ...(fallback || {}),
    id: String(summary.id || fallback?.id || ""),
    task_no: firstMeaningful(summary.taskOrderNo, summary.taskSerialCode, summary.taskCode, summary.taskNo, summary.serialNo, fallback?.task_no),
    task_name: firstMeaningful(summary.taskOrderName, summary.taskName, summary.name, fallback?.task_name),
    supplier_name: firstMeaningful(summary.supplierName, fallback?.supplier_name),
    project_name: firstMeaningful(summary.projectName, fallback?.project_name),
    domain_name: firstMeaningful(summary.domainName, summary.belongTeamName, fallback?.domain_name),
    request_budget: firstMeaningful(summary.applyTotalBudget, summary.applyBudgetTotal, summary.taskAmount, summary.taskAmountTax, summary.planTotalCost, fallback?.request_budget),
    annual_budget: firstMeaningful(summary.applyYearBudget, summary.applyBudgetYear, summary.taskAmount, summary.taskAmountTax, summary.planTotalCost, fallback?.annual_budget),
    start_date: firstMeaningful(summary.startTime, summary.planStartTime, summary.taskStartTime, fallback?.start_date),
    end_date: firstMeaningful(summary.endTime, summary.planEndTime, summary.taskEndTime, fallback?.end_date),
    approved_at: firstMeaningful(summary.approvalPassTime, summary.taskAduitTime, fallback?.approved_at),
    project_ownership: {
      ...(fallback?.project_ownership || {}),
      project_code: firstMeaningful(summary.projectCode, summary.projectNo, fallback?.project_ownership?.project_code),
      project_manager: firstMeaningful(summary.projectManagerName, summary.project_manager_name, fallback?.project_ownership?.project_manager),
      department_name: firstMeaningful(
        summary.departmentName,
        summary.department_name,
        summary.putDepartmentName,
        summary.taskPutDeptName,
        summary.taskDeptName,
        fallback?.project_ownership?.department_name,
      ),
    },
    classification: {
      ...(fallback?.classification || {}),
    },
    budget_overview: {
      project_budget: firstMeaningful(summary.applyTotalBudget, summary.applyBudgetTotal, summary.taskAmount, summary.taskAmountTax, summary.planTotalCost, fallback?.budget_overview?.project_budget),
      project_year_budget: firstMeaningful(summary.applyYearBudget, summary.applyBudgetYear, summary.taskAmount, summary.taskAmountTax, summary.planTotalCost, fallback?.budget_overview?.project_year_budget),
      project_used_budget: firstMeaningful(summary.issueAmountNoTax, summary.issueAmountTax, summary.totalAcceptCost, summary.acceptanceAmountTax, fallback?.budget_overview?.project_used_budget),
      project_remaining_budget: fallback?.budget_overview?.project_remaining_budget,
    },
    basic_info: {
      ...fallbackInfo,
      task_name: firstMeaningful(summary.taskOrderName, summary.taskName, summary.name, baseInfo.taskName, baseInfo.name, fallbackInfo.task_name),
      task_no: firstMeaningful(summary.taskOrderNo, summary.taskSerialCode, summary.taskCode, summary.taskNo, summary.serialNo, baseInfo.taskNo, baseInfo.taskCode, fallbackInfo.task_no),
      start_date: firstMeaningful(summary.startTime, summary.planStartTime, summary.taskStartTime, baseInfo.startTime, baseInfo.planStartTime, fallbackInfo.start_date),
      end_date: firstMeaningful(summary.endTime, summary.planEndTime, summary.taskEndTime, baseInfo.endTime, baseInfo.planEndTime, fallbackInfo.end_date),
      supplier_name: firstMeaningful(summary.supplierName, baseInfo.supplierName, fallbackInfo.supplier_name),
      contract_name: firstMeaningful(summary.contractName, baseInfo.contractName, baseInfo.contractTitle, fallbackInfo.contract_name),
      contract_no: firstMeaningful(summary.contractCode, summary.contractNo, baseInfo.contractCode, baseInfo.contractNo, fallbackInfo.contract_no),
      target_list: normalizeList(baseInfo.targetListEstablishment || baseInfo.targetList || fallbackInfo.target_list),
      related_products: normalizeList(baseInfo.checkSupplierReason || baseInfo.productList || fallbackInfo.related_products),
      supplier_reason: supplierReasonText,
      procurement_note: procurementNoteText,
      supplier_contact: firstMeaningful(summary.supplierManageName, baseInfo.supplierManageName, baseInfo.supplierManagerName, fallbackInfo.supplier_contact),
      task_department: firstMeaningful(
        summary.putDepartmentName,
        summary.taskPutDeptName,
        summary.taskDeptName,
        summary.departmentName,
        baseInfo.putDepartmentName,
        baseInfo.taskPutDeptName,
        baseInfo.taskDeptName,
        fallbackInfo.task_department,
      ),
      task_description: taskDescriptionText,
      acceptance_criteria: acceptanceCriteriaText,
    },
    business_architecture: {
      business_units: businessUnits.length ? businessUnits : normalizeList(fallback?.business_architecture?.business_units),
      approval_nodes: approvalNodes.length ? approvalNodes : normalizeList(fallback?.business_architecture?.approval_nodes),
    },
    task_assignment: {
      process_rows: processRows.length ? processRows : normalizeList(fallback?.task_assignment?.process_rows),
      task_rows: normalizedTaskRows,
      metric_rows: normalizeList(fallback?.task_assignment?.metric_rows),
    },
    staffing: {
      ...fallbackStaffing,
      rows: normalizedMatrixRows,
      total_days: totalDays,
      total_cost: totalCost,
    },
    cost_estimation: {
      ...fallbackCost,
      current_rows: normalizedMatrixRows,
      total_cost: totalCost,
      history_rows: normalizedHistoryRows,
      history_total_cost:
        normalizedHistoryRows.reduce((sum, item) => sum + normalizeNumber(item.total_cost), 0) || fallbackCost.history_total_cost,
    },
    technical_requirements: {
      ...fallbackTech,
      system_function: flattenTaskSpecText(specRows, ["功能"]) || fallbackTech.system_function,
      system_architecture: flattenTaskSpecText(specRows, ["架构"]) || fallbackTech.system_architecture,
      integration_requirements: flattenTaskSpecText(specRows, ["接口"]) || fallbackTech.integration_requirements,
      database_requirements: flattenTaskSpecText(specRows, ["数据库"]) || fallbackTech.database_requirements,
      performance_requirements: flattenTaskSpecText(specRows, ["性能"]) || fallbackTech.performance_requirements,
      security_requirements: flattenTaskSpecText(specRows, ["安全"]) || fallbackTech.security_requirements,
      scalability_requirements: flattenTaskSpecText(specRows, ["扩展"]) || fallbackTech.scalability_requirements,
      tech_stack_requirements: flattenTaskSpecText(specRows, ["技术"]) || fallbackTech.tech_stack_requirements,
      frontend_requirements: flattenTaskSpecText(specRows, ["前端"]) || fallbackTech.frontend_requirements,
      compatibility_requirements: flattenTaskSpecText(specRows, ["兼容"]) || fallbackTech.compatibility_requirements,
      quality_requirements: flattenTaskSpecText(specRows, ["质量"]) || fallbackTech.quality_requirements,
      schedule_requirements: flattenTaskSpecText(specRows, ["进度"]) || fallbackTech.schedule_requirements,
      handover_requirements: flattenTaskSpecText(specRows, ["交接"]) || fallbackTech.handover_requirements,
      handover_items: flattenTaskSpecText(specRows, ["交付"]) || fallbackTech.handover_items,
      acceptance_criteria: flattenTaskSpecText(specRows, ["验收"]) || fallbackTech.acceptance_criteria,
      spec_rows: specRows,
    },
  };
}

function resolveAcceptanceContractIdentity(row, options = {}) {
  const allowRowId = Boolean(options.allowRowId);
  const contractId = String(
    firstMeaningful(
      row?.contractId,
      row?.contract_id,
      row?.contractBasicId,
      row?.basicContractId,
      allowRowId ? row?.id : "",
    ),
  ).trim();
  const contractNumber = String(
    firstMeaningful(row?.contractNo, row?.contractNumber, row?.contractCode, row?.contract_code, row?.serialNo),
  ).trim();
  return { contractId, contractNumber };
}

function contractPerformanceLabel(value) {
  const normalized = String(value ?? "").trim();
  if (!normalized) {
    return "-";
  }
  if (["0", "false", "否", "N", "n"].includes(normalized)) {
    return "否";
  }
  if (["1", "true", "是", "Y", "y"].includes(normalized)) {
    return "是";
  }
  return normalized;
}

function buildContractPartyRows(contractDetail) {
  const rawRows = [
    ...normalizeList(contractDetail?.relativeParties),
    ...normalizeList(contractDetail?.partyList),
    ...normalizeList(contractDetail?.counterpartList),
    ...normalizeList(contractDetail?.signSubjectList),
    ...normalizeList(contractDetail?.contractRelativeList),
    ...normalizeList(contractDetail?.contractPartyList),
  ].filter((item) => item && typeof item === "object");
  return rawRows.map((item, index) => ({
    id: item.id || item.relativeId || item.partyId || `party-${index + 1}`,
    name: firstMeaningful(item?.relativeName, item?.partyName, item?.supplierName, item?.name),
    address: firstMeaningful(item?.relativeAddress, item?.partyAddress, item?.address, item?.registerAddress),
    legalPerson: firstMeaningful(item?.legalPerson, item?.legalRepresentative, item?.corporationName),
    nature: firstMeaningful(item?.relativeTypeName, item?.partyNatureName, item?.partyTypeName, item?.natureName, item?.relativeNature),
  }));
}

function buildAcceptanceContractViewModel(contractSummary, contractDetail, documentPayload) {
  const summary = contractSummary || {};
  const detail = contractDetail || {};
  return {
    contract_name: firstMeaningful(detail?.contractName, detail?.name, summary?.contractName, summary?.name),
    contract_number: firstMeaningful(detail?.contractNumber, detail?.contractNo, detail?.contractCode, summary?.contractNo, summary?.contractCode),
    contract_subject: firstMeaningful(
      detail?.contractMainBody,
      detail?.contractSubject,
      detail?.mainBodyName,
      detail?.signMainName,
      summary?.contractSubject,
    ),
    contract_amount_tax: firstMeaningful(detail?.contractAmountTax, detail?.contractAmount, detail?.amountTax, summary?.amountTax, summary?.amount),
    contract_amount_no_tax: firstMeaningful(detail?.contractAmountNoTax, detail?.amountNoTax, detail?.contractNoTaxAmount, summary?.amountNoTax),
    contract_category: firstMeaningful(detail?.contractCategoryName, detail?.belongContractTypeName, detail?.belongCategoryName, summary?.contractCategoryName),
    contract_subcategory: firstMeaningful(detail?.contractSubclassName, detail?.contractSubTypeName, detail?.contractTypeName, summary?.contractTypeName),
    supplier_name: firstMeaningful(detail?.supplierName, detail?.supplierFullName, detail?.signSupplierName, summary?.supplierName),
    demand_department: firstMeaningful(
      detail?.actualDemandDeptName,
      detail?.actualNeedDeptName,
      detail?.demandDeptName,
      detail?.requireDeptName,
      summary?.demandDeptName,
    ),
    demand_user: firstMeaningful(
      detail?.actualDemandUserName,
      detail?.actualNeedUserName,
      detail?.demandUserName,
      detail?.requireUserName,
      summary?.demandUserName,
    ),
    contract_type: firstMeaningful(detail?.contractOpenTypeName, detail?.openCloseContractName, detail?.contractTypeLabel, summary?.contractTypeLabel),
    start_time: firstMeaningful(detail?.contractStartTime, detail?.startTime, detail?.effectiveDate),
    end_time: firstMeaningful(detail?.contractEndTime, detail?.endTime, detail?.expireDate),
    involves_performance: contractPerformanceLabel(
      firstMeaningful(detail?.isPerformance, detail?.performanceFlag, detail?.isInvolveFulfillment, detail?.performanceLabel),
    ),
    tax_rate: firstMeaningful(detail?.taxRate, detail?.rate, summary?.taxRate),
    project_name: firstMeaningful(detail?.projectName, summary?.projectName, documentPayload?.project_name),
    parties: buildContractPartyRows(detail),
  };
}

function taskOrderSectionStatus(order, sectionKey) {
  if (!order) {
    return "未填写";
  }
  const basicInfo = order.basic_info || {};
  const businessArchitecture = order.business_architecture || {};
  const taskAssignment = order.task_assignment || {};
  const staffing = order.staffing || {};
  const costEstimation = order.cost_estimation || {};
  const technicalRequirements = order.technical_requirements || {};
  const completionMap = {
    basic_info: {
      total: 10,
      filled: countFilled([
        basicInfo.task_name,
        basicInfo.task_no,
        basicInfo.start_date,
        basicInfo.end_date,
        basicInfo.supplier_name,
        basicInfo.contract_name,
        basicInfo.contract_no,
        basicInfo.target_list,
        basicInfo.related_products,
        basicInfo.procurement_note,
      ]),
    },
    business_architecture: {
      total: 2,
      filled: countFilled([normalizeList(businessArchitecture.business_units), normalizeList(businessArchitecture.approval_nodes)]),
    },
    task_assignment: {
      total: 3,
      filled: countFilled([
        normalizeList(taskAssignment.process_rows),
        normalizeList(taskAssignment.task_rows),
        normalizeList(taskAssignment.metric_rows),
      ]),
    },
    staffing: {
      total: 3,
      filled: countFilled([normalizeList(staffing.rows), staffing.total_days, staffing.total_cost]),
    },
    cost_estimation: {
      total: 3,
      filled: countFilled([
        normalizeList(costEstimation.current_rows),
        costEstimation.total_cost,
        normalizeList(costEstimation.history_rows),
      ]),
    },
    technical_requirements: {
      total: 14,
      filled: countFilled(Object.values(technicalRequirements)),
    },
  };
  const completion = completionMap[sectionKey];
  if (!completion || completion.filled <= 0) {
    return "未填写";
  }
  if (completion.filled >= completion.total) {
    return "已填写";
  }
  return "待补充";
}

function pickColumns(rows, preferredKeys = []) {
  const allKeys = new Set(preferredKeys);
  normalizeList(rows).forEach((row) => {
    if (row && typeof row === "object") {
      Object.keys(row).forEach((key) => allKeys.add(key));
    }
  });
  return Array.from(allKeys).filter(Boolean).slice(0, 8);
}

function DefinitionGrid({ items }) {
  return (
    <div className="viewer-kv-grid">
      {items.map((item) => (
        <div key={item.label} className="viewer-kv-item">
          <p className="viewer-kv-label">{item.label}</p>
          <p className="viewer-kv-value">{formatValue(item.value)}</p>
        </div>
      ))}
    </div>
  );
}

function DataTable({ rows, preferredKeys = [], emptyText = "暂无数据" }) {
  const normalizedRows = normalizeList(rows).filter((row) => row && typeof row === "object");
  const columns = pickColumns(normalizedRows, preferredKeys);
  if (!normalizedRows.length || !columns.length) {
    return <p className="viewer-empty">{emptyText}</p>;
  }
  return (
    <div className="table-wrap">
      <table className="compact-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {normalizedRows.map((row, index) => (
            <tr key={row.id || `${index}`}> 
              {columns.map((column) => (
                <td key={column}>{formatValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function machineScopeYearLabels(budgetYear) {
  const numericYear = Number(String(budgetYear || "").replace(/[^\d]/g, ""));
  if (Number.isFinite(numericYear) && numericYear > 2000) {
    return { previous: numericYear - 1, current: numericYear };
  }
  return { previous: "上一年", current: "当年" };
}

function MachineScopeTable({ rows, budgetYear, emptyText = "暂无范围明细数据" }) {
  const normalizedRows = normalizeList(rows).filter((row) => row && typeof row === "object");
  if (!normalizedRows.length) {
    return <p className="viewer-empty">{emptyText}</p>;
  }
  const yearLabels = machineScopeYearLabels(budgetYear);
  return (
    <div className="table-wrap viewer-scope-table-wrap">
      <table className="compact-table viewer-scope-table">
        <thead>
          <tr>
            <th rowSpan="2">序号</th>
            <th rowSpan="2">系统名称</th>
            <th rowSpan="2">需求类型</th>
            <th rowSpan="2">配置/型号</th>
            <th colSpan="2">{yearLabels.previous}年费用(元)</th>
            <th rowSpan="2">小计</th>
            <th colSpan="2">{yearLabels.current}年费用(元)</th>
          </tr>
          <tr>
            <th>数量</th>
            <th>费用</th>
            <th>数量</th>
            <th>费用</th>
          </tr>
        </thead>
        <tbody>
          {normalizedRows.map((row, index) => (
            <tr key={row.id || `${index}`}>
              <td>{index + 1}</td>
              <td>{formatValue(firstMeaningful(row.machineName, row.name, row.systemName))}</td>
              <td>{formatValue(firstMeaningful(row.demandType, row.machineDescType, row.typeName))}</td>
              <td>{formatValue(firstMeaningful(row.configModel, row.model, row.specification))}</td>
              <td>{formatValue(firstMeaningful(row.pastYearNum, row.historyNum, row.lastYearNum))}</td>
              <td>{formatValue(firstMeaningful(row.pastYearCost, row.historyCost, row.lastYearCost))}</td>
              <td>{formatValue(firstMeaningful(row.pastYearTotal, row.subtotal, row.totalCost))}</td>
              <td>{formatValue(firstMeaningful(row.budgetYearNum, row.currentYearNum, row.thisYearNum))}</td>
              <td>{formatValue(firstMeaningful(row.budgetYearCost, row.currentYearCost, row.thisYearCost))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function looksLikeMachineScopeRows(rows) {
  return normalizeList(rows).some((row) => {
    if (!row || typeof row !== "object") {
      return false;
    }
    return [
      row.machineName,
      row.demandType,
      row.configModel,
      row.machineDescType,
      row.pastYearNum,
      row.budgetYearNum,
      row.currentYearNum,
      row.thisYearNum,
    ].some((value) => String(value || "").trim());
  });
}

function UploadSection({ section, emptyText = "暂无内容" }) {
  if (!hasUploadSectionContent(section)) {
    return <p className="viewer-empty">{emptyText}</p>;
  }
  const images = normalizeList(section?.images).map(imageUrlOf).filter(Boolean);
  const items = normalizeList(section?.items);
  return (
    <div className="acceptance-architecture-grid">
      {section?.title ? <h3>{section.title}</h3> : null}
      {section?.content ? <p>{section.content}</p> : null}
      {items.length ? (
        <div className="stack-sm">
          {items.map((item, index) => (
            <article key={`${item.title || "item"}-${index}`} className="card viewer-card-soft">
              <h4>{item.title || `内容 ${index + 1}`}</h4>
              {item.content ? <p>{item.content}</p> : null}
            </article>
          ))}
        </div>
      ) : null}
      {images.length ? (
        <div className="viewer-image-grid">
          {images.map((image) => (
            <a key={image} href={image} target="_blank" rel="noreferrer">
              <img src={image} alt="upload" className="viewer-inline-image" />
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function normalizeDepartmentValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean).join("、") || "-";
  }
  if (typeof value === "string") {
    const source = value.trim();
    if (!source) {
      return "-";
    }
    if (source.startsWith("[")) {
      try {
        const parsed = JSON.parse(source);
        return normalizeDepartmentValue(parsed);
      } catch {
        return source;
      }
    }
    return source;
  }
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function projectValueGroupLabel(groupKey) {
  if (groupKey === "result") {
    return "结果（财务/客户）模型";
  }
  if (groupKey === "management") {
    return "管理体系模型";
  }
  return "能力（竞争力）模型";
}

function buildTamModelEntries(documentPayload) {
  const tamModels = documentPayload?.tam_models || {};
  const groups = {
    capability: [],
    result: [],
    management: [],
  };

  const pushEntry = (groupKey, item, index) => {
    groups[groupKey].push({
      id: item?.projectValueId || item?.id || `${groupKey}-${index}`,
      groupKey,
      title: item?.title || item?.name || "-",
      currentState: item?.currentStatus || item?.current_state || item?.currentState || item?.status || "-",
      benefitDepartment: normalizeDepartmentValue(item?.deptId || item?.benefitDepartment || item?.benefit_department),
      year2026: item?.target_2026 || item?.oneValue || item?.valueGoal || item?.target_3y?.["2026"] || "-",
      year2027: item?.target_2027 || item?.twoValue || item?.twoYearValue || item?.target_3y?.["2027"] || "-",
      year2028: item?.target_2028 || item?.threeValue || item?.threeYearValue || item?.target_3y?.["2028"] || "-",
      calculationBasis: item?.content || item?.calculationBasis || item?.calculation_basis || "-",
    });
  };

  [
    { key: "capability", items: normalizeList(tamModels.capability) },
    { key: "result", items: normalizeList(tamModels.result) },
    { key: "management", items: normalizeList(tamModels.management) },
  ].forEach((group) => {
    group.items.forEach((item, index) => pushEntry(group.key, item, index));
  });

  if (!groups.capability.length && !groups.result.length && !groups.management.length) {
    const remoteTamData = documentPayload?.remote_snapshot?.endpoints?.tam_info?.data || {};
    ["1", "2", "3"].forEach((key) => {
      const groupKey = key === "2" ? "result" : key === "3" ? "management" : "capability";
      const rows = normalizeList(remoteTamData?.[key]?.projectValueInfoList || remoteTamData?.[key]?.valueInfoList);
      rows.forEach((item, index) => pushEntry(groupKey, item, index));
    });
  }

  return groups;
}

function TamModelBoard({ documentPayload, activeTab }) {
  const groups = buildTamModelEntries(documentPayload);
  const key = activeTab === "result" || activeTab === "management" ? activeTab : "capability";
  const entries = groups[key] || [];

  if (!entries.length) {
    return <p className="viewer-empty">暂无TAM模型数据</p>;
  }

  return (
    <div className="viewer-value-list">
      <div className="viewer-tam-tipbar">
        <span className="viewer-tam-tip">TAM模型指标至少填报一项</span>
        <span className={`viewer-tam-toggle ${entries.length ? "active" : ""}`}>涉及该模型</span>
      </div>
      {entries.map((entry) => (
        <article key={entry.id} className="viewer-value-card">
          <div className="viewer-value-section-title">{projectValueGroupLabel(entry.groupKey)}</div>
          <div className="viewer-value-grid viewer-value-grid-3">
            <label className="viewer-value-field">
              <span>指标标题</span>
              <div className="viewer-value-box">{entry.title}</div>
            </label>
            <label className="viewer-value-field">
              <span>现状</span>
              <div className="viewer-value-box">{entry.currentState}</div>
            </label>
            <label className="viewer-value-field">
              <span>受益部门</span>
              <div className="viewer-value-box">{entry.benefitDepartment}</div>
            </label>
          </div>
          <div className="viewer-value-grid viewer-value-grid-3">
            <label className="viewer-value-field">
              <span>2026年目标</span>
              <div className="viewer-value-box">{entry.year2026}</div>
            </label>
            <label className="viewer-value-field">
              <span>2027年目标</span>
              <div className="viewer-value-box">{entry.year2027}</div>
            </label>
            <label className="viewer-value-field">
              <span>2028年目标</span>
              <div className="viewer-value-box">{entry.year2028}</div>
            </label>
          </div>
          <label className="viewer-value-field">
            <span>测算依据</span>
            <div className="viewer-value-box viewer-value-box-large">{entry.calculationBasis}</div>
          </label>
        </article>
      ))}
    </div>
  );
}

function normalizeProjectReviewBlocks(section) {
  if (!section || typeof section !== "object") {
    return [];
  }
  const items = normalizeList(section.items)
    .filter((item) => item && typeof item === "object")
    .map((item, index) => ({
      id: item.id || item.order || `review-block-${index + 1}`,
      title: firstMeaningful(item.title, section.title),
      content: firstMeaningful(item.content, section.content),
      images: normalizeList(item.images).length ? normalizeList(item.images) : normalizeList(section.images),
    }));
  if (items.length) {
    return items;
  }
  if (!hasUploadSectionContent(section)) {
    return [];
  }
  return [
    {
      id: "review-block-1",
      title: firstMeaningful(section.title),
      content: firstMeaningful(section.content),
      images: normalizeList(section.images),
    },
  ];
}

function buildProjectReviewGoalGroups(documentPayload) {
  const okr = documentPayload?.okr || {};
  const rows = normalizeList(documentPayload?.scope?.content_list).length
    ? normalizeList(documentPayload?.scope?.content_list)
    : normalizeList(documentPayload?.scope?.business_processes);
  const groups = new Map();

  rows.forEach((row, index) => {
    const key = String(firstMeaningful(row?.goalId, row?.productId, row?.productName, `goal-${index + 1}`));
    if (!groups.has(key)) {
      groups.set(key, {
        id: key,
        rows: [],
        productNames: new Set(),
      });
    }
    const group = groups.get(key);
    group.rows.push(row);
    const productName = firstMeaningful(row?.productName, row?.productFullName, row?.productLabel);
    if (productName) {
      group.productNames.add(productName);
    }
  });

  if (!groups.size) {
    groups.set("project-review-default", {
      id: "project-review-default",
      rows: [],
      productNames: new Set(normalizeList(okr.related_products).map((item) => firstMeaningful(item?.productName, item?.name)).filter(Boolean)),
    });
  }

  return Array.from(groups.values()).map((group, index) => ({
    id: group.id,
    buttonLabel: `项目目标${index + 1}`,
    statusLabel: "已填写",
    rows: group.rows,
    productNames: Array.from(group.productNames),
    processCount: group.rows.length,
    businessUnitCount: group.rows.reduce((sum, row) => sum + normalizeNumber(firstMeaningful(row?.busNum, row?.businessUnitCount)), 0),
    businessRoleCount: group.rows.reduce((sum, row) => sum + normalizeNumber(firstMeaningful(row?.busObjNum, row?.businessObjectCount)), 0),
  }));
}

function buildProjectReviewSystemScopeGroups(documentPayload) {
  const rows = [
    ...normalizeList(documentPayload?.scope?.microservices),
    ...normalizeList(documentPayload?.scope?.microapps),
  ];
  const groups = new Map();
  const seen = new Set();

  rows.forEach((row, index) => {
    const itemKey = String(firstMeaningful(row?.id, row?.subCode, row?.code, `system-item-${index + 1}`));
    if (seen.has(itemKey)) {
      return;
    }
    seen.add(itemKey);
    const key = String(firstMeaningful(row?.systemCode, row?.systemId, row?.systemName, `system-${index + 1}`));
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        name: firstMeaningful(row?.systemName, row?.applicationSystemName, row?.name, `系统${groups.size + 1}`),
        items: [],
      });
    }
    groups.get(key).items.push({
      id: itemKey,
      code: firstMeaningful(row?.subCode, row?.code, row?.systemCode),
      name: firstMeaningful(row?.subName, row?.name, row?.applicationSystemName),
      type: firstMeaningful(row?.subType, row?.type, row?.categoryName, "微应用"),
      owner: firstMeaningful(row?.subLeader, row?.ownerName, row?.subLeaderAccount),
    });
  });

  return Array.from(groups.values());
}

function buildArchitectureReviewTags(group) {
  const summary = group?.summary || {};
  if (group?.key === "business") {
    return [
      summary.product_count ? `产品数 ${summary.product_count}` : "",
      summary.business_process_count ? `业务流程数 ${summary.business_process_count}` : "",
      summary.business_unit_count ? `业务单元数 ${summary.business_unit_count}` : "",
      summary.business_object_count ? `业务对象数 ${summary.business_object_count}` : "",
    ].filter(Boolean);
  }
  if (group?.key === "data") {
    return [
      summary.flow_dimension_count ? `维度数 ${summary.flow_dimension_count}` : "",
      summary.check_point_count ? `检查点 ${summary.check_point_count}` : "",
    ].filter(Boolean);
  }
  return [
    summary.app_count ? `应用数 ${summary.app_count}` : "",
    summary.service_count ? `服务数 ${summary.service_count}` : "",
    summary.safety_level ? `安全等级 ${summary.safety_level}` : "",
  ].filter(Boolean);
}

function buildArchitecturePreviewItems(group) {
  const items = normalizeList(group?.items);
  if (items.length) {
    return items.map((item) => firstMeaningful(item?.checkpoint, item?.dimension, item?.value_model, item?.description, "-"));
  }
  return [];
}

function buildAcceptanceArchitectureStatusCards(groups) {
  const groupMap = new Map(normalizeList(groups).map((group) => [String(group?.key || "").trim(), group]));
  const cards = [
    { key: "business", title: "业务架构评审状态", links: ["前往EAMAP查看"] },
    { key: "technology", title: "技术架构评审状态", links: ["前往云原生查看"] },
    { key: "security", title: "安全架构评审状态", links: [] },
    { key: "data", title: "数据架构评审状态", links: ["查看评审详情", "前往信息架构中心查看"] },
  ];
  return cards.map((card) => {
    const group = groupMap.get(card.key) || {};
    return {
      ...card,
      items: normalizeList(group?.items).map((item, index) => ({
        id: item?.id || `${card.key}-${index + 1}`,
        title: acceptanceReviewItemTitle(item),
      })),
    };
  });
}

function splitAcceptanceNamedItems(value) {
  return String(value || "")
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildAcceptanceArchitectureCards(groups) {
  const groupMap = new Map(normalizeList(groups).map((group) => [String(group?.key || "").trim(), group]));
  const cards = [
    { key: "business", title: "业务架构评审状态", links: ["前往EAMAP查看"] },
    { key: "technology", title: "技术架构评审状态", links: ["前往云原生查看"] },
    { key: "security", title: "安全架构评审状态", links: [] },
    { key: "data", title: "数据架构评审状态", links: ["查看评审详情", "前往信息架构中心查看"] },
  ];
  return cards.map((card) => {
    const group = groupMap.get(card.key) || {};
    return {
      ...card,
      items: normalizeList(group?.items).map((item, index) => ({
        id: item?.id || `${card.key}-${index + 1}`,
        title: acceptanceReviewItemTitle(item),
      })),
    };
  });
}

function buildAcceptanceDeliverableStats(documentPayload, deliverableSummary) {
  const milestoneRows = normalizeList(documentPayload?.remote_snapshot?.endpoints?.milestones?.data);
  const standardRow = milestoneRows.reduce((current, item) => {
    const currentCount = splitAcceptanceNamedItems(current?.deliverablesName).length;
    const nextCount = splitAcceptanceNamedItems(item?.deliverablesName).length;
    return nextCount > currentCount ? item : current;
  }, {});
  const standardTotal = splitAcceptanceNamedItems(standardRow?.deliverablesName).length;
  const taskTotal = Number(firstMeaningful(deliverableSummary?.taskTargetNumNew, deliverableSummary?.taskTargetNum, 0)) || 0;
  const taskUploaded = Number(firstMeaningful(deliverableSummary?.taskFactNumNew, deliverableSummary?.taskFactNum, 0)) || 0;
  const taskRate = Number(firstMeaningful(deliverableSummary?.taskUploadRate, taskTotal ? (taskUploaded / taskTotal) * 100 : 0)) || 0;
  const standardRate = Number(firstMeaningful(deliverableSummary?.contractUploadRate, standardTotal ? 100 : 0)) || 0;
  const standardUploaded = standardTotal ? Math.min(standardTotal, Math.round((standardRate / 100) * standardTotal)) : 0;
  return {
    task: { label: "任务单交付物", rate: Math.max(0, Math.min(100, taskRate)), uploaded: taskUploaded, total: taskTotal },
    standard: { label: "标准交付物", rate: Math.max(0, Math.min(100, standardRate)), uploaded: standardUploaded, total: standardTotal },
  };
}

function normalizeAcceptanceDeliverableFiles(value) {
  return normalizeList(value)
    .map((item, index) => {
      const fileId = firstMeaningful(item?.id, item?.fileId, item?.attachmentId, item?.uid, `deliverable-file-${index + 1}`);
      const fileName = firstMeaningful(item?.name, item?.fileName, item?.attachmentName, item?.title, `交付物${index + 1}`);
      if (!fileId && !fileName) {
        return null;
      }
      return {
        id: String(fileId || `deliverable-file-${index + 1}`),
        name: fileName,
        url: fileId ? imageUrlOf(fileId) : "",
      };
    })
    .filter(Boolean);
}

function buildAcceptanceStandardDeliverableRows(acceptance) {
  return normalizeList(acceptance?.standard_deliverables?.rows).map((item, index) => ({
    id: item?.id || `standard-deliverable-${index + 1}`,
    index: Number(firstMeaningful(item?.index, index + 1)) || index + 1,
    delivery_field: firstMeaningful(item?.delivery_field, item?.deliveryField, item?.phaseName),
    delivery_type: firstMeaningful(item?.delivery_type, item?.attachment_name, item?.attachmentName, item?.deliverTypeName),
    template_name: firstMeaningful(item?.template_name, item?.deliverName, item?.templateName),
    template_id: firstMeaningful(item?.template_id, item?.attachmentSrc, item?.templateId),
    files: normalizeAcceptanceDeliverableFiles(item?.files),
  }));
}

function pickAcceptanceTaskFallbackDeliverable(standardRows) {
  return (
    standardRows.find((item) => /试运|运行报告/.test(String(item?.delivery_type || "")) && normalizeList(item?.files).length)
    || standardRows.find((item) => normalizeList(item?.files).length)
    || null
  );
}

function buildAcceptanceTaskDeliverableGroups(taskRow, taskOrderView, documentPayload, deliverableRow, taskDeliverablesPayload, standardRows) {
  const rawGroups = normalizeList(taskDeliverablesPayload?.groups);
  const normalizedGroups = rawGroups.map((group, groupIndex) => {
    const taskRows = normalizeList(
      group?.child
      || group?.rows
      || group?.tasks
      || group?.taskList
      || group?.dataList
      || group?.list,
    ).map((item, rowIndex) => ({
      id: item?.id || `task-deliverable-row-${groupIndex + 1}-${rowIndex + 1}`,
      task_name: firstMeaningful(item?.task_name, item?.taskName, item?.name),
      task_category: firstMeaningful(item?.task_category, item?.taskGroup, item?.taskTypeName, item?.taskType, item?.typeName),
      deliverable_type: firstMeaningful(item?.deliverable_type, item?.paramName, item?.deliveryTypeName, item?.attachmentName, item?.deliverTypeName),
      template_name: firstMeaningful(item?.template_name, item?.templateName, item?.deliverName),
      template_id: firstMeaningful(item?.template_id, item?.templateId, item?.attachmentSrc),
      uploads: normalizeAcceptanceDeliverableFiles(
        item?.files
        || item?.deliverAttachmentFile
        || item?.attachments
        || (item?.deliverFileId || item?.deliverName
          ? [{ id: item?.deliverFileId, name: item?.deliverName }]
          : []),
      ),
    })).filter((item) => item.task_name || item.task_category || item.deliverable_type || normalizeList(item.uploads).length);
    if (!taskRows.length) {
      return null;
    }
    return {
      id: group?.id || `task-deliverable-group-${groupIndex + 1}`,
      title: firstMeaningful(group?.title, group?.flowName, group?.process_name, group?.processName, group?.businessFlow, `流程${groupIndex + 1}基本信息`),
      process_code: firstMeaningful(group?.process_code, group?.processCoding, group?.processCode, group?.processId, group?.businessUnitCode),
      process_level: firstMeaningful(group?.process_level, group?.processLevel, group?.level, group?.level_name),
      develop_category: firstMeaningful(group?.develop_category, group?.type, group?.developCategory, group?.taskTypeName, group?.taskType),
      rows: taskRows,
    };
  }).filter(Boolean);
  if (normalizedGroups.length) {
    return normalizedGroups;
  }

  if (!taskRow) {
    return [];
  }

  const processRows = buildAcceptanceDetailProcessRows(taskRow, taskOrderView, documentPayload, deliverableRow);
  const fallbackDeliverable = pickAcceptanceTaskFallbackDeliverable(standardRows);
  const fallbackUploads = normalizeList(fallbackDeliverable?.files);
  const fallbackDeliverableType = String(firstMeaningful(fallbackDeliverable?.delivery_type, "运行报告"))
    .replace(/^系统试运营报告$/, "运行报告")
    .replace(/^系统试运行报告$/, "运行报告");
  const taskName = firstMeaningful(taskRow?.taskName, taskRow?.name, taskOrderView?.task_name, "实施任务");
  const taskCategory = firstMeaningful(taskRow?.taskTypeName, taskRow?.taskType, "功能上线");

  return processRows.map((item, index) => ({
    id: item?.id || `task-deliverable-group-fallback-${index + 1}`,
    title: `${firstMeaningful(item?.process_name, `流程${index + 1}`)}基本信息`,
    process_code: item?.process_code,
    process_level: item?.process_level,
    develop_category: item?.develop_category,
    rows: [
      {
        id: `task-deliverable-row-fallback-${index + 1}`,
        task_name: taskName,
        task_category: taskCategory,
        deliverable_type: fallbackDeliverableType,
        template_name: fallbackDeliverable?.template_name,
        template_id: fallbackDeliverable?.template_id,
        uploads: fallbackUploads,
      },
    ],
  }));
}

function acceptanceReviewGroupMeta(group) {
  const titleByKey = {
    business: "业务架构评审",
    data: "数据架构评审",
    technology: "技术架构评审",
    security: "安全架构评审",
  };
  return titleByKey[group?.key] || group?.title || "专业技术领域评审";
}

function acceptanceReviewItemTitle(item) {
  return firstMeaningful(item?.checkpoint, item?.value_model, item?.description, item?.dimension, item?.title, "未命名评审项");
}

function AcceptanceArchitectureReviewPanel({ groups }) {
  const normalizedGroups = buildAcceptanceArchitectureCards(groups);
  if (!normalizedGroups.length) {
    return <p className="viewer-empty">暂无专业技术领域评审数据</p>;
  }
  return (
    <div className="stack-md">
      {normalizedGroups.map((group) => {
        const items = normalizeList(group?.items);
        const title = `${acceptanceReviewGroupMeta(group)}状态`;
        return (
          <article key={group?.key || group?.title || title} className="card acceptance-review-card">
            <div className="acceptance-review-head">
              <h3>{title}</h3>
              <span className={`acceptance-review-badge ${group?.ok ? "done" : ""}`}>{group?.ok ? "已填写" : "待补充"}</span>
            </div>
            <div className="acceptance-review-list">
              {items.map((item, index) => {
                const description = firstMeaningful(item?.description, item?.value_model, item?.conclusion);
                return (
                  <article key={item?.id || `${group?.key || "group"}-${index}`} className="acceptance-review-item">
                    <span className="acceptance-review-index">{index + 1}</span>
                    <div className="acceptance-review-body">
                      <p className="acceptance-review-title">{acceptanceReviewItemTitle(item)}</p>
                      {description && description !== acceptanceReviewItemTitle(item) ? (
                        <p className="acceptance-review-description">{description}</p>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function AcceptanceArchitectureStatusBoard({ groups }) {
  const cards = buildAcceptanceArchitectureStatusCards(groups);
  return (
    <div className="acceptance-architecture-grid">
      {cards.map((card) => {
        const items = normalizeList(card.items);
        return (
          <article key={card.key} className="card acceptance-review-card acceptance-architecture-card">
            <div className="acceptance-review-head">
              <h3>{card.title}</h3>
              <div className="acceptance-architecture-links">
                {card.links.map((link) => (
                  <span key={link} className="acceptance-architecture-link">{link}</span>
                ))}
              </div>
            </div>
            <div className="acceptance-review-list">
              {items.length ? items.map((item, index) => (
                <article key={item?.id || `${card.key}-${index + 1}`} className="acceptance-review-item acceptance-architecture-item">
                  <span className="acceptance-review-index">{index + 1}</span>
                  <div className="acceptance-review-body">
                    <p className="acceptance-review-title">{item.title}</p>
                  </div>
                </article>
              )) : (
                <div className="acceptance-architecture-empty">暂无评审项</div>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function AcceptanceArchitectureStatusPanel({ groups }) {
  const cards = buildAcceptanceArchitectureCards(groups);
  return (
    <div className="acceptance-architecture-grid">
      {cards.map((card) => {
        const items = normalizeList(card.items);
        return (
          <article key={card.key} className="card acceptance-review-card acceptance-architecture-card">
            <div className="acceptance-review-head">
              <h3>{card.title}</h3>
              <div className="acceptance-architecture-links">
                {card.links.map((link) => (
                  <span key={link} className="acceptance-architecture-link">{link}</span>
                ))}
              </div>
            </div>
            <div className="acceptance-review-list">
              {items.length ? items.map((item, index) => (
                <article key={item?.id || `${card.key}-${index + 1}`} className="acceptance-review-item acceptance-architecture-item">
                  <span className="acceptance-review-index">{index + 1}</span>
                  <div className="acceptance-review-body">
                    <p className="acceptance-review-title">{item.title}</p>
                  </div>
                </article>
              )) : (
                <div className="acceptance-architecture-empty">暂无评审项</div>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function AcceptanceDeliverablesBoard({ currentAcceptance, summary, stats, onOpenStandard, onOpenTask }) {
  const isFinalAcceptance = Number(firstMeaningful(currentAcceptance?.isFinalAccept, summary?.isFinalAcceptLast, 0)) === 1;
  const stageLabel = isFinalAcceptance ? "终验收(本次验收)" : "阶段验收(本次验收)";
  return (
    <section className="acceptance-deliverables-card">
      <div className="acceptance-deliverables-tab-row">
        <button type="button" className="acceptance-deliverables-tab active">
          {stageLabel}
        </button>
        <span className="acceptance-deliverables-mode">交付物/履约模型</span>
      </div>
      <div className="acceptance-deliverables-layout">
        <div className="acceptance-deliverables-upload-box">
          <div className="acceptance-deliverables-upload-icon" aria-hidden="true">↑</div>
          <p className="acceptance-deliverables-upload-hint">支持文件格式: word、pdf、ppt、excel</p>
          <button type="button" className="acceptance-deliverables-upload-button" onClick={onOpenStandard}>查看备证</button>
        </div>
        <div className="acceptance-deliverables-stats">
          {[stats.task, stats.standard].map((item) => (
            <button
              key={item.label}
              type="button"
              className="acceptance-deliverables-stat-card acceptance-deliverables-stat-button"
              onClick={item.label === "任务单交付物" ? onOpenTask : onOpenStandard}
            >
              <div className="acceptance-deliverables-stat-head">
                <span>{item.label}</span>
              </div>
              <div className="acceptance-deliverables-progress-row">
                <div className="acceptance-deliverables-progress-track">
                  <div className="acceptance-deliverables-progress-fill" style={{ width: `${item.rate}%` }} />
                </div>
                <div className="acceptance-deliverables-progress-meta">
                  <span>{`已上传${formatPercent(item.rate)}`}</span>
                  <strong>{`${item.uploaded}/${item.total || 0}`}</strong>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function AcceptanceDeliverablesDialog({
  open,
  activeTab,
  onClose,
  onTabChange,
  currentAcceptance,
  summary,
  standardRows,
  standardSummary,
  taskGroups,
}) {
  if (!open) {
    return null;
  }

  const isFinalAcceptance = Number(firstMeaningful(currentAcceptance?.isFinalAccept, summary?.isFinalAcceptLast, 0)) === 1;
  const stageLabel = isFinalAcceptance ? "终验收(本次验收)" : "阶段验收(本次验收)";
  const businessType = firstMeaningful(summary?.project_type_name, summary?.project_category_name);
  const businessSubcategory = firstMeaningful(summary?.business_subcategory_name, summary?.project_type_name);
  const standardTotal = Number(firstMeaningful(standardSummary?.total, standardRows.length, 0)) || 0;

  return (
    <div className="viewer-modal acceptance-deliverables-modal" role="dialog" aria-modal="true" aria-label="上传交付物">
      <button type="button" className="viewer-modal-backdrop" aria-label="关闭上传交付物弹窗" onClick={onClose} />
      <div className="viewer-modal-dialog acceptance-deliverables-dialog">
        <div className="viewer-modal-head acceptance-deliverables-dialog-head">
          <div>
            <h3>上传交付物</h3>
          </div>
          <button type="button" className="acceptance-deliverables-dialog-close" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="viewer-modal-body acceptance-deliverables-dialog-body">
          <div className="acceptance-deliverables-stage-pill">{stageLabel}</div>
          <div className="acceptance-deliverables-dialog-tabs">
            <button
              type="button"
              className={`acceptance-deliverables-dialog-tab ${activeTab === "standard" ? "active" : ""}`}
              onClick={() => onTabChange("standard")}
            >
              标准交付物
            </button>
            <button
              type="button"
              className={`acceptance-deliverables-dialog-tab ${activeTab === "task" ? "active" : ""}`}
              onClick={() => onTabChange("task")}
            >
              任务单交付物
            </button>
          </div>

          {activeTab === "standard" ? (
            <div className="stack-md">
              <section className="acceptance-deliverables-panel">
                <div className="acceptance-deliverables-section-title">基本信息</div>
                <div className="acceptance-deliverables-basic-grid">
                  <div>
                    <span>业务类型</span>
                    <strong>{formatValue(businessType)}</strong>
                  </div>
                  <div>
                    <span>业务子类</span>
                    <strong>{formatValue(businessSubcategory)}</strong>
                  </div>
                  <div>
                    <span>交付物类型数量</span>
                    <strong>{formatValue(standardTotal)}</strong>
                  </div>
                </div>
              </section>
              <section className="acceptance-deliverables-panel">
                <div className="acceptance-deliverables-section-title">标准交付物</div>
                {standardRows.length ? (
                  <table className="acceptance-deliverables-table">
                    <thead>
                      <tr>
                        <th>序号</th>
                        <th>交付领域</th>
                        <th>交付物上传</th>
                        <th>交付物类型</th>
                        <th>模板</th>
                      </tr>
                    </thead>
                    <tbody>
                      {standardRows.map((item) => (
                        <tr key={item.id}>
                          <td>{item.index}</td>
                          <td>{formatValue(item.delivery_field)}</td>
                          <td>
                            <div className="acceptance-deliverable-upload-list">
                              <span className="acceptance-deliverable-upload-count">{`已有${normalizeList(item.files).length}个交付物。`}</span>
                              {normalizeList(item.files).map((file) => (
                                <a
                                  key={file.id}
                                  className="acceptance-deliverable-link"
                                  href={file.url || "#"}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {file.name}
                                </a>
                              ))}
                            </div>
                          </td>
                          <td>{formatValue(item.delivery_type)}</td>
                          <td>
                            {item.template_id ? (
                              <a className="acceptance-deliverable-link" href={imageUrlOf(item.template_id)} target="_blank" rel="noreferrer">
                                下载模版
                              </a>
                            ) : (
                              "-"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="viewer-empty">暂无标准交付物数据</p>
                )}
              </section>
            </div>
          ) : (
            <div className="stack-md">
              {taskGroups.length ? taskGroups.map((group) => (
                <section key={group.id} className="acceptance-deliverables-panel">
                  <div className="acceptance-deliverables-section-title">{formatValue(group.title)}</div>
                  <div className="acceptance-deliverables-basic-grid">
                    <div>
                      <span>流程编号</span>
                      <strong>{formatValue(group.process_code)}</strong>
                    </div>
                    <div>
                      <span>流程级别</span>
                      <strong>{formatValue(group.process_level)}</strong>
                    </div>
                    <div>
                      <span>开发类别</span>
                      <strong>{formatValue(group.develop_category)}</strong>
                    </div>
                  </div>
                  <div className="acceptance-deliverables-subtitle">任务交付物</div>
                  <table className="acceptance-deliverables-table">
                    <thead>
                      <tr>
                        <th>序号</th>
                        <th>任务名称</th>
                        <th>任务类别</th>
                        <th>交付物上传</th>
                        <th>交付物类型</th>
                        <th>模板</th>
                      </tr>
                    </thead>
                    <tbody>
                      {normalizeList(group.rows).map((row, index) => (
                        <tr key={row.id}>
                          <td>{index + 1}</td>
                          <td>{formatValue(row.task_name)}</td>
                          <td>{formatValue(row.task_category)}</td>
                          <td>
                            <div className="acceptance-deliverable-upload-list">
                              <span className="acceptance-deliverable-upload-count">{`已有${normalizeList(row.uploads).length}个交付物。`}</span>
                              {normalizeList(row.uploads).map((file) => (
                                <a
                                  key={file.id}
                                  className="acceptance-deliverable-link"
                                  href={file.url || "#"}
                                  target="_blank"
                                  rel="noreferrer"
                                >
                                  {file.name}
                                </a>
                              ))}
                            </div>
                          </td>
                          <td>{formatValue(row.deliverable_type)}</td>
                          <td>
                            {row.template_id ? (
                              <a className="acceptance-deliverable-link" href={imageUrlOf(row.template_id)} target="_blank" rel="noreferrer">
                                下载模版
                              </a>
                            ) : (
                              "-"
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )) : (
                <p className="viewer-empty">暂无任务单交付物数据</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ArchitectureReviewPanel({ groups, scene = "initiation" }) {
  if (scene === "acceptance") {
    return <AcceptanceArchitectureStatusBoard groups={groups} />;
  }
  const normalizedGroups = normalizeList(groups);
  if (!normalizedGroups.length) {
    return <p className="viewer-empty">暂无专业领域评审数据</p>;
  }
  return (
    <div className="architecture-review-board">
      {normalizedGroups.map((group) => {
        const previewItems = buildArchitecturePreviewItems(group);
        const tags = buildArchitectureReviewTags(group);
        return (
          <article key={group.key || group.title} className="architecture-review-card">
            <div className="architecture-review-head">
              <div>
                <h3>{group.title || "专业领域评审"}</h3>
                <p className="category-meta">{group.ok ? "接口已返回结果" : group.message || "接口未返回有效结果"}</p>
              </div>
              <div className="architecture-review-tags">
                {tags.map((tag) => (
                  <span key={tag} className="architecture-review-tag">
                    {tag}
                  </span>
                ))}
              </div>
            </div>
            {group.link_label ? <div className="architecture-review-actions"><span className="viewer-linkish">{group.link_label}</span></div> : null}
            <div className="architecture-review-list">
              {previewItems.length ? (
                previewItems.map((item, index) => (
                  <div key={`${group.key || "review"}-${index}`} className="architecture-review-row">
                    <span className="architecture-review-index">{index + 1}</span>
                    <span>{item}</span>
                  </div>
                ))
              ) : (
                <div className="architecture-review-empty">{group.message || "当前分组暂无评审明细"}</div>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export {
  IMAGE_DOWNLOAD_PREFIX,
  INITIATION_SECTIONS,
  ACCEPTANCE_SECTIONS,
  TASK_ORDER_PHASE,
  TASK_ORDER_SECTIONS,
  ACCEPTANCE_SECTION_RULE_TABS,
  ACCEPTANCE_REVIEW_POINT_TO_TAB_KEY,
  ACCEPTANCE_TAM_POINT_TO_TAB_KEY,
  COMMON_REVIEW_TABS,
  ACCEPTANCE_PROJECT_REVIEW_TAB_KEYS,
  ACCEPTANCE_PROJECT_REVIEW_TABS,
  TAM_TABS,
  SECTION_TABS,
  ACCEPTANCE_ORDER_SECTIONS,
  definitionKey,
  filterDefinitionsByKeys,
  orderDefinitionsByKeys,
  normalizeList,
  formatValue,
  formatCurrency,
  formatCurrencyAllowZero,
  formatPercent,
  formatCompactDate,
  formatCurrencyWithUnit,
  approvalToneClass,
  formatApprovalItemStatus,
  detailStatusTone,
  normalizeApprovalDetailItems,
  firstMeaningful,
  imageUrlOf,
  hasUploadSectionContent,
  hasObjectContent,
  hasReviewTabContent,
  hasArchitectureReviewContent,
  sectionStatus,
  buildProjectBadges,
  acceptanceSectionTitle,
  matchesAcceptanceCategory,
  buildAcceptanceVisibility,
  normalizeNumber,
  toTextItems,
  countFilled,
  isTruthyFlag,
  acceptanceScopeTaskStatus,
  buildTaskOrderDrawerReasonOptions,
  buildTaskOrderDrawerWorkItems,
  buildTaskOrderDrawerCriteriaItems,
  buildTaskOrderDrawerEvaluationRows,
  buildTaskOrderDrawerStaffingMatrix,
  acceptanceMemberPartyLabel,
  buildAcceptanceDetailProcessRows,
  buildAcceptanceDetailMemberRows,
  buildTaskOrders,
  flattenTaskDetailObjects,
  flattenTaskSpecText,
  buildTaskOrderViewModel,
  resolveAcceptanceContractIdentity,
  contractPerformanceLabel,
  buildContractPartyRows,
  buildAcceptanceContractViewModel,
  taskOrderSectionStatus,
  pickColumns,
  DefinitionGrid,
  DataTable,
  machineScopeYearLabels,
  MachineScopeTable,
  looksLikeMachineScopeRows,
  UploadSection,
  normalizeDepartmentValue,
  projectValueGroupLabel,
  buildTamModelEntries,
  TamModelBoard,
  normalizeProjectReviewBlocks,
  buildProjectReviewGoalGroups,
  buildProjectReviewSystemScopeGroups,
  buildArchitectureReviewTags,
  buildArchitecturePreviewItems,
  buildAcceptanceArchitectureStatusCards,
  splitAcceptanceNamedItems,
  buildAcceptanceArchitectureCards,
  buildAcceptanceDeliverableStats,
  normalizeAcceptanceDeliverableFiles,
  buildAcceptanceStandardDeliverableRows,
  pickAcceptanceTaskFallbackDeliverable,
  buildAcceptanceTaskDeliverableGroups,
  acceptanceReviewGroupMeta,
  acceptanceReviewItemTitle,
  AcceptanceArchitectureReviewPanel,
  AcceptanceArchitectureStatusBoard,
  AcceptanceArchitectureStatusPanel,
  AcceptanceDeliverablesBoard,
  AcceptanceDeliverablesDialog,
  ArchitectureReviewPanel,
};
