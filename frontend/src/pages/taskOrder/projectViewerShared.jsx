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
  if (["background", "target", "solution", "panorama", "acceptance_plan"].includes(tabKey)) {
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
    return normalizeList(scope.business_processes).length || normalizeList(scope.content_list).length;
  }
  return false;
}

function sectionStatus(documentPayload, architecturePayload, scene, sectionKey) {
  const groups = normalizeList(architecturePayload?.groups || documentPayload?.architecture_review_details);
  const acceptance = documentPayload?.acceptance || {};
  const acceptanceInfoList = normalizeList(acceptance.info_list);
  const statusMap = {
    project_content: COMMON_REVIEW_TABS.some((tab) => hasReviewTabContent(documentPayload, tab.key)),
    project_review: COMMON_REVIEW_TABS.some((tab) => hasReviewTabContent(documentPayload, tab.key)),
    project_value: Boolean(String(documentPayload?.project_value || "").trim()),
    architecture_review: groups.some((group) => normalizeList(group?.items).length),
    tam_models: TAM_TABS.some((tab) => normalizeList(documentPayload?.tam_models?.[tab.key]).length),
    organization: normalizeList(documentPayload?.organization?.members).length || normalizeList(documentPayload?.organization?.teams).length,
    milestones: Object.values(documentPayload?.milestones || {}).some((value) => normalizeList(value).length || (value && typeof value === "object" && Object.keys(value).length)),
    budget: normalizeList(documentPayload?.budget?.cost_items).length || Boolean(documentPayload?.budget?.summary),
    cost_change: Boolean(String(documentPayload?.cost_change?.reason || "").trim()) || normalizeList(documentPayload?.cost_change?.history_items).length,
    acceptance_scope: normalizeList(acceptance.task_list).length || normalizeList(acceptance.contract_list).length,
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

function countFilled(values) {
  return values.filter((value) => {
    if (Array.isArray(value)) {
      return value.length > 0;
    }
    return String(value ?? "").trim() !== "";
  }).length;
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
  return normalizeList(value).filter((item) => item && typeof item === "object");
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
  const businessUnits = flattenTaskDetailObjects(taskOrderDetail?.business_units);
  const approvalNodes = flattenTaskDetailObjects(taskOrderDetail?.approval_nodes);
  const processRows = flattenTaskDetailObjects(taskOrderDetail?.process_rows);
  const matrixRows = flattenTaskDetailObjects(taskOrderDetail?.matrix_rows);
  const historyRows = flattenTaskDetailObjects(taskOrderDetail?.history_rows);
  const specRows = flattenTaskDetailObjects(taskOrderDetail?.spec_rows);
  const fallbackInfo = fallback?.basic_info || {};
  const fallbackStaffing = fallback?.staffing || {};
  const fallbackCost = fallback?.cost_estimation || {};
  const fallbackTech = fallback?.technical_requirements || {};

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
        name: firstMeaningful(item.name, item.userName, item.employeeName, item.memberName),
        post_name: firstMeaningful(item.post_name, item.postName, item.roleName, item.jobName, item.positionName),
        level_name: firstMeaningful(item.level_name, item.levelName, item.gradeName),
        expected_days: firstMeaningful(item.expected_days, item.expectedDays, item.planDays, item.taskCostDay, item.workDays, item.days),
        unit_price: firstMeaningful(item.unit_price, item.unitPrice, item.price, item.dayPrice, item.personDayPrice),
        estimated_cost: firstMeaningful(item.estimated_cost, item.estimatedCost, item.totalCost, item.cost, item.amount),
        department_name: firstMeaningful(item.department_name, item.departmentName, item.deptName),
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
    task_no: firstMeaningful(summary.taskOrderNo, summary.taskSerialCode, fallback?.task_no),
    task_name: firstMeaningful(summary.taskOrderName, summary.taskName, fallback?.task_name),
    supplier_name: firstMeaningful(summary.supplierName, fallback?.supplier_name),
    project_name: firstMeaningful(summary.projectName, fallback?.project_name),
    domain_name: firstMeaningful(summary.domainName, summary.belongTeamName, fallback?.domain_name),
    request_budget: firstMeaningful(summary.applyTotalBudget, summary.applyBudgetTotal, fallback?.request_budget),
    annual_budget: firstMeaningful(summary.applyYearBudget, summary.applyBudgetYear, fallback?.annual_budget),
    start_date: firstMeaningful(summary.startTime, summary.planStartTime, fallback?.start_date),
    end_date: firstMeaningful(summary.endTime, summary.planEndTime, fallback?.end_date),
    approved_at: firstMeaningful(summary.approvalPassTime, summary.taskAduitTime, fallback?.approved_at),
    project_ownership: {
      ...(fallback?.project_ownership || {}),
    },
    classification: {
      ...(fallback?.classification || {}),
    },
    budget_overview: {
      project_budget: firstMeaningful(summary.applyTotalBudget, summary.applyBudgetTotal, fallback?.budget_overview?.project_budget),
      project_year_budget: firstMeaningful(summary.applyYearBudget, summary.applyBudgetYear, fallback?.budget_overview?.project_year_budget),
      project_used_budget: firstMeaningful(summary.issueAmountNoTax, summary.issueAmountTax, fallback?.budget_overview?.project_used_budget),
      project_remaining_budget: fallback?.budget_overview?.project_remaining_budget,
    },
    basic_info: {
      ...fallbackInfo,
      task_name: firstMeaningful(summary.taskOrderName, summary.taskName, baseInfo.taskName, baseInfo.name, fallbackInfo.task_name),
      task_no: firstMeaningful(summary.taskOrderNo, summary.taskSerialCode, baseInfo.taskNo, baseInfo.taskCode, fallbackInfo.task_no),
      start_date: firstMeaningful(summary.startTime, summary.planStartTime, baseInfo.startTime, baseInfo.planStartTime, fallbackInfo.start_date),
      end_date: firstMeaningful(summary.endTime, summary.planEndTime, baseInfo.endTime, baseInfo.planEndTime, fallbackInfo.end_date),
      supplier_name: firstMeaningful(summary.supplierName, baseInfo.supplierName, fallbackInfo.supplier_name),
      contract_name: firstMeaningful(baseInfo.contractName, baseInfo.contractTitle, fallbackInfo.contract_name),
      contract_no: firstMeaningful(baseInfo.contractCode, baseInfo.contractNo, fallbackInfo.contract_no),
      target_list: normalizeList(baseInfo.targetListEstablishment || baseInfo.targetList || fallbackInfo.target_list),
      related_products: normalizeList(baseInfo.checkSupplierReason || baseInfo.productList || fallbackInfo.related_products),
      supplier_reason: firstMeaningful(baseInfo.supplierReason, fallbackInfo.supplier_reason),
      procurement_note: firstMeaningful(baseInfo.procurementNote, baseInfo.purchaseRemark, fallbackInfo.procurement_note),
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

function UploadSection({ section, emptyText = "暂无内容" }) {
  if (!hasUploadSectionContent(section)) {
    return <p className="viewer-empty">{emptyText}</p>;
  }
  const images = normalizeList(section?.images).map(imageUrlOf).filter(Boolean);
  const items = normalizeList(section?.items);
  return (
    <div className="stack-md">
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
  const normalizedGroups = normalizeList(groups).filter((group) => normalizeList(group?.items).length);
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

function ArchitectureReviewPanel({ groups, scene = "initiation" }) {
  if (scene === "acceptance") {
    return <AcceptanceArchitectureReviewPanel groups={groups} />;
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
  TAM_TABS,
  SECTION_TABS,
  ACCEPTANCE_ORDER_SECTIONS,
  normalizeList,
  formatValue,
  formatCurrency,
  formatPercent,
  approvalToneClass,
  firstMeaningful,
  imageUrlOf,
  hasUploadSectionContent,
  hasObjectContent,
  hasReviewTabContent,
  sectionStatus,
  buildProjectBadges,
  acceptanceSectionTitle,
  matchesAcceptanceCategory,
  buildAcceptanceVisibility,
  normalizeNumber,
  countFilled,
  buildTaskOrders,
  flattenTaskDetailObjects,
  flattenTaskSpecText,
  buildTaskOrderViewModel,
  taskOrderSectionStatus,
  pickColumns,
  DefinitionGrid,
  DataTable,
  machineScopeYearLabels,
  MachineScopeTable,
  UploadSection,
  normalizeDepartmentValue,
  projectValueGroupLabel,
  buildTamModelEntries,
  TamModelBoard,
  buildArchitectureReviewTags,
  buildArchitecturePreviewItems,
  acceptanceReviewGroupMeta,
  acceptanceReviewItemTitle,
  AcceptanceArchitectureReviewPanel,
  ArchitectureReviewPanel,
};
