import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import PageLayout from "../components/PageLayout";
import { requestJson } from "../api";

const IMAGE_DOWNLOAD_PREFIX = "https://prod-itpm.faw.cn/itpmNew/gateway/sop-itpm-service/files/download/";

const sectionDefinitions = [
  { key: "project_content", label: "项目内容" },
  { key: "project_value", label: "项目价值" },
  { key: "milestones", label: "项目里程碑" },
  { key: "budget", label: "预算信息" },
  { key: "cost_change", label: "费用变化点" },
];

const tabDefinitions = {
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

const changeProjectSectionDefinitions = [
  { key: "project_content", label: "项目内容" },
  { key: "architecture_review", label: "专业技术领域评审" },
  { key: "tam_models", label: "TAM模型" },
  { key: "organization", label: "组织架构" },
  { key: "milestones", label: "项目里程碑" },
  { key: "budget", label: "预算信息" },
];

const changeProjectTabDefinitions = {
  project_content: tabDefinitions.project_content,
  architecture_review: [],
  tam_models: [],
  organization: [],
  milestones: tabDefinitions.milestones,
  budget: tabDefinitions.budget,
};

const systemProjectSectionDefinitions = [
  { key: "project_content", label: "项目内容" },
  { key: "architecture_review", label: "专业技术领域评审" },
  { key: "tam_models", label: "TAM模型" },
  { key: "organization", label: "组织架构" },
  { key: "milestones", label: "项目里程碑" },
  { key: "budget", label: "预算信息" },
];

const systemProjectTabDefinitions = {
  project_content: [
    { key: "background", label: "项目背景" },
    { key: "okr", label: "项目OKR" },
    { key: "scope", label: "项目范围" },
    { key: "system_scope", label: "系统范围" },
    { key: "solution", label: "项目方案" },
  ],
  architecture_review: [],
  tam_models: [
    { key: "capability", label: "能力（竞争力）模型" },
    { key: "result", label: "结果（财务/客户）模型" },
    { key: "management", label: "管理体系模型" },
  ],
  organization: [],
  milestones: tabDefinitions.milestones,
  budget: tabDefinitions.budget,
};

const EXCEL_PROJECT_CONTENT_TABS_STANDARD = [
  { key: "background", label: "项目背景" },
  { key: "target", label: "项目目标" },
  { key: "scope", label: "项目范围" },
  { key: "solution", label: "项目方案" },
  { key: "panorama", label: "业务全景图" },
  { key: "annual_model", label: "年度管理模型" },
];

const EXCEL_PROJECT_CONTENT_TABS_SYSTEM = [
  { key: "background", label: "项目背景" },
  { key: "okr", label: "项目OKR" },
  { key: "scope", label: "项目范围" },
  { key: "system_scope", label: "系统范围" },
  { key: "solution", label: "项目方案" },
];

const EXCEL_LAYOUTS = {
  system_construction: {
    contentMode: "system",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "architecture_review", label: "专业技术领域评审" },
      { key: "tam_models", label: "TAM模型" },
      { key: "organization", label: "组织架构" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
    ],
    tabs: {
      project_content: EXCEL_PROJECT_CONTENT_TABS_SYSTEM,
      architecture_review: [],
      tam_models: [],
      organization: [],
      milestones: [],
      budget: [],
    },
  },
  operation_service: {
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "project_value", label: "项目价值" },
      { key: "organization", label: "组织架构" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
    tabs: {
      project_content: EXCEL_PROJECT_CONTENT_TABS_STANDARD,
      project_value: [],
      organization: [],
      milestones: [],
      budget: [],
      cost_change: [{ key: "reason", label: "费用变化点" }, { key: "history", label: "历史投入" }],
    },
  },
  technical_service: {
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "architecture_review", label: "专业技术领域评审" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
    tabs: {
      project_content: EXCEL_PROJECT_CONTENT_TABS_STANDARD,
      architecture_review: [],
      project_value: [],
      milestones: [],
      budget: [],
      cost_change: [{ key: "reason", label: "费用变化点" }, { key: "history", label: "历史投入" }],
    },
  },
  value_only: {
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
    tabs: {
      project_content: EXCEL_PROJECT_CONTENT_TABS_STANDARD,
      project_value: [],
      milestones: [],
      budget: [],
      cost_change: [{ key: "reason", label: "费用变化点" }, { key: "history", label: "历史投入" }],
    },
  },
  infrastructure_review: {
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "architecture_review", label: "专业技术领域评审" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
    tabs: {
      project_content: EXCEL_PROJECT_CONTENT_TABS_STANDARD,
      architecture_review: [],
      project_value: [],
      milestones: [],
      budget: [],
      cost_change: [{ key: "reason", label: "费用变化点" }, { key: "history", label: "历史投入" }],
    },
  },
  infrastructure_no_change: {
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
    ],
    tabs: {
      project_content: EXCEL_PROJECT_CONTENT_TABS_STANDARD,
      project_value: [],
      milestones: [],
      budget: [],
    },
  },
};

const EXCEL_SYSTEM_CONSTRUCTION_SUBCATEGORIES = new Set(["系统开发及实施", "系统产品购买", "产品运营"]);
const EXCEL_OPERATION_SERVICE_SUBCATEGORIES = new Set(["系统运维(一、二线)", "数据中心维护", "系统运维(三线)", "系统运维(产品维保)"]);
const EXCEL_TECHNICAL_SERVICE_SUBCATEGORIES = new Set(["基础服务", "数据服务", "安全服务", "保密服务"]);
const EXCEL_VALUE_ONLY_SUBCATEGORIES = new Set(["数据订阅及购买", "研发工具订阅许可升级", "研发工具许可购买", "非研发工具订阅许可升级", "非研发工具许可购买", "设备维修"]);
const EXCEL_INFRASTRUCTURE_REVIEW_SUBCATEGORIES = new Set(["设备购买及弱电布线", "资源租赁"]);
const EXCEL_INFRASTRUCTURE_NO_CHANGE_SUBCATEGORIES = new Set(["机房建设"]);

const LATEST_EXCEL_ARCHITECTURE_REVIEW_KEYS_ALL = ["business", "data", "security", "technology"];
const LATEST_EXCEL_ARCHITECTURE_REVIEW_KEYS_DATA_AND_SECURITY = ["data", "security"];
const LATEST_EXCEL_ARCHITECTURE_REVIEW_KEYS_SECURITY_ONLY = ["security"];

function createLatestExcelLayout({ contentMode, sections, architectureReviewKeys = [] }) {
  const projectContentTabs = contentMode === "system" ? EXCEL_PROJECT_CONTENT_TABS_SYSTEM : EXCEL_PROJECT_CONTENT_TABS_STANDARD;
  return {
    contentMode,
    sections,
    tabs: {
      project_content: projectContentTabs,
      project_value: [],
      architecture_review: [],
      tam_models: [],
      organization: [],
      milestones: [],
      budget: [],
      cost_change: [
        { key: "reason", label: "费用变化点" },
        { key: "history", label: "历史投入" },
      ],
    },
    architectureReviewKeys,
  };
}

const LATEST_EXCEL_LAYOUTS = {
  system_construction: createLatestExcelLayout({
    contentMode: "system",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "architecture_review", label: "专业技术领域评审" },
      { key: "tam_models", label: "TAM模型" },
      { key: "organization", label: "组织架构" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
    ],
    architectureReviewKeys: LATEST_EXCEL_ARCHITECTURE_REVIEW_KEYS_ALL,
  }),
  operation_service: createLatestExcelLayout({
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "project_value", label: "项目价值" },
      { key: "organization", label: "组织架构" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
  }),
  standard_with_change: createLatestExcelLayout({
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
  }),
  standard_without_change: createLatestExcelLayout({
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
    ],
  }),
  standard_security_review_with_change: createLatestExcelLayout({
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "architecture_review", label: "专业技术领域评审" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
    architectureReviewKeys: LATEST_EXCEL_ARCHITECTURE_REVIEW_KEYS_SECURITY_ONLY,
  }),
  standard_data_security_review_with_change: createLatestExcelLayout({
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "architecture_review", label: "专业技术领域评审" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
      { key: "cost_change", label: "费用变化点" },
    ],
    architectureReviewKeys: LATEST_EXCEL_ARCHITECTURE_REVIEW_KEYS_DATA_AND_SECURITY,
  }),
  standard_security_review_without_change: createLatestExcelLayout({
    contentMode: "standard",
    sections: [
      { key: "project_content", label: "项目内容" },
      { key: "architecture_review", label: "专业技术领域评审" },
      { key: "project_value", label: "项目价值" },
      { key: "milestones", label: "项目里程碑" },
      { key: "budget", label: "预算信息" },
    ],
    architectureReviewKeys: LATEST_EXCEL_ARCHITECTURE_REVIEW_KEYS_SECURITY_ONLY,
  }),
};

const LATEST_EXCEL_LAYOUT_BY_SUBCATEGORY = new Map([
  ["系统开发及实施", LATEST_EXCEL_LAYOUTS.system_construction],
  ["系统产品购买", LATEST_EXCEL_LAYOUTS.system_construction],
  ["产品运营", LATEST_EXCEL_LAYOUTS.system_construction],
  ["系统运维(一、二线)", LATEST_EXCEL_LAYOUTS.operation_service],
  ["数据中心维护", LATEST_EXCEL_LAYOUTS.operation_service],
  ["系统运维(三线)", LATEST_EXCEL_LAYOUTS.operation_service],
  ["系统运维(产品维保)", LATEST_EXCEL_LAYOUTS.operation_service],
  ["基础服务", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["数据服务", LATEST_EXCEL_LAYOUTS.standard_security_review_with_change],
  ["安全服务", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["保密服务", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["数据订阅及购买", LATEST_EXCEL_LAYOUTS.standard_data_security_review_with_change],
  ["研发工具订阅许可升级", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["研发工具许可购买", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["非研发工具订阅许可升级", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["非研发工具许可购买", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["设备维修", LATEST_EXCEL_LAYOUTS.standard_with_change],
  ["设备购买及弱电布线", LATEST_EXCEL_LAYOUTS.standard_security_review_without_change],
  ["机房建设", LATEST_EXCEL_LAYOUTS.standard_without_change],
  ["资源租赁", LATEST_EXCEL_LAYOUTS.standard_with_change],
]);

function normalizeLayoutKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[()（）_\-/]/g, "");
}

const NORMALIZED_LATEST_LAYOUT_BY_SUBCATEGORY = new Map(
  Array.from(LATEST_EXCEL_LAYOUT_BY_SUBCATEGORY.entries()).map(([name, layout]) => [normalizeLayoutKey(name), layout]),
);

const LAYOUT_ALIAS_TO_SUBCATEGORY = new Map([
  ["工作台开发及实施", "系统开发及实施"],
  ["系统研发及实施", "系统开发及实施"],
  ["系统开发与实施", "系统开发及实施"],
]);

function normalizeList(value) {
  if (Array.isArray(value)) {
    return value.filter((item) => item !== null && item !== undefined && item !== "");
  }
  if (value && typeof value === "object") {
    return Object.values(value).filter((item) => item !== null && item !== undefined && item !== "");
  }
  return [];
}

function buildImageUrl(rawValue) {
  const source = String(rawValue || "").trim();
  if (!source) {
    return "";
  }
  const normalized = /^https?:\/\//i.test(source) ? source : `${IMAGE_DOWNLOAD_PREFIX}${source.replace(/^\/+/, "")}`;
  return `/api/files/download?path=${encodeURIComponent(normalized)}`;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

function definitionPairs(items) {
  return (
    <dl className="viewer-detail-kv">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{formatValue(item.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function formatCurrency(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return String(value);
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

function normalizeScopeRows(documentPayload) {
  const contentRows = normalizeList(documentPayload?.scope?.content_list).map((item, index) => {
    const row = item && typeof item === "object" ? item : {};
    const usageSummary =
      row.reverageUseRate !== undefined || row.maxUseRate !== undefined
        ? `平均使用率 ${firstMeaningful(row.reverageUseRate, "-")}% / 峰值 ${firstMeaningful(row.maxUseRate, "-")}%`
        : "-";
    return {
      id: row.id || `scope-${index}`,
      applicationParty: row.applicationParty || row.softName || documentPayload?.project_name || "-",
      resourceType: row.resourceType || row.purchaseType || row.type || "-",
      businessDescription: row.businessDescription || row.softDesc || row.name || "-",
      subType: row.subType || row.code || row.softName || "-",
      previousQuantity: row.previousQuantity ?? "",
      previousCost: row.previousCost ?? "",
      currentQuantity: row.currentQuantity ?? "",
      quantityChange: row.quantityChange ?? "-",
      currentCost: row.currentCost ?? "",
      costChange: row.costChange ?? "-",
      changeExplain: row.changeExplain || usageSummary,
    };
  });
  if (contentRows.length) {
    return contentRows;
  }
  return normalizeList(documentPayload?.scope?.business_processes).map((item, index) => {
    const row = item && typeof item === "object" ? item : {};
    return {
      id: row.id || `scope-process-${index}`,
      applicationParty: row.productName || documentPayload?.project_name || "-",
      resourceType: row.type || row.level || "-",
      businessDescription: row.name || row.processName || "-",
      subType: row.code || row.processCode || "-",
      previousQuantity: "",
      previousCost: "",
      currentQuantity: row.busNum ?? "",
      quantityChange: "-",
      currentCost: "",
      costChange: "-",
      changeExplain: "来自开发范围接口",
    };
  });
}

function normalizeSoftwareScopeRows(documentPayload) {
  return normalizeList(documentPayload?.scope?.content_list)
    .filter((item) => item && typeof item === "object")
    .filter((row) => row.softName || row.softDesc || row.purchaseType || row.reverageUseRate !== undefined || row.maxUseRate !== undefined)
    .map((row, index) => ({
      id: row.id || `software-scope-${index}`,
      softwareName: row.softName || row.name || "-",
      purchaseType: row.purchaseType || row.type || "-",
      averageUseRate: row.reverageUseRate ?? "-",
      maxUseRate: row.maxUseRate ?? "-",
      description: row.softDesc || row.businessDescription || "-",
    }));
}

function buildSystemProjectScopeEntries(documentPayload) {
  const processRows = normalizeList(documentPayload?.scope?.business_processes);
  const rawGoals = normalizeList(documentPayload?.remote_snapshot?.endpoints?.project_goal?.data);
  const goalMap = new Map(
    rawGoals
      .filter((item) => item && typeof item === "object")
      .map((item, index) => [
        item.id || `goal-${index}`,
        {
          id: item.id || `goal-${index}`,
          label: `项目目标${index + 1}`,
          title: item.goalName || item.goalContent || documentPayload?.okr?.objective || `项目目标${index + 1}`,
        },
      ]),
  );

  const grouped = new Map();
  processRows.forEach((item, index) => {
    const row = item && typeof item === "object" ? item : {};
    const goalId = row.goalId || rawGoals[0]?.id || "default-goal";
    const goalMeta =
      goalMap.get(goalId) ||
      {
        id: goalId,
        label: `项目目标${grouped.size + 1}`,
        title: documentPayload?.okr?.objective || "项目目标",
      };
    if (!grouped.has(goalId)) {
      grouped.set(goalId, {
        ...goalMeta,
        flowCount: 0,
        businessUnitCount: 0,
        rows: [],
      });
    }
    const group = grouped.get(goalId);
    group.flowCount += 1;
    group.businessUnitCount = Math.max(group.businessUnitCount, Number(row.busNum) || 0);
    group.rows.push({
      id: row.id || `scope-process-${index}`,
      productName: row.productName || "-",
      processCode: row.code || "-",
      processName: row.name || "-",
      roleName: row.roleName || "-",
      businessUnitText: row.busNum ? `查看详情 (${row.busNum})` : "-",
      type: row.type || "-",
    });
  });

  if (!grouped.size) {
    grouped.set("default-goal", {
      id: "default-goal",
      label: "项目目标1",
      title: documentPayload?.okr?.objective || "项目目标",
      flowCount: 0,
      businessUnitCount: 0,
      rows: [],
    });
  }
  return Array.from(grouped.values());
}

function buildProjectValueEntries(documentPayload, activeTab) {
  const tamModels = documentPayload?.tam_models || {};
  const groups = [
    { key: "capability", label: "能力（竞争力）模型", items: normalizeList(tamModels.capability) },
    { key: "result", label: "结果（财务/客户）模型", items: normalizeList(tamModels.result) },
    { key: "management", label: "管理（运营）模型", items: normalizeList(tamModels.management) },
  ];
  const selectedGroups = activeTab === "overview" ? groups : groups.filter((group) => group.key === activeTab);
  const entries = selectedGroups.flatMap((group) =>
    group.items.map((item, index) => ({
      id: `${group.key}-${index}`,
      groupLabel: group.label,
      title: item.title || item.name || "-",
      benefitDepartment: item.benefit_department || item.benefitDepartment || item.department || "-",
      target: item.target_3y || item.target3y || item.target || "-",
      currentState: item.current_state || item.currentState || item.status || "-",
      calculationBasis: item.calculation_basis || item.calculationBasis || "-",
    })),
  );
  if (entries.length) {
    return entries;
  }
  return [
    {
      id: "project-value-fallback",
      groupLabel: activeTab === "result" ? "结果（财务/客户）模型" : activeTab === "management" ? "管理（运营）模型" : "能力（竞争力）模型",
      title: "项目价值说明",
      benefitDepartment: "-",
      target: documentPayload?.project_value || "暂无项目价值说明",
      currentState: "-",
      calculationBasis: "-",
    },
  ];
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

function projectValueGroupFromType(type) {
  const normalized = String(type ?? "").trim();
  if (normalized === "1") {
    return "capability";
  }
  if (normalized === "2") {
    return "result";
  }
  if (normalized === "3") {
    return "management";
  }
  return "capability";
}

function projectValueGroupLabel(groupKey) {
  if (groupKey === "result") {
    return "结果(财务/客户)模型";
  }
  if (groupKey === "management") {
    return "管理(运营)模型";
  }
  return "能力(竞争力)模型";
}

function buildOkrEntries(documentPayload) {
  const rawGoalData = documentPayload?.remote_snapshot?.endpoints?.project_goal?.data;
  if (Array.isArray(rawGoalData) && rawGoalData.length) {
    return rawGoalData.map((item, index) => ({
      id: item?.id || `okr-${index}`,
      title: item?.goalName || `项目目标 ${index + 1}`,
      productLineName: item?.productLineName || documentPayload?.okr?.product_chain || "",
      relatedProducts: normalizeList(item?.subProductDtoList).map((product, productIndex) => ({
        id: product?.id || `${item?.id || index}-product-${productIndex}`,
        name: product?.productName || product?.name || product?.title || "-",
      })),
      objective: item?.goalName || item?.goalContent || documentPayload?.okr?.objective || "",
      squadOkr: item?.okrName || documentPayload?.okr?.squad_okr || "",
      timeRange: {
        start: item?.startTime || item?.targetStartTime || documentPayload?.okr?.time_range?.start || "",
        end: item?.endTime || item?.targetEndTime || documentPayload?.okr?.time_range?.end || "",
      },
      keyResults: normalizeList(item?.keyResultDtoList).map((goal, goalIndex) => ({
        id: goal?.id || `${item?.id || index}-kr-${goalIndex}`,
        order: goal?.orderNum ?? goalIndex + 1,
        content: goal?.keyResult || goal?.content || goal?.name || "-",
      })),
    }));
  }

  const okr = documentPayload?.okr || {};
  return [
    {
      id: "okr-fallback",
      title: "项目目标 1",
      productLineName: okr.product_chain || "",
      relatedProducts: normalizeList(okr.related_products).map((product, index) => ({
        id: `fallback-product-${index}`,
        name: typeof product === "object" ? product?.productName || product?.name || JSON.stringify(product) : String(product),
      })),
      objective: okr.objective || "",
      squadOkr: okr.squad_okr || "",
      timeRange: okr.time_range || { start: "", end: "" },
      keyResults: normalizeList(okr.key_results).map((item, index) => ({
        id: `fallback-kr-${index}`,
        order: index + 1,
        content: typeof item === "object" ? item?.keyResult || item?.content || JSON.stringify(item) : String(item),
      })),
    },
  ];
}

function buildProjectValueEntriesById(documentPayload, activeTab) {
  const tamModels = documentPayload?.tam_models || {};
  const rawProjectValues = normalizeList(documentPayload?.remote_snapshot?.endpoints?.project_value?.data);
  const grouped = new Map();

  const pushEntry = (groupKey, item, fallbackIndex) => {
    const entryId = item?.projectValueId || item?.id || item?.valueId || `${groupKey}-${fallbackIndex}`;
    const mapKey = `${groupKey}:${entryId}`;
    const current = grouped.get(mapKey) || {
      id: mapKey,
      entryId,
      groupKey,
      groupLabel: projectValueGroupLabel(groupKey),
      title: "-",
      benefitDepartment: "-",
      target: "-",
      currentState: "-",
      calculationBasis: "-",
    };
    current.title = firstMeaningful(current.title !== "-" ? current.title : "", item?.title, item?.name, current.title, "-");
    current.benefitDepartment = firstMeaningful(
      current.benefitDepartment !== "-" ? current.benefitDepartment : "",
      item?.benefit_department,
      item?.benefitDepartment,
      item?.department,
      normalizeDepartmentValue(item?.deptId),
      current.benefitDepartment,
      "-",
    );
    current.target = firstMeaningful(
      current.target !== "-" ? current.target : "",
      item?.valueGoal,
      item?.target_3y,
      item?.target3y,
      item?.target,
      current.target,
      "-",
    );
    current.currentState = firstMeaningful(
      current.currentState !== "-" ? current.currentState : "",
      item?.currentStatus,
      item?.current_state,
      item?.currentState,
      item?.status,
      current.currentState,
      "-",
    );
    current.calculationBasis = firstMeaningful(
      current.calculationBasis !== "-" ? current.calculationBasis : "",
      item?.content,
      item?.calculation_basis,
      item?.calculationBasis,
      current.calculationBasis,
      "-",
    );
    grouped.set(mapKey, current);
  };

  [
    { key: "capability", items: normalizeList(tamModels.capability) },
    { key: "result", items: normalizeList(tamModels.result) },
    { key: "management", items: normalizeList(tamModels.management) },
  ].forEach((group) => {
    group.items.forEach((item, index) => pushEntry(group.key, item, index));
  });

  rawProjectValues.forEach((item, index) => {
    pushEntry(projectValueGroupFromType(item?.type), item, index);
  });

  const entries = Array.from(grouped.values()).filter((entry) => activeTab === "overview" || entry.groupKey === activeTab);
  if (entries.length) {
    return entries;
  }
  return [
    {
      id: "project-value-fallback",
      entryId: "-",
      groupKey: activeTab === "overview" ? "capability" : activeTab,
      groupLabel: projectValueGroupLabel(activeTab === "overview" ? "capability" : activeTab),
      title: "项目价值说明",
      benefitDepartment: "-",
      target: documentPayload?.project_value || "暂无项目价值说明",
      currentState: "-",
      calculationBasis: "-",
    },
  ];
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
    const rawProjectValues = normalizeList(documentPayload?.remote_snapshot?.endpoints?.project_value?.data);
    rawProjectValues.forEach((item, index) => {
      pushEntry(projectValueGroupFromType(item?.type), item, index);
    });
  }

  return groups;
}

function buildSystemScopeRows(documentPayload) {
  return normalizeList(documentPayload?.scope?.microservices).map((item, index) => {
    const row = item && typeof item === "object" ? item : { name: item };
    return {
      id: row.id || row.microserviceId || row.serviceId || `system-scope-${index}`,
      groupName: firstMeaningful(
        row.groupName,
        row.rootName,
        row.categoryName,
        row.domainName,
        row.systemDomainName,
        "系统",
      ),
      systemName: firstMeaningful(
        row.parentSystemName,
        row.systemName,
        row.applicationSystemName,
        row.appName,
        "未命名系统",
      ),
      code: firstMeaningful(row.microserviceCode, row.serviceCode, row.code, row.systemCode, "-"),
      name: firstMeaningful(row.microserviceName, row.name, row.serviceName, row.systemName, "-"),
      type: firstMeaningful(row.microserviceTypeName, row.typeName, row.type, row.systemTypeName, "微服务"),
      owner: firstMeaningful(row.ownerName, row.responsiblePerson, row.managerName, row.userName, row.principal, "-"),
      qualityLevel: firstMeaningful(
        row.qualityTargetLevel,
        row.qualityLevel,
        row.qualityGrade,
        row.levelName,
        "-",
      ),
      gradeBasis: firstMeaningful(row.gradeBasis, row.levelBasis, row.remark, row.description, row.content, "-"),
    };
  });
}

function buildSystemScopeTree(documentPayload) {
  const tree = documentPayload?.remote_snapshot?.endpoints?.project_scope_dev?.data?.systemRelationSystemTrees;
  const rows = buildSystemScopeRows(documentPayload);
  const relatedNames = new Set(rows.map((item) => item.systemName).filter(Boolean));

  const walk = (items) =>
    normalizeList(items)
      .map((item, index) => {
        const node = item && typeof item === "object" ? item : {};
        const name = firstMeaningful(node.name, node.title, `系统节点${index + 1}`);
        const children = walk(node.children);
        const matched = relatedNames.has(name);
        if (!children.length && !matched && !String(node.type || "").trim()) {
          return null;
        }
        return {
          id: node.id || `${name}-${index}`,
          name,
          type: String(node.type || "").trim().toLowerCase(),
          children,
          matched,
        };
      })
      .filter(Boolean);

  const nodes = walk(tree);
  if (nodes.length) {
    return nodes;
  }
  return rows.map((row, index) => ({
    id: row.id || `system-${index}`,
    name: row.systemName,
    type: "system",
    matched: true,
    children: [],
  }));
}

function budgetMetricValue(rawBudget, summary, keys, fallback = 0) {
  for (const key of keys) {
    const value = rawBudget?.[key];
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }
  return fallback ?? firstMeaningful(summary?.budget_year, 0);
}

function buildBudgetSummary(documentPayload) {
  const summary = documentPayload?.project_summary || {};
  const rawBudget = documentPayload?.remote_snapshot?.endpoints?.budget?.data || {};
  const requestBudget = budgetMetricValue(
    rawBudget,
    summary,
    ["applyTotalBudget", "applyBudgetYear", "proBudgetYear", "proBudget"],
    summary.budget_year || 0,
  );
  const acceptedBudget = budgetMetricValue(
    rawBudget,
    summary,
    ["acceptTotalBudget", "acceptedTotalBudget", "acceptBudget", "acceptTotalMoney", "acceptMoneyTotal"],
    0,
  );
  const currentAcceptBudget = budgetMetricValue(
    rawBudget,
    summary,
    ["applyAcceptBudget", "applyAcceptanceBudget", "acceptApplyBudget", "applyBudget"],
    0,
  );
  const remainingBudget = firstMeaningful(
    rawBudget?.remainBudget,
    rawBudget?.remainingBudget,
    rawBudget?.surplusBudget,
    Number(requestBudget || 0) - Number(acceptedBudget || 0),
  );
  return {
    budgetTypeName: firstMeaningful(rawBudget?.budgetTypeName, summary.project_category_name, "预算"),
    requestBudget,
    acceptedBudget,
    currentAcceptBudget,
    remainingBudget,
  };
}

function buildBudgetRows(documentPayload) {
  const rawBudget = documentPayload?.remote_snapshot?.endpoints?.budget?.data || {};
  const partInfos = normalizeList(rawBudget?.partInfos);
  if (partInfos.length) {
    return partInfos.map((item, index) => ({
      id: item?.id || `budget-${index}`,
      index: index + 1,
      title: firstMeaningful(item?.budgetName, item?.content, item?.partName, "未命名预算项"),
      code: firstMeaningful(item?.budgetCode, item?.bmdNo, "-"),
      supplier: firstMeaningful(item?.supplierName, "-"),
      calcMethod: firstMeaningful(item?.calcMethod, "-"),
      amount: firstMeaningful(item?.expectFee, item?.budgetYearPrice, item?.partPrice, 0),
      procurementMethod: firstMeaningful(item?.procurementMethod, "-"),
    }));
  }

  return normalizeList(documentPayload?.budget?.cost_items).map((item, index) => ({
    id: item?.id || `budget-${index}`,
    index: index + 1,
    title: item?.name || "未命名预算项",
    code: item?.budget_subject || "-",
    supplier: item?.supplier_name || "-",
    calcMethod: item?.calculation || "-",
    amount: item?.amount || 0,
    procurementMethod: item?.purchase_mode || "-",
  }));
}

function procurementMethodLabel(value) {
  const mapping = {
    "1": "直接采购",
    "2": "招标采购",
    "3": "询比采购",
    "4": "竞争性谈判",
    "5": "单一来源",
    "6": "开发资源池",
  };
  const normalized = String(value ?? "").trim();
  return mapping[normalized] || normalized || "-";
}

function buildProjectBadges(summary) {
  const candidates = [
    summary.business_subcategory_name,
    summary.project_category_name,
    summary.project_type_name,
    summary.fixed_project_label,
  ];
  return candidates.filter((item, index) => item && candidates.indexOf(item) === index).slice(0, 3);
}

function isChangeProjectSummary(summary) {
  const candidates = [
    summary?.project_type_name,
    summary?.project_category_name,
    summary?.business_subcategory_name,
  ]
    .filter(Boolean)
    .map((item) => String(item));
  return candidates.some((item) => item.includes("变革项目"));
}

function isSystemDevelopmentSummary(summary) {
  const candidates = [
    summary?.project_type_name,
    summary?.project_category_name,
    summary?.business_subcategory_name,
    summary?.business_category_name,
  ]
    .filter(Boolean)
    .map((item) => String(item));
  return candidates.some((item) => ["系统开发及实施", "系统研发及实施", "工作台开发及实施"].some((keyword) => item.includes(keyword)));
}

function resolveExcelLayout(summary, preferredSubcategory = "") {
  const matchedLayout = [
    summary?.business_subcategory_name,
    summary?.project_category_name,
    summary?.project_type_name,
    preferredSubcategory,
  ]
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .map((item) => {
      const alias = LAYOUT_ALIAS_TO_SUBCATEGORY.get(item) || item;
      return LATEST_EXCEL_LAYOUT_BY_SUBCATEGORY.get(alias) || NORMALIZED_LATEST_LAYOUT_BY_SUBCATEGORY.get(normalizeLayoutKey(alias));
    })
    .find(Boolean);
  if (matchedLayout) {
    return matchedLayout;
  }
  if (isSystemDevelopmentSummary(summary)) {
    return LATEST_EXCEL_LAYOUTS.system_construction;
  }
  return LATEST_EXCEL_LAYOUTS.standard_with_change;
}

function hasProjectValueData(documentPayload) {
  const valueText = String(documentPayload?.project_value || "").trim();
  const isMeaningfulText =
    valueText &&
    !["暂无项目价值说明", "暂无说明", "-", "null", "undefined", "{}"].includes(valueText) &&
    !valueText.startsWith("{") &&
    !valueText.startsWith("[");
  if (isMeaningfulText) {
    return true;
  }
  const hasMeaningfulObject = (item) => {
    if (!item || typeof item !== "object") {
      return false;
    }
    const checkKeys = [
      "title",
      "name",
      "valueGoal",
      "target_2026",
      "target_2027",
      "target_2028",
      "oneValue",
      "twoValue",
      "threeValue",
      "target_3y",
      "currentStatus",
      "current_state",
      "currentState",
      "content",
      "calculationBasis",
      "calculation_basis",
      "benefitDepartment",
      "benefit_department",
      "deptId",
    ];
    return checkKeys.some((key) => {
      const value = item[key];
      if (Array.isArray(value)) {
        return value.some((entry) => String(entry ?? "").trim() !== "");
      }
      if (value && typeof value === "object") {
        return Object.values(value).some((entry) => String(entry ?? "").trim() !== "");
      }
      return String(value ?? "").trim() !== "";
    });
  };
  const tamCapability = normalizeList(documentPayload?.tam_models?.capability);
  const tamResult = normalizeList(documentPayload?.tam_models?.result);
  const tamManagement = normalizeList(documentPayload?.tam_models?.management);
  if ([...tamCapability, ...tamResult, ...tamManagement].some((item) => hasMeaningfulObject(item))) {
    return true;
  }
  const rawValueEntries = normalizeList(documentPayload?.remote_snapshot?.endpoints?.project_value?.data);
  return rawValueEntries.some((item) => hasMeaningfulObject(item));
}

function filterSectionsByData(sections, documentPayload) {
  const source = Array.isArray(sections) ? sections : [];
  const hasValueData = hasProjectValueData(documentPayload);
  return source.filter((item) => {
    if (!item || typeof item !== "object") {
      return false;
    }
    if (item.key === "project_value" && !hasValueData) {
      return false;
    }
    return true;
  });
}

function resolveRuleCategoryFromSummary(summary, rules) {
  const categoryItems = Array.isArray(rules?.categories) ? rules.categories : [];
  const candidates = [
    summary?.business_subcategory_name,
    summary?.project_category_name,
    summary?.project_type_name,
  ]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  for (const candidate of candidates) {
    const matched = categoryItems.find((item) => String(item?.name || "").trim() === candidate);
    if (matched) {
      return matched.name;
    }
  }
  return "";
}

function renderOverviewItems(items) {
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

function ImageGallery({ images, onPreview }) {
  if (!images.length) {
    return <p className="viewer-empty">暂无图片</p>;
  }
  return (
    <div className="viewer-image-grid">
      {images.map((item, index) => {
        const source = typeof item === "object" ? item.url || item.fileUrl || item.path || item.filePath || item.id || "" : item;
        const label = typeof item === "object" ? item.fileName || item.name || item.title || item.url || item.path || `图片 ${index + 1}` : `图片 ${index + 1}`;
        const url = buildImageUrl(source);
        if (!url) {
          return null;
        }
        return (
          <article key={`${source}-${index}`} className="viewer-image-shell">
            <button className="viewer-image-card" type="button" onClick={() => onPreview(url, label)}>
              <img src={url} alt={label} />
              <span>{label}</span>
            </button>
            <a className="viewer-image-link" href={url} target="_blank" rel="noreferrer">
              新页打开
            </a>
          </article>
        );
      })}
    </div>
  );
}

function ProjectContentBlocks({
  sectionTitle,
  titleLabel,
  contentLabel,
  items,
  fallbackTitle,
  fallbackContent,
  fallbackImages,
  onPreview,
}) {
  const normalizedItems = items.length
    ? items
    : [
        {
          title: fallbackTitle || "未填写",
          content: fallbackContent || "暂无说明",
          images: fallbackImages || [],
        },
      ];

  return (
    <div className="viewer-form-list">
      {normalizedItems.map((item, index) => (
        <article key={`${item.title || sectionTitle}-${index}`} className="viewer-form-card">
          <div className="viewer-form-section-title">{sectionTitle}</div>
          <div className="viewer-form-grid">
            <div className="viewer-form-main">
              <label className="viewer-form-field">
                <span>{titleLabel}</span>
                <div className="viewer-form-box">{item.title || "未填写"}</div>
              </label>
              <label className="viewer-form-field">
                <span>{contentLabel}</span>
                <div className="viewer-form-box viewer-form-box-large">{item.content || "暂无说明"}</div>
              </label>
            </div>
            <div className="viewer-form-side">
              <p className="viewer-form-side-title">添加图片</p>
              <ImageGallery images={normalizeList(item.images)} onPreview={onPreview} />
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function OkrBoard({ documentPayload }) {
  const entries = buildOkrEntries(documentPayload);
  const [activeEntryId, setActiveEntryId] = useState(entries[0]?.id || "");

  useEffect(() => {
    setActiveEntryId(entries[0]?.id || "");
  }, [documentPayload]);

  const activeEntry = entries.find((item) => item.id === activeEntryId) || entries[0];
  const productLineName = activeEntry?.productLineName || "暂无产品链";
  return (
    <div className="viewer-okr-layout">
      <aside className="viewer-okr-side">
        <label className="viewer-okr-field">
          <span>产品链</span>
          <select value={productLineName} disabled>
            <option value={productLineName}>{productLineName}</option>
          </select>
        </label>
        <div className="viewer-okr-side-title">项目已关联的产品</div>
        <div className="viewer-okr-related-list">
          {activeEntry?.relatedProducts?.length ? (
            activeEntry.relatedProducts.map((product) => (
              <button key={product.id} type="button" className="viewer-okr-related-item active">
                {product.name}
              </button>
            ))
          ) : (
            <div className="viewer-empty">暂无关联产品</div>
          )}
        </div>
      </aside>

      <div className="viewer-okr-main">
        <div className="viewer-form-list">
          {entries.map((entry, index) => {
            const isActive = entry.id === activeEntry?.id;
            return (
              <article key={entry.id} className={`viewer-form-card ${isActive ? "viewer-form-card-active" : ""}`}>
                <div className="viewer-form-section-title">
                  <button type="button" className="viewer-okr-entry-button" onClick={() => setActiveEntryId(entry.id)}>
                    {entry.title || `项目目标 ${index + 1}`}
                  </button>
                </div>
                {isActive ? (
                  <>
                    <div className="viewer-value-grid viewer-value-grid-2">
                      <label className="viewer-value-field">
                        <span>项目目标（O）</span>
                        <div className="viewer-value-box">{entry.objective || "暂无说明"}</div>
                      </label>
                      <label className="viewer-value-field">
                        <span>关联战队OKR</span>
                        <div className="viewer-value-box">{entry.squadOkr || "暂无说明"}</div>
                      </label>
                    </div>
                    <div className="viewer-value-grid viewer-value-grid-2">
                      <label className="viewer-value-field">
                        <span>项目对应的产品</span>
                        <div className="viewer-value-box">
                          {entry.relatedProducts?.length ? entry.relatedProducts.map((product) => product.name).join("、") : "暂无关联产品"}
                        </div>
                      </label>
                      <label className="viewer-value-field">
                        <span>预计目标时间范围</span>
                        <div className="viewer-value-box">
                          {entry.timeRange?.start || "-"} <span className="viewer-okr-arrow">→</span> {entry.timeRange?.end || "-"}
                        </div>
                      </label>
                    </div>
                    <label className="viewer-value-field">
                      <span>关键成果（KR）</span>
                      <div className="viewer-okr-kr-list">
                        {entry.keyResults?.length ? (
                          entry.keyResults.map((goal) => (
                            <div key={goal.id} className="viewer-okr-kr-row">
                              <span className="viewer-okr-kr-index">{goal.order}</span>
                              <div className="viewer-value-box">{goal.content || "-"}</div>
                            </div>
                          ))
                        ) : (
                          <div className="viewer-value-box">暂无关键成果</div>
                        )}
                      </div>
                    </label>
                  </>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function SystemScopeBoard({ documentPayload }) {
  const rows = buildSystemScopeRows(documentPayload);
  const treeNodes = buildSystemScopeTree(documentPayload);
  const [keyword, setKeyword] = useState("");
  const [selectedSystem, setSelectedSystem] = useState(rows[0]?.systemName || "");

  useEffect(() => {
    setSelectedSystem(rows[0]?.systemName || "");
  }, [documentPayload]);

  const normalizedKeyword = keyword.trim().toLowerCase();
  const filteredRows = rows.filter((row) => !normalizedKeyword || row.systemName.toLowerCase().includes(normalizedKeyword));
  const activeRows = filteredRows.filter((row) => row.systemName === selectedSystem);
  const activeSystemName = activeRows[0]?.systemName || filteredRows[0]?.systemName || "";
  const tableRows = activeRows.length ? activeRows : filteredRows.filter((row) => row.systemName === activeSystemName);

  function renderTree(nodes, depth = 0) {
    return normalizeList(nodes).map((node) => {
      const children = normalizeList(node.children);
      const label = node.name || "未命名";
      const isLeaf = !children.length;
      const isRelatedSystem = node.matched || rows.some((row) => row.systemName === label);
      const visible =
        !normalizedKeyword ||
        label.toLowerCase().includes(normalizedKeyword) ||
        children.some((child) => JSON.stringify(child).toLowerCase().includes(normalizedKeyword));
      if (!visible) {
        return null;
      }

      if (isLeaf) {
        return (
          <button
            key={node.id}
            type="button"
            className={`viewer-system-tree-item ${activeSystemName === label ? "active" : ""}`}
            style={{ marginLeft: depth * 14 }}
            onClick={() => setSelectedSystem(label)}
          >
            {label}
            {isRelatedSystem ? <span className="viewer-system-tree-badge">已关联</span> : null}
          </button>
        );
      }

      return (
        <details key={node.id} className="viewer-system-tree-node" open>
          <summary className="viewer-system-tree-title" style={{ marginLeft: depth * 14 }}>
            {label}
          </summary>
          <div className="viewer-system-tree-children">{renderTree(children, depth + 1)}</div>
        </details>
      );
    });
  }

  if (!rows.length) {
    return <p className="viewer-empty">暂无系统范围数据</p>;
  }
  return (
    <div className="viewer-system-scope">
      <aside className="viewer-system-tree">
        <div className="viewer-form-section-title">选择关联系统</div>
        <div className="viewer-system-search">
          <input
            type="text"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder="请输入关联系统"
          />
          <button type="button" className="ghost-button">检索</button>
        </div>
        <div className="viewer-system-tree-list">
          {renderTree(treeNodes)}
        </div>
      </aside>

      <section className="viewer-system-table-panel">
        <div className="viewer-system-table-head">
          <span className="viewer-system-chip">{activeSystemName || "未选择系统"}</span>
          <span className="viewer-system-meta">代码质量评价模型</span>
        </div>
        <div className="viewer-scope-table-wrap">
          <table className="viewer-scope-table viewer-system-table">
            <thead>
              <tr>
                <th>序号</th>
                <th>编号</th>
                <th>名称</th>
                <th>类型</th>
                <th>负责人</th>
                <th>质量目标等级</th>
                <th>定级依据</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row, index) => (
                <tr key={row.id}>
                  <td>{index + 1}</td>
                  <td>{row.code}</td>
                  <td>{row.name}</td>
                  <td>{row.type}</td>
                  <td>{row.owner}</td>
                  <td>{row.qualityLevel}</td>
                  <td>{row.gradeBasis}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function SystemProjectScopeBoard({ documentPayload }) {
  const entries = buildSystemProjectScopeEntries(documentPayload);
  const [activeEntryId, setActiveEntryId] = useState(entries[0]?.id || "");

  useEffect(() => {
    setActiveEntryId(entries[0]?.id || "");
  }, [documentPayload]);

  const activeEntry = entries.find((item) => item.id === activeEntryId) || entries[0];
  if (!activeEntry) {
    return <p className="viewer-empty">暂无项目范围数据</p>;
  }

  return (
    <div className="viewer-scope-goal-board">
      <div className="viewer-scope-goal-tabs">
        {entries.map((entry) => (
          <button
            key={entry.id}
            type="button"
            className={`viewer-scope-goal-tab ${activeEntry.id === entry.id ? "active" : ""}`}
            onClick={() => setActiveEntryId(entry.id)}
          >
            {entry.label}(已填写)
          </button>
        ))}
      </div>

      <div className="viewer-scope-goal-title">{activeEntry.title}</div>
      <div className="viewer-scope-goal-meta">
        <span>业务流程总数: {activeEntry.flowCount}</span>
        <span>业务单元总数: {activeEntry.businessUnitCount}</span>
      </div>

      <div className="viewer-scope-table-wrap">
        <table className="viewer-scope-table">
          <thead>
            <tr>
              <th>序号</th>
              <th>产品名称</th>
              <th>流程编码</th>
              <th>流程名称</th>
              <th>业务角色</th>
              <th>业务单元</th>
              <th>开发类别</th>
            </tr>
          </thead>
          <tbody>
            {activeEntry.rows.length ? (
              activeEntry.rows.map((row, index) => (
                <tr key={row.id}>
                  <td>{index + 1}</td>
                  <td>{row.productName}</td>
                  <td>{row.processCode}</td>
                  <td>{row.processName}</td>
                  <td>{row.roleName}</td>
                  <td><span className="viewer-linkish">{row.businessUnitText}</span></td>
                  <td>{row.type}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={7} className="viewer-empty-cell">暂无项目范围数据</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function isPassDecision(decision) {
  return String(decision || "").trim() === "通过";
}

function approvalToneClass(decision) {
  if (isPassDecision(decision)) {
    return "is-pass";
  }
  if (String(decision || "").trim() === "驳回") {
    return "is-reject";
  }
  if (String(decision || "").trim()) {
    return "is-warning";
  }
  return "is-pending";
}

function buildApprovalHighlights(result) {
  if (!result) {
    return [];
  }
  if (isPassDecision(result.decision)) {
    const statistics = result?.baseline?.statistics || {};
    const evidence = [];
    if (statistics.total_rules) {
      evidence.push(`共通过 ${statistics.passed_rules || 0}/${statistics.total_rules} 条审批规则`);
    }
    (result.positive_evidence || []).forEach((item) => {
      if (item) {
        evidence.push(item);
      }
    });
    return Array.from(new Set(evidence)).slice(0, 3);
  }
  return Array.from(new Set([...(result.risks || []), ...(result.missing_information || [])])).slice(0, 4);
}

function buildProjectCommentary(result) {
  if (!isPassDecision(result?.decision)) {
    return "";
  }
  return String(result?.project_commentary || "").trim();
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
      evidence: item.evidence || "",
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

function formatApprovalTimestamp(value) {
  if (!value) {
    return "";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString("zh-CN", { hour12: false });
}

function ApprovalInfoCard({ projectId, approvalResult, approvalDetails, approvalSource }) {
  const [detailOpen, setDetailOpen] = useState(false);
  const toneClass = approvalToneClass(approvalDetails?.decision);
  const highlights = buildApprovalHighlights(approvalDetails);
  const projectCommentary = buildProjectCommentary(approvalDetails);
  const detailItems = normalizeApprovalDetailItems(approvalDetails);
  const sectionTitle = isPassDecision(approvalDetails?.decision) ? "证据" : "关注事项";
  const approvalTimestamp = formatApprovalTimestamp(approvalDetails?.generated_at);
  const approvalTimestampLabel = approvalSource === "history" ? "上次审批时间" : "本次审批时间";

  return (
    <section className="card viewer-approval-card">
      <div className="viewer-approval-tabs">
        <span className="viewer-approval-tab active">审批信息</span>
        <span className="viewer-approval-tab">审批流水</span>
      </div>
      {approvalDetails ? (
        <div className={`viewer-approval-hero ${toneClass}`}>
          <div className="viewer-approval-hero-head">
            <span className={`viewer-decision-pill ${toneClass}`}>{approvalDetails.decision || "-"}</span>
            {approvalDetails?.baseline?.score !== undefined ? (
              <span className="viewer-approval-score">评分 {approvalDetails.baseline.score}</span>
            ) : null}
          </div>
          {approvalTimestamp ? <p className="viewer-approval-meta">{approvalTimestampLabel}: {approvalTimestamp}</p> : null}
          <p className="viewer-approval-summary">{approvalDetails.summary || "-"}</p>
          {projectCommentary ? (
            <div className="viewer-approval-section">
              <strong>项目评价</strong>
              <p className="viewer-approval-commentary">{projectCommentary}</p>
            </div>
          ) : null}
          {highlights.length ? (
            <div className="viewer-approval-section">
              <strong>{sectionTitle}</strong>
              <ul className="viewer-approval-list">
                {highlights.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
      {approvalDetails && detailItems.length ? (
        <div className="viewer-approval-actions">
          <button className="ghost-button" type="button" onClick={() => setDetailOpen((current) => !current)}>
            {detailOpen ? "收起明细" : "审批明细"}
          </button>
        </div>
      ) : null}
      {approvalDetails && detailOpen ? (
        <div className="viewer-approval-detail-panel">
          <div className="viewer-approval-detail-head">
            <h3>审批明细</h3>
            <span>{detailItems.length} 项检查</span>
          </div>
          <div className="viewer-approval-detail-list">
            {detailItems.map((item) => (
              <article key={item.id} className="viewer-approval-detail-card">
                <div className="viewer-approval-detail-row">
                  <strong>{item.checkPoint}</strong>
                  <span className={`viewer-detail-status ${detailStatusTone(item.status)}`}>{item.status}</span>
                </div>
                <div className="viewer-approval-detail-meta">
                  <span>规则ID: {item.ruleId}</span>
                  {item.severity ? <span>级别: {item.severity}</span> : null}
                </div>
                {item.resultText ? (
                  <div className="viewer-approval-detail-block">
                    <strong>检查结果</strong>
                    <p>{item.resultText}</p>
                  </div>
                ) : null}
                {item.suggestion ? (
                  <div className="viewer-approval-detail-block">
                    <strong>建议</strong>
                    <p>{item.suggestion}</p>
                  </div>
                ) : null}
                {item.evidence ? (
                  <div className="viewer-approval-detail-block">
                    <strong>证据</strong>
                    <pre>{item.evidence}</pre>
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      ) : null}
      <div className="hero-copy" style={{ marginBottom: 16 }}>
        接口记录目录: <code>runtime/api_result/projects/{projectId}/</code>
      </div>
      <div className="result-box viewer-approval-result">{approvalResult || "暂无数据"}</div>
    </section>
  );
}

function ScopeTable({ rows }) {
  if (!rows.length) {
    return <p className="viewer-empty">暂无项目范围数据</p>;
  }
  return (
    <div className="viewer-scope-table-wrap">
      <table className="viewer-scope-table">
        <thead>
          <tr>
            <th rowSpan="2">应用方</th>
            <th rowSpan="2">资源类型</th>
            <th rowSpan="2">业务描述</th>
            <th rowSpan="2">子类型</th>
            <th colSpan="2">2025年费用(元)</th>
            <th colSpan="4">2026年费用(元)</th>
            <th rowSpan="2">变化点说明</th>
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
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.applicationParty}</td>
              <td>{row.resourceType}</td>
              <td>{row.businessDescription}</td>
              <td>{row.subType}</td>
              <td>{formatCurrency(row.previousQuantity)}</td>
              <td>{formatCurrency(row.previousCost)}</td>
              <td>{formatCurrency(row.currentQuantity)}</td>
              <td>{row.quantityChange}</td>
              <td>{formatCurrency(row.currentCost)}</td>
              <td>{row.costChange}</td>
              <td>{row.changeExplain}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SoftwareScopeTable({ rows }) {
  if (!rows.length) {
    return <p className="viewer-empty">暂无项目范围数据</p>;
  }
  return (
    <div className="viewer-software-scope">
      <p className="viewer-software-scope-tip">以下数据均来源于软件中心，请上软件中心确认数据。</p>
      <div className="viewer-scope-table-wrap">
        <table className="viewer-scope-table">
          <thead>
            <tr>
              <th>软件名称</th>
              <th>采购类别</th>
              <th>最大使用率(%)</th>
              <th>平均使用率(%)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.softwareName}</td>
                <td>{row.purchaseType}</td>
                <td>{row.maxUseRate}</td>
                <td>{row.averageUseRate}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="viewer-software-scope-description">
        {rows.map((row) => (
          <section key={`${row.id}-description`} className="viewer-software-scope-block">
            <strong>软件描述:</strong>
            <div className="viewer-software-scope-text">{row.description}</div>
          </section>
        ))}
      </div>
    </div>
  );
}

function ProjectSolutionBlocks({ section, onPreview }) {
  const items = normalizeList(section?.items);
  if (!items.length) {
    return <p className="viewer-empty">暂无项目方案条目</p>;
  }
  return (
    <div className="viewer-solution-list">
      {items.map((item, index) => (
        <article key={`${item.title || "solution"}-${index}`} className="viewer-solution-card">
          <div className="viewer-solution-main">
            <label className="viewer-solution-field">
              <span>项目方案</span>
              <div className="viewer-solution-box">{item.title || `方案 ${index + 1}`}</div>
            </label>
            <label className="viewer-solution-field">
              <span>方案内容</span>
              <div className="viewer-solution-box viewer-solution-content">{item.content || "暂无内容"}</div>
            </label>
          </div>
          <div className="viewer-solution-side">
            <p className="viewer-solution-side-title">添加图片</p>
            <ImageGallery images={normalizeList(item.images)} onPreview={onPreview} />
          </div>
        </article>
      ))}
    </div>
  );
}

function ProjectValueCards({ entries }) {
  return (
    <div className="viewer-value-list">
      {entries.map((entry) => (
        <article key={entry.id} className="viewer-value-card">
          <div className="viewer-value-section-title">基本信息</div>
          <div className="viewer-value-grid viewer-value-grid-3">
            <label className="viewer-value-field">
              <span>指标分类</span>
              <div className="viewer-value-box">{entry.groupLabel}</div>
            </label>
            <label className="viewer-value-field">
              <span>指标标题</span>
              <div className="viewer-value-box">{entry.title}</div>
            </label>
            <label className="viewer-value-field">
              <span>受益部门</span>
              <div className="viewer-value-box">{entry.benefitDepartment}</div>
            </label>
          </div>
          <div className="viewer-value-grid viewer-value-grid-2">
            <label className="viewer-value-field">
              <span>价值目标</span>
              <div className="viewer-value-box">{entry.target}</div>
            </label>
            <label className="viewer-value-field">
              <span>现状</span>
              <div className="viewer-value-box">{entry.currentState}</div>
            </label>
          </div>
          <label className="viewer-value-field">
            <span>测算依据</span>
            <div className="viewer-value-box">{entry.calculationBasis}</div>
          </label>
        </article>
      ))}
    </div>
  );
}

function TamModelBoard({ documentPayload, activeTab }) {
  const groups = buildTamModelEntries(documentPayload);
  const key = activeTab === "result" || activeTab === "management" ? activeTab : "capability";
  const entries = groups[key] || [];
  const groupLabel = projectValueGroupLabel(key);

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
          <div className="viewer-value-section-title">基本信息</div>
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

function buildMilestoneRows(documentPayload) {
  const rawItems = normalizeList(documentPayload?.remote_snapshot?.endpoints?.milestones?.data);
  const rows = [];
  const seen = new Set();

  rawItems.forEach((item, index) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const title = String(item.milestoneTitle || item.title || item.name || `计划 ${index + 1}`).trim();
    const start = String(item.milestoneStartDate || item.startDate || item.start || item.planStartDate || item.milestoneDate || "").trim();
    const end = String(item.milestoneDoneDate || item.endDate || item.end || item.planEndDate || item.milestoneDate || "").trim();
    if (!title && !start && !end) {
      return;
    }
    const dedupeKey = `${title}::${start}::${end}`;
    if (seen.has(dedupeKey)) {
      return;
    }
    seen.add(dedupeKey);
    rows.push({
      index: rows.length + 1,
      title: title || `计划 ${index + 1}`,
      start: start || "-",
      end: end || "-",
    });
  });

  if (rows.length) {
    return rows;
  }

  const milestones = documentPayload?.milestones || {};
  return [
    { index: 1, title: "绔嬮」璁″垝", start: milestones.approval_plan?.start || "-", end: milestones.approval_plan?.end || "-" },
    { index: 2, title: "鍚堝悓绛捐璁″垝", start: milestones.contract_plan?.start || "-", end: milestones.contract_plan?.end || "-" },
    {
      index: 3,
      title: milestones.target_plan?.title || documentPayload?.project_name || "椤圭洰鐩爣",
      start: milestones.target_plan?.start || "-",
      end: milestones.target_plan?.end || "-",
    },
  ];
}

function MilestoneTable({ documentPayload }) {
  const milestones = documentPayload?.milestones || {};
  const fallbackRows = [
    { index: 1, title: "立项计划", value: milestones.approval_plan },
    { index: 2, title: "合同签订计划", value: milestones.contract_plan },
    { index: 3, title: milestones.target_plan?.title || documentPayload?.project_name || "项目目标", value: milestones.target_plan },
  ];
  const rows = buildMilestoneRows(documentPayload);

  return (
    <div className="viewer-scope-table-wrap">
      <table className="viewer-scope-table viewer-milestone-table">
        <thead>
          <tr>
            <th>序号</th>
            <th>里程碑标题</th>
            <th>计划启动时间</th>
            <th>计划完成时间</th>
          </tr>
        </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.index}>
                  <td>{row.index}</td>
                  <td>{row.title}</td>
                  <td>
                    <span className="viewer-date-box">{row.start || row.value?.start || "-"}</span>
                  </td>
                  <td>
                    <span className="viewer-date-box">{row.end || row.value?.end || "-"}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
  );
}

function BudgetTable({ documentPayload }) {
  const rows = buildBudgetRows(documentPayload);
  if (!rows.length) {
    return <p className="viewer-empty">暂无预算信息</p>;
  }
  return (
    <div className="viewer-scope-table-wrap">
      <table className="viewer-scope-table viewer-budget-detail-table">
        <thead>
          <tr>
            <th>序号</th>
            <th>预算标题</th>
            <th>预算编码</th>
            <th>供应商</th>
            <th>测算依据</th>
            <th>预算金额</th>
            <th>采购方式</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>{row.index}</td>
              <td>{row.title}</td>
              <td>{row.code}</td>
              <td>{row.supplier}</td>
              <td>{row.calcMethod}</td>
              <td>{formatCurrency(row.amount)}</td>
              <td>{row.procurementMethod}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function parseNumeric(value) {
  if (value === null || value === undefined || value === "") {
    return NaN;
  }
  if (typeof value === "number") {
    return value;
  }
  const normalized = String(value).replace(/,/g, "").trim();
  if (!normalized) {
    return NaN;
  }
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : NaN;
}

function buildHistoryInvestmentData(documentPayload) {
  const costChange = documentPayload?.cost_change || {};
  const directRows = normalizeList(costChange.history_items)
    .filter((item) => item && typeof item === "object")
    .map((item, index) => ({
      index: item.index || index + 1,
      project_year: firstMeaningful(item.project_year, item.year, item.projectYear, "-"),
      project_name: firstMeaningful(item.project_name, item.projectName, "-"),
      project_content: firstMeaningful(item.project_content, item.projectContent, item.content, "-"),
      project_amount: firstMeaningful(item.project_amount, item.projectAmount, item.amount, ""),
      related_cost: firstMeaningful(item.related_cost, item.relatedCost, item.involveFee, ""),
    }));

  const fallbackRows = normalizeList(documentPayload?.remote_snapshot?.endpoints?.cost_change?.data)
    .filter((item) => item && typeof item === "object")
    .map((item, index) => ({
      index: index + 1,
      project_year: firstMeaningful(item.projectYear, item.year, item.budgetYear, item.proBudgetYear, "-"),
      project_name: firstMeaningful(item.projectName, item.preProjectName, item.name, item.serialNo, "-"),
      project_content: firstMeaningful(item.projectContent, item.content, item.analysis, item.description, "-"),
      project_amount: firstMeaningful(item.projectAmount, item.proBudget, item.amount, item.expectFee, ""),
      related_cost: firstMeaningful(item.relatedCost, item.involveFee, item.cost, item.changeAmount, item.threeValue, ""),
    }));

  const rows = directRows.length ? directRows : fallbackRows;
  const previousProjects = normalizeList(costChange.previous_projects).length
    ? normalizeList(costChange.previous_projects)
    : Array.from(new Set(rows.map((row) => String(row.project_name || "").trim()).filter(Boolean)));

  const inferredTotal = rows.reduce((sum, row) => {
    const related = parseNumeric(row.related_cost);
    if (Number.isFinite(related)) {
      return sum + related;
    }
    const amount = parseNumeric(row.project_amount);
    return Number.isFinite(amount) ? sum + amount : sum;
  }, 0);

  const historyTotalCost = firstMeaningful(
    costChange.history_total_cost,
    Number.isFinite(inferredTotal) && inferredTotal > 0 ? inferredTotal : "",
  );

  const hasHistoryCost = typeof costChange.has_history_cost === "boolean"
    ? costChange.has_history_cost
    : rows.length > 0;

  return {
    rows,
    hasHistoryCost,
    previousProjects,
    historyTotalCost,
    historyAnalysis: costChange.history_analysis || "",
  };
}

function HistoryInvestmentPanel({ documentPayload }) {
  const data = buildHistoryInvestmentData(documentPayload);
  return (
    <div className="history-investment-panel">
      <div className="history-investment-form-row">
        <div className="history-investment-field">
          <span className="history-investment-label">是否有历史费用：</span>
          <div className="history-radio-group">
            <span className={`history-radio-item ${data.hasHistoryCost ? "active" : ""}`}>是</span>
            <span className={`history-radio-item ${!data.hasHistoryCost ? "active" : ""}`}>否</span>
          </div>
        </div>

        <div className="history-investment-field history-project-field">
          <span className="history-investment-label">前序项目</span>
          <div className="history-project-tags">
            {data.previousProjects.length ? (
              data.previousProjects.map((project) => (
                <span key={project} className="history-project-tag">
                  {project}
                </span>
              ))
            ) : (
              <span className="history-project-empty">-</span>
            )}
          </div>
        </div>

        <div className="history-investment-field history-total-field">
          <span className="history-investment-label">历史费用</span>
          <div className="history-total-box">{data.historyTotalCost === "" ? "-" : formatCurrency(data.historyTotalCost)}</div>
        </div>
      </div>

      {data.rows.length ? (
        <div className="viewer-scope-table-wrap">
          <table className="viewer-scope-table viewer-budget-detail-table history-investment-table">
            <thead>
              <tr>
                <th>序号</th>
                <th>项目年度</th>
                <th>项目名称</th>
                <th>项目内容</th>
                <th>项目金额</th>
                <th>涉及费用</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={`history-${row.index}-${row.project_name}`}>
                  <td>{row.index}</td>
                  <td>{row.project_year || "-"}</td>
                  <td>{row.project_name || "-"}</td>
                  <td>{row.project_content || "-"}</td>
                  <td>{row.project_amount === "" ? "-" : formatCurrency(row.project_amount)}</td>
                  <td>{row.related_cost === "" ? "-" : formatCurrency(row.related_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="viewer-empty">暂无历史投入数据</p>
      )}

      {data.historyAnalysis ? (
        <>
          <div className="viewer-budget-section-title">历史分析</div>
          <div className="viewer-value-box history-analysis-box">{data.historyAnalysis}</div>
        </>
      ) : null}
    </div>
  );
}

function BudgetBoard({ documentPayload }) {
  const rawBudget = documentPayload?.remote_snapshot?.endpoints?.budget?.data || {};
  const budgetSummary = buildBudgetSummary(documentPayload);
  const items = normalizeList(rawBudget?.partInfos);
  const [activeBudgetTab, setActiveBudgetTab] = useState("items");

  const summaryFields = [
    { label: "项目预算", value: formatCurrency(firstMeaningful(rawBudget?.proBudget, budgetSummary.requestBudget, 0)) },
    { label: "2026年项目年度预算(不含税)", value: formatCurrency(firstMeaningful(rawBudget?.proBudgetYear, rawBudget?.proBudget, 0)) },
    { label: "2027年项目年度预算(不含税)", value: formatCurrency(firstMeaningful(rawBudget?.proBudgetTwoYear, 0)) },
    { label: "2028年项目年度预算(不含税)", value: formatCurrency(firstMeaningful(rawBudget?.proBudgetThreeYear, 0)) },
    { label: "申请总预算", value: formatCurrency(firstMeaningful(rawBudget?.applyTotalBudget, 0)) },
    { label: "2026年申请项目年度预算(不含税)", value: formatCurrency(firstMeaningful(rawBudget?.applyBudgetYear, rawBudget?.applyTotalBudget, 0)) },
    { label: "2027年申请项目年度预算(不含税)", value: formatCurrency(firstMeaningful(rawBudget?.applyBudgetTwoYear, 0)) },
    { label: "2028年申请项目年度预算(不含税)", value: formatCurrency(firstMeaningful(rawBudget?.applyBudgetThreeYear, 0)) },
  ];

  return (
    <div className="viewer-budget-page">
      <div className="viewer-budget-subject">预算科目 - {budgetSummary.budgetTypeName}</div>
      <div className="viewer-budget-inner-tabs">
        <button type="button" className={`viewer-tab ${activeBudgetTab === "items" ? "active" : ""}`} onClick={() => setActiveBudgetTab("items")}>
          费用构成
        </button>
        <button type="button" className={`viewer-tab ${activeBudgetTab === "tail" ? "active" : ""}`} onClick={() => setActiveBudgetTab("tail")}>
          长尾费用
        </button>
        <button type="button" className={`viewer-tab ${activeBudgetTab === "history" ? "active" : ""}`} onClick={() => setActiveBudgetTab("history")}>
          历史投入
        </button>
      </div>

      {activeBudgetTab === "items" ? (
        <>
          <div className="viewer-value-grid viewer-value-grid-4">
            {summaryFields.map((field) => (
              <label key={field.label} className="viewer-value-field">
                <span>{field.label}</span>
                <div className="viewer-value-box">{field.value}</div>
              </label>
            ))}
          </div>

          <div className="viewer-budget-section-title">费用构成及采购方式</div>
          <div className="viewer-form-list">
            {items.length ? items.map((item, index) => (
              <article key={item.id || index} className="viewer-form-card">
                <div className="viewer-value-grid viewer-value-grid-4">
                  <label className="viewer-value-field">
                    <span>费用构成名称</span>
                    <div className="viewer-value-box">{firstMeaningful(item.budgetName, item.content, "-")}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>采购方式</span>
                    <div className="viewer-value-box">{procurementMethodLabel(item.procurementMethod)}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>是否使用IT开发资源池</span>
                    <div className="viewer-value-box">{item.useDevelopPool ? "是" : "否"}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>计算方式</span>
                    <div className="viewer-value-box">{item.calcMethod || "-"}</div>
                  </label>
                </div>
                <div className="viewer-value-grid viewer-value-grid-4">
                  <label className="viewer-value-field">
                    <span>数量</span>
                    <div className="viewer-value-box">{formatValue(item.number)}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>单价</span>
                    <div className="viewer-value-box">{formatCurrency(item.partPrice)}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>费用构成项目预算</span>
                    <div className="viewer-value-box">{formatCurrency(item.expectFee)}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>2026费用构成项目计划年度预算</span>
                    <div className="viewer-value-box">{formatCurrency(item.budgetYearPrice)}</div>
                  </label>
                </div>
                <div className="viewer-value-grid viewer-value-grid-3 viewer-budget-bottom-grid">
                  <label className="viewer-value-field">
                    <span>2027费用构成项目计划年度预算</span>
                    <div className="viewer-value-box">{formatCurrency(item.budgetYearPriceTwoYear)}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>2028费用构成项目计划年度预算</span>
                    <div className="viewer-value-box">{formatCurrency(item.budgetYearPriceThreeYear)}</div>
                  </label>
                  <label className="viewer-value-field">
                    <span>意向供应商</span>
                    <div className="viewer-value-box">{item.supplierName || "-"}</div>
                  </label>
                </div>
              </article>
            )) : <p className="viewer-empty">暂无费用构成信息</p>}
          </div>
        </>
      ) : null}

      {activeBudgetTab === "tail" ? <p className="viewer-empty">暂无长尾费用数据</p> : null}
      {activeBudgetTab === "history" ? <HistoryInvestmentPanel documentPayload={documentPayload} /> : null}
    </div>
  );
}

const ARCHITECTURE_REVIEW_PREVIEW = {
  business: ["业务对象", "概念模型", "三板斧", "指标树", "流程架构", "业务能力架构"],
  data: ["流程维度评审", "系统维度评审"],
  technology: ["自动化检测评审", "技术栈偏离评审", "技术架构分类指标评审"],
  security: [
    "应用系统安全等级评审（系统开发类）",
    "信息系统安全需求和设计要点评审（系统开发类）",
    "数据安全评审（系统开发类）",
    "数据服务类项目安全评审（数据服务类）",
  ],
};

function normalizeArchitectureReviewGroups(reviewPayload) {
  const groups = Array.isArray(reviewPayload?.groups) ? reviewPayload.groups : [];
  return groups.map((group) => {
    const items = normalizeList(group?.items).map((item, index) => ({
      id: item?.id || `${group?.key || "review"}-${index + 1}`,
      index: item?.index || index + 1,
      dimension: item?.dimension || "",
      checkpoint: item?.checkpoint || "",
      value_model: item?.value_model || "",
      reviewer: item?.reviewer || "",
      conclusion: item?.conclusion || "",
      description: item?.description || "",
    }));
    return {
      key: group?.key || `review-${groups.length}`,
      title: group?.title || "评审状态",
      ok: Boolean(group?.ok),
      message: group?.message || "",
      linkLabel: group?.link_label || "",
      summary: group?.summary || {},
      context: group?.context || {},
      items,
    };
  });
}

function filterArchitectureReviewPayload(reviewPayload, allowedKeys) {
  const groups = normalizeArchitectureReviewGroups(reviewPayload);
  if (!allowedKeys?.length) {
    return { groups };
  }
  return {
    groups: groups.filter((group) => allowedKeys.includes(group.key)),
  };
}

function buildArchitectureReviewTags(group) {
  const summary = group.summary || {};
  if (group.key === "business") {
    return [
      summary.product_count ? `产品数 ${summary.product_count}` : "",
      summary.business_process_count ? `业务流程数 ${summary.business_process_count}` : "",
      summary.business_unit_count ? `业务单元数 ${summary.business_unit_count}` : "",
      summary.business_object_count ? `业务对象数 ${summary.business_object_count}` : "",
    ].filter(Boolean);
  }
  if (group.key === "data") {
    return [
      summary.flow_dimension_count ? `维度数 ${summary.flow_dimension_count}` : "",
      summary.check_point_count ? `检查点 ${summary.check_point_count}` : "",
    ].filter(Boolean);
  }
  if (group.key === "technology" || group.key === "security") {
    return [
      summary.app_count ? `应用数 ${summary.app_count}` : "",
      summary.service_count ? `服务数 ${summary.service_count}` : "",
      summary.safety_level ? `安全等级 ${summary.safety_level}` : "",
    ].filter(Boolean);
  }
  return [];
}

function buildArchitecturePreviewItems(group) {
  if (group.items.length) {
    return group.items.map((item) => item.checkpoint || item.dimension || "-");
  }
  return ARCHITECTURE_REVIEW_PREVIEW[group.key] || [];
}

function renderArchitectureSummaryCards(group) {
  const summary = group.summary || {};
  if (group.key === "business") {
    const cards = [
      { label: "产品数", value: summary.product_count || 0 },
      { label: "业务流程数", value: summary.business_process_count || 0 },
      { label: "业务单元数", value: summary.business_unit_count || 0 },
      { label: "业务对象数", value: summary.business_object_count || 0 },
    ];
    return (
      <div className="architecture-review-summary-grid">
        {cards.map((item) => (
          <article key={item.label} className="architecture-review-summary-card">
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </article>
        ))}
      </div>
    );
  }
  const cards = [
    { label: "应用数", value: summary.app_count ?? "-" },
    { label: "服务数", value: summary.service_count ?? "-" },
    { label: "安全等级", value: summary.safety_level || "-" },
    { label: "检查点", value: group.items.length || 0 },
  ];
  return (
    <div className="architecture-review-summary-grid">
      {cards.map((item) => (
        <article key={item.label} className="architecture-review-summary-card">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </article>
      ))}
    </div>
  );
}

function ArchitectureReviewDetailDialog({ review, projectName, onClose }) {
  if (!review) {
    return null;
  }
  return (
    <div className="architecture-review-dialog-backdrop" onClick={onClose}>
      <div className="architecture-review-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="section-head">
          <div>
            <h2>{review.title}Checklist总体结论</h2>
            <p className="category-meta">
              {review.key === "business" ? "请去EAMAP平台中维护相关信息" : review.message || projectName}
            </p>
          </div>
          <button className="ghost-button" type="button" onClick={onClose}>
            关闭
          </button>
        </div>

        {renderArchitectureSummaryCards(review)}

        <div className="architecture-review-dialog-chip-row">
          <span className="viewer-pill">{projectName}</span>
          {review.context?.product_name ? <span className="viewer-pill viewer-pill-muted">{review.context.product_name}</span> : null}
          {review.linkLabel ? <span className="viewer-linkish">{review.linkLabel}</span> : null}
        </div>

        {review.items.length ? (
          <div className="table-wrap architecture-review-detail-wrap">
            <table className="compact-table architecture-review-detail-table">
              <thead>
                <tr>
                  <th>序号</th>
                  <th>维度</th>
                  <th>检查点</th>
                  <th>价值主张及评审模型</th>
                  <th>初审人</th>
                  <th>初审结论</th>
                </tr>
              </thead>
              <tbody>
                {review.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.index}</td>
                    <td>{item.dimension || "-"}</td>
                    <td>{item.checkpoint || "-"}</td>
                    <td>{item.value_model || item.description || "-"}</td>
                    <td>{item.reviewer || "-"}</td>
                    <td>
                      <span className={`architecture-review-conclusion ${(item.conclusion || "").includes("通过") ? "is-pass" : ""}`}>
                        {item.conclusion || "-"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="architecture-review-empty">
            {review.message || "接口已调用，但当前没有返回可展示的评审明细。"}
          </div>
        )}
      </div>
    </div>
  );
}

function ArchitectureReviewPanel({ projectName, reviewPayload, loading, error, onOpenDetail }) {
  const groups = normalizeArchitectureReviewGroups(reviewPayload);

  if (loading) {
    return <p className="viewer-empty">正在加载架构评审结果...</p>;
  }
  if (error) {
    return <p className="viewer-empty">{error}</p>;
  }
  if (!groups.length) {
    return <p className="viewer-empty">暂无架构评审结果</p>;
  }

  return (
    <div className="architecture-review-board">
      {groups.map((group) => {
        const previewItems = buildArchitecturePreviewItems(group);
        const tags = buildArchitectureReviewTags(group);
        return (
          <article key={group.key} className="architecture-review-card">
            <div className="architecture-review-head">
              <div>
                <h3>{group.title}</h3>
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
            <div className="architecture-review-actions">
              <button className="ghost-button" type="button" onClick={() => onOpenDetail(group)}>
                查看评审详情
              </button>
              {group.linkLabel ? <span className="viewer-linkish">{group.linkLabel}</span> : null}
            </div>
            <div className="architecture-review-list">
              {previewItems.map((item, index) => (
                <div key={`${group.key}-${item}-${index}`} className="architecture-review-row">
                  <span className="architecture-review-index">{index + 1}</span>
                  <span>{item}</span>
                </div>
              ))}
            </div>
          </article>
        );
      })}
    </div>
  );
}

function ArchitectureReviewBoard({ documentPayload }) {
  const businessFlowCount = normalizeList(documentPayload?.scope?.business_processes).length;
  const systemCount = normalizeList(documentPayload?.scope?.microservices).length;
  const tamCount =
    normalizeList(documentPayload?.tam_models?.capability).length +
    normalizeList(documentPayload?.tam_models?.result).length +
    normalizeList(documentPayload?.tam_models?.management).length;
  const memberCount = normalizeList(documentPayload?.organization?.members).length;

  const groups = [
    {
      title: "业务架构评审状态",
      tags: [businessFlowCount ? "已关联业务流程" : "", tamCount ? "已关联TAM模型" : ""].filter(Boolean),
      items: ["业务单元评审", "业务流程评审", "运营指标评审"],
    },
    {
      title: "技术架构评审状态",
      tags: [systemCount ? "已关联系统" : ""].filter(Boolean),
      items: ["自动化检测评审", "技术栈偏离评审", "技术架构7类指标评审"],
    },
    {
      title: "数据架构评审状态",
      tags: [],
      items: ["流程维度评审", "系统维度评审"],
    },
    {
      title: "安全架构评审状态",
      tags: [memberCount ? "已关联团队成员" : ""].filter(Boolean),
      items: [
        "应用系统安全等级评审（系统开发类）",
        "信息系统安全需求和设计要点评审（系统开发类）",
        "数据安全评审（系统开发类）",
        "数据服务类项目安全评审（数据服务类）",
      ],
    },
  ];

  return (
    <div className="architecture-review-board">
      {groups.map((group) => (
        <article key={group.title} className="architecture-review-card">
          <div className="architecture-review-head">
            <div>
              <h3>{group.title}</h3>
            </div>
            <div className="architecture-review-tags">
              {group.tags.map((tag) => (
                <span key={tag} className="architecture-review-tag">
                  {tag}
                </span>
              ))}
            </div>
          </div>
          <div className="architecture-review-list">
            {group.items.map((item, index) => (
              <div key={item} className="architecture-review-row">
                <span className="architecture-review-index">{index + 1}</span>
                <span>{item}</span>
              </div>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function inferOrganizationPartyType(item) {
  const flag = String(item?.flag || "").trim();
  const peopleBelong = String(item?.peopleBelong || "").trim();
  const type = String(item?.type || "").trim();
  const employeeName = String(item?.employeeName || item?.memberName || item?.userName || item?.name || "").trim();
  const maintenanceName = String(item?.maintenanceName || "").trim();
  if (flag === "1") {
    return "third";
  }
  if (flag === "0") {
    return "own";
  }
  if (employeeName === "资源池" || maintenanceName === "资源池") {
    return "third";
  }
  if (peopleBelong.includes("三方") || peopleBelong.includes("外部")) {
    return "third";
  }
  if (type === "1" || type === "2") {
    return "third";
  }
  return "own";
}

function buildOrganizationRows(documentPayload) {
  const flag0Rows = Array.isArray(documentPayload?.remote_snapshot?.endpoints?.organization_flag_0?.data)
    ? documentPayload.remote_snapshot.endpoints.organization_flag_0.data
    : [];
  const flag1Rows = Array.isArray(documentPayload?.remote_snapshot?.endpoints?.organization_flag_1?.data)
    ? documentPayload.remote_snapshot.endpoints.organization_flag_1.data
    : [];
  const legacyRows =
    !flag0Rows.length && !flag1Rows.length && Array.isArray(documentPayload?.remote_snapshot?.endpoints?.organization?.data)
      ? documentPayload.remote_snapshot.endpoints.organization.data
      : [];
  const rawRows = [...flag0Rows, ...flag1Rows, ...legacyRows];
  if (rawRows.length) {
    const rows = [];
    const seen = new Set();
    rawRows
      .filter((item) => item && typeof item === "object")
      .forEach((item, index) => {
        const partyType = inferOrganizationPartyType(item);
        const id =
          item.id ||
          item.employeeId ||
          `${partyType}-${item.postName || item.roleName || ""}-${item.rank || item.level || ""}-${item.planStartDate || ""}-${item.planEndDate || ""}-${index}`;
        if (seen.has(id)) {
          return;
        }
        seen.add(id);
        const priceWithTax = Number(item.priceTax ?? item.unitPriceTax ?? 0) || 0;
        const priceWithoutTax = Number(item.price ?? item.unitPrice ?? 0) || 0;
        const manDay = Number(item.manDay ?? item.workload ?? item.taskPlan ?? 0) || 0;
        const taxRateValue = item.taxRate ?? item.rate ?? "";
        const taxRateText = taxRateValue === "" || taxRateValue === null || taxRateValue === undefined
          ? "-"
          : String(taxRateValue).includes("%")
            ? String(taxRateValue)
            : `${taxRateValue}%`;
        rows.push({
          id,
          name: item.employeeName || item.memberName || item.userName || item.name || item.maintenanceName || "-",
          employeeId: item.employeeId || item.userId || "-",
          teamName: item.teamName || item.groupName || "未分组",
          postName: item.postName || item.roleName || item.dutyName || "-",
          rank: item.rank || item.levelName || item.level || "-",
          planStartDate: item.planStartDate || item.startDate || "-",
          planEndDate: item.planEndDate || item.endDate || "-",
          manDay: item.manDay || item.workload || item.taskPlan || "-",
          manDayValue: manDay,
          partyType,
          partyLabel: partyType === "third" ? item.maintenanceName || item.peopleBelong || "资源池" : item.department || "自有人员",
          priceWithTax,
          priceWithoutTax,
          taxRateText,
          totalWithTax: priceWithTax * manDay,
          totalWithoutTax: priceWithoutTax * manDay,
        });
      });
    return rows;
  }
  return normalizeList(documentPayload?.organization?.members).map((item, index) => ({
    id: `org-fallback-${index + 1}`,
    name: item?.name || "-",
    employeeId: "-",
    teamName: "未分组",
    postName: item?.role || "-",
    rank: item?.level || "-",
    planStartDate: "-",
    planEndDate: "-",
    manDay: item?.workload || item?.task_plan || "-",
    partyType: "own",
  }));
}

function buildThirdPartySummary(rows) {
  return rows.reduce(
    (summary, item) => ({
      totalManDay: summary.totalManDay + (Number(item.manDayValue) || 0),
      totalWithTax: summary.totalWithTax + (Number(item.totalWithTax) || 0),
      totalWithoutTax: summary.totalWithoutTax + (Number(item.totalWithoutTax) || 0),
    }),
    { totalManDay: 0, totalWithTax: 0, totalWithoutTax: 0 },
  );
}

function buildOrganizationChartRows(rows, mode) {
  const groups = new Map();
  rows.forEach((item) => {
    const label =
      mode === "rank"
        ? item.rank || "-"
        : mode === "composition"
          ? item.teamName || "未分组"
          : item.postName || "-";
    if (!groups.has(label)) {
      groups.set(label, { label, own: 0, third: 0 });
    }
    const bucket = groups.get(label);
    if (item.partyType === "third") {
      bucket.third += 1;
    } else {
      bucket.own += 1;
    }
  });
  return Array.from(groups.values()).sort((left, right) => right.own + right.third - (left.own + left.third));
}

function OrganizationBoard({ documentPayload }) {
  const [partyFilter, setPartyFilter] = useState("own");
  const [teamFilter, setTeamFilter] = useState("all");
  const [chartMode, setChartMode] = useState("post");

  const rows = buildOrganizationRows(documentPayload);
  const teams = Array.from(new Set(rows.map((item) => item.teamName).filter(Boolean)));
  const ownCount = rows.filter((item) => item.partyType === "own").length;
  const thirdCount = rows.filter((item) => item.partyType === "third").length;
  const filteredRows = rows.filter((item) => {
    if (partyFilter !== "all" && item.partyType !== partyFilter) {
      return false;
    }
    if (teamFilter !== "all" && item.teamName !== teamFilter) {
      return false;
    }
    return true;
  });
  const thirdPartySummary = buildThirdPartySummary(filteredRows.filter((item) => item.partyType === "third"));
  const chartRows = buildOrganizationChartRows(filteredRows, chartMode);
  const maxChartValue = Math.max(1, ...chartRows.map((item) => item.own + item.third));

  if (!rows.length) {
    return <p className="viewer-empty">暂无组织架构数据</p>;
  }

  return (
    <div className="organization-board">
      <div className="organization-board-main">
        <div className="organization-board-head">
          <div>
            <h3>组织架构</h3>
            <p className="category-meta">请在敏捷小队完成相关岗位信息配置</p>
          </div>
        </div>

        <div className="organization-team-pills">
          <button
            type="button"
            className={`organization-team-pill ${teamFilter === "all" ? "active" : ""}`}
            onClick={() => setTeamFilter("all")}
          >
            全部小队
          </button>
          {teams.map((team) => (
            <button
              key={team}
              type="button"
              className={`organization-team-pill ${teamFilter === team ? "active" : ""}`}
              onClick={() => setTeamFilter(team)}
            >
              {team}
            </button>
          ))}
        </div>

        <div className="organization-toolbar">
          <div className="organization-party-buttons">
            <button
              type="button"
              className={`viewer-tab ${partyFilter === "own" ? "active" : ""}`}
              onClick={() => setPartyFilter("own")}
            >
              自有人员
            </button>
            <button
              type="button"
              className={`viewer-tab ${partyFilter === "third" ? "active" : ""}`}
              onClick={() => setPartyFilter("third")}
            >
              三方人员
            </button>
            <button
              type="button"
              className={`viewer-tab ${partyFilter === "all" ? "active" : ""}`}
              onClick={() => setPartyFilter("all")}
            >
              全部
            </button>
          </div>
          <div className="organization-toolbar-stats">
            <span>共计：{rows.length}人</span>
            <span>自有：{ownCount}人</span>
            <span>三方：{thirdCount}人</span>
          </div>
        </div>

        {partyFilter === "third" ? (
          <>
            <div className="organization-cost-summary">
              <div>
                <span>核定总人天</span>
                <strong>{formatCurrency(thirdPartySummary.totalManDay)}</strong>
              </div>
              <div>
                <span>核定总费用（含税）</span>
                <strong>{formatCurrency(thirdPartySummary.totalWithTax)}元</strong>
              </div>
              <div>
                <span>核定总费用（不含税）</span>
                <strong>{formatCurrency(thirdPartySummary.totalWithoutTax)}元</strong>
              </div>
            </div>
            <div className="table-wrap">
              <table className="compact-table organization-table organization-third-table">
                <thead>
                  <tr>
                    <th className="col-index">序号</th>
                    <th className="col-party">人员归属</th>
                    <th className="col-post">岗位</th>
                    <th className="col-rank">职级</th>
                    <th className="col-price">单价(含税)</th>
                    <th className="col-price">单价(不含税)</th>
                    <th className="col-tax">税率</th>
                    <th className="col-date">计划开始时间</th>
                    <th className="col-date">计划结束时间</th>
                    <th className="col-manday">预计人天</th>
                    <th className="col-total">预计费用(含税)</th>
                    <th className="col-total">预计费用(不含税)</th>
                    <th className="col-action">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((item, index) => (
                    <tr key={item.id}>
                      <td className="col-index">{index + 1}</td>
                      <td className="col-party">{item.partyLabel}</td>
                      <td className="col-post">{item.postName}</td>
                      <td className="col-rank">{item.rank}</td>
                      <td className="col-price">{formatCurrency(item.priceWithTax)}</td>
                      <td className="col-price">{formatCurrency(item.priceWithoutTax)}</td>
                      <td className="col-tax">{item.taxRateText}</td>
                      <td className="col-date">{item.planStartDate}</td>
                      <td className="col-date">{item.planEndDate}</td>
                      <td className="col-manday">{formatCurrency(item.manDayValue)}</td>
                      <td className="col-total">{formatCurrency(item.totalWithTax)}</td>
                      <td className="col-total">{formatCurrency(item.totalWithoutTax)}</td>
                      <td className="col-action">-</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <div className="table-wrap">
            <table className="compact-table organization-table">
              <thead>
                <tr>
                  <th>序号</th>
                  <th>姓名</th>
                  <th>工号</th>
                  <th>敏捷小队</th>
                  <th>岗位</th>
                  <th>职级</th>
                  <th>计划开始时间</th>
                  <th>计划结束时间</th>
                  <th>预计人天</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {filteredRows.map((item, index) => (
                  <tr key={item.id}>
                    <td>{index + 1}</td>
                    <td>{item.name}</td>
                    <td>{item.employeeId}</td>
                    <td>{item.teamName}</td>
                    <td>{item.postName}</td>
                    <td>{item.rank}</td>
                    <td>{item.planStartDate}</td>
                    <td>{item.planEndDate}</td>
                    <td>{item.manDay}</td>
                    <td>-</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <aside className="organization-board-side">
        <div className="organization-chart-head">
          <h3>架构视图</h3>
          <div className="organization-chart-tabs">
            <button
              type="button"
              className={`organization-chart-tab ${chartMode === "post" ? "active" : ""}`}
              onClick={() => setChartMode("post")}
            >
              岗位
            </button>
            <button
              type="button"
              className={`organization-chart-tab ${chartMode === "rank" ? "active" : ""}`}
              onClick={() => setChartMode("rank")}
            >
              职级
            </button>
            <button
              type="button"
              className={`organization-chart-tab ${chartMode === "composition" ? "active" : ""}`}
              onClick={() => setChartMode("composition")}
            >
              人员构成
            </button>
          </div>
        </div>

        <div className="organization-chart-legend">
          <span><i className="organization-legend-swatch own" />自有人员</span>
          <span><i className="organization-legend-swatch third" />三方人员</span>
        </div>

        <div className="organization-chart">
          {chartRows.map((item) => {
            const ownWidth = `${(item.own / maxChartValue) * 100}%`;
            const thirdWidth = `${(item.third / maxChartValue) * 100}%`;
            return (
              <div key={item.label} className="organization-chart-row">
                <div className="organization-chart-label">{item.label}</div>
                <div className="organization-chart-bars">
                  <div className="organization-chart-bar own" style={{ width: ownWidth }} />
                  <div className="organization-chart-bar third" style={{ width: thirdWidth }} />
                </div>
              </div>
            );
          })}
        </div>
      </aside>
    </div>
  );
}

function formatApprovalResult(result) {
  const lines = [`项目: ${result.project_name}`, `品类: ${result.category}`, `结论: ${result.decision}`];
  if (result.summary) {
    lines.push(`摘要: ${result.summary}`);
  }
  if (result.project_commentary && isPassDecision(result.decision)) {
    lines.push(`项目评价: ${result.project_commentary}`);
  }
  if (result.run_dir) {
    lines.push(`审批落盘: ${result.run_dir}`);
  }
  const highlights = isPassDecision(result.decision)
    ? result.positive_evidence || []
    : [...(result.risks || []), ...(result.missing_information || [])];
  lines.push("");
  lines.push(isPassDecision(result.decision) ? "证据:" : "风险摘要:");
  if (highlights.length) {
    highlights.slice(0, 8).forEach((item) => lines.push(`- ${item}`));
  } else {
    lines.push("- 无");
  }
  return lines.join("\n");
}

export default function ProjectViewerPage() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const [rules, setRules] = useState(null);
  const [category, setCategory] = useState("");
  const [documentPayload, setDocumentPayload] = useState(null);
  const [approvalResult, setApprovalResult] = useState("等待加载项目。");
  const [approvalDetails, setApprovalDetails] = useState(null);
  const [approvalSource, setApprovalSource] = useState("current");
  const [approvalDetailOpen, setApprovalDetailOpen] = useState(false);
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [activeSection, setActiveSection] = useState("project_content");
  const [activeTabs, setActiveTabs] = useState({
    project_content: "background",
    project_value: "overview",
    architecture_review: "",
    tam_models: "capability",
    organization: "",
    milestones: "approval_plan",
    budget: "items",
    cost_change: "reason",
  });
  const [previewImage, setPreviewImage] = useState(null);
  const [architectureReviews, setArchitectureReviews] = useState(null);
  const [architectureReviewsLoading, setArchitectureReviewsLoading] = useState(false);
  const [architectureReviewsError, setArchitectureReviewsError] = useState("");
  const [activeArchitectureReview, setActiveArchitectureReview] = useState(null);

  useEffect(() => {
    let alive = true;
    requestJson("/api/rules")
      .then((payload) => {
        if (!alive) {
          return;
        }
        setRules(payload);
        setCategory(searchParams.get("category") || "");
        setApprovalDetails(null);
        setApprovalSource("current");
        setApprovalDetailOpen(false);
      })
      .catch((error) => {
        if (alive) {
          setApprovalDetails(null);
          setApprovalSource("current");
          setApprovalDetailOpen(false);
          setApprovalResult(error.message);
        }
      });
    return () => {
      alive = false;
    };
  }, [searchParams]);

  useEffect(() => {
    if (!rules || category) {
      return;
    }
    const inferredCategory = resolveRuleCategoryFromSummary(documentPayload?.project_summary || {}, rules);
    if (inferredCategory) {
      setCategory(inferredCategory);
      return;
    }
    const backendResolvedCategory = String(documentPayload?.resolved_category || "").trim();
    if (backendResolvedCategory) {
      setCategory(backendResolvedCategory);
      return;
    }
    const fallbackCategory = rules.categories?.[0]?.name || "";
    if (fallbackCategory) {
      setCategory(fallbackCategory);
    }
  }, [rules, category, documentPayload]);

  useEffect(() => {
    if (!projectId || documentPayload?.architecture_review_details) {
      return;
    }
    let alive = true;
    const queryString = category ? `?category=${encodeURIComponent(category)}` : "";
    requestJson(`/api/projects/${encodeURIComponent(projectId)}/document${queryString}`)
      .then((payload) => {
        if (alive) {
          setDocumentPayload(payload);
          const resolvedCategory = String(payload?.resolved_category || "").trim();
          if (resolvedCategory && resolvedCategory !== category) {
            setCategory(resolvedCategory);
          }
        }
      })
      .catch((error) => {
        if (alive) {
          setApprovalDetails(null);
          setApprovalSource("current");
          setApprovalDetailOpen(false);
          setApprovalResult(error.message);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, category]);

  useEffect(() => {
    setActiveArchitectureReview(null);
    setApprovalDetails(null);
    setApprovalSource("current");
    setApprovalDetailOpen(false);
    setApprovalResult("等待加载项目。");
  }, [projectId, category]);

  useEffect(() => {
    if (!projectId || !category || approvalBusy || approvalDetails) {
      return;
    }
    let alive = true;
    requestJson(`/api/projects/${encodeURIComponent(projectId)}/latest-approval?category=${encodeURIComponent(category)}`)
      .then((payload) => {
        if (!alive) {
          return;
        }
        if (payload?.resolved_category && payload.resolved_category !== category) {
          setCategory(payload.resolved_category);
        }
        if (!payload?.found || !payload.result) {
          setApprovalResult("本次未执行审批，暂无上次审批结果。");
          return;
        }
        setApprovalDetails(payload.result);
        setApprovalSource("history");
        setApprovalResult(formatApprovalResult(payload.result));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [projectId, category, approvalBusy, approvalDetails]);

  useEffect(() => {
    if (!projectId || !category) {
      return;
    }
    const embeddedGroups = documentPayload?.architecture_review_details;
    if (Array.isArray(embeddedGroups) && embeddedGroups.length > 0) {
      setArchitectureReviews({
        project_id: projectId,
        project_name: documentPayload?.project_name || projectId,
        document_source: documentPayload?.document_source || "persisted",
        groups: embeddedGroups,
      });
      setArchitectureReviewsError("");
      setArchitectureReviewsLoading(false);
      return;
    }
    if (!documentPayload) {
      return;
    }
    let alive = true;
    setArchitectureReviewsLoading(true);
    setArchitectureReviewsError("");
    requestJson(`/api/projects/${encodeURIComponent(projectId)}/architecture-reviews?category=${encodeURIComponent(category)}`)
      .then((payload) => {
        if (!alive) {
          return;
        }
        setArchitectureReviews(payload);
      })
      .catch((error) => {
        if (!alive) {
          return;
        }
        setArchitectureReviews(null);
        setArchitectureReviewsError(error.message || "架构评审结果加载失败");
      })
      .finally(() => {
        if (alive) {
          setArchitectureReviewsLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, category, documentPayload]);

  useEffect(() => {
    const summary = documentPayload?.project_summary || {};
    const layout = resolveExcelLayout(
      summary,
      category || documentPayload?.resolved_category || documentPayload?.requested_category || "",
    );
    const visibleSections = filterSectionsByData(layout.sections, documentPayload);
    if (!visibleSections.some((item) => item.key === activeSection)) {
      setActiveSection(visibleSections[0]?.key || "project_content");
    }
  }, [documentPayload, activeSection, category]);

  async function runApproval() {
    try {
      setApprovalBusy(true);
      setApprovalDetails(null);
      setApprovalSource("current");
      setApprovalDetailOpen(false);
      setApprovalResult(`正在执行远程审批，请稍候。\n接口记录目录: runtime/api_result/projects/${projectId}/`);
      const result = await requestJson("/api/approve/remote-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId, category }),
      });
      if (result?.resolved_category && result.resolved_category !== category) {
        setCategory(result.resolved_category);
      }
      setApprovalDetails(result);
      setApprovalSource("current");
      setApprovalResult(formatApprovalResult(result));
    } catch (error) {
      setApprovalDetails(null);
      setApprovalSource("current");
      setApprovalDetailOpen(false);
      setApprovalResult(error.message || "审批执行失败");
    } finally {
      setApprovalBusy(false);
    }
  }

  const summary = documentPayload?.project_summary || {};
  const layoutConfig = resolveExcelLayout(
    summary,
    category || documentPayload?.resolved_category || documentPayload?.requested_category || "",
  );
  const isChangeProject = false;
  const isSystemProject = layoutConfig.contentMode === "system";
  const activeSectionDefinitions = filterSectionsByData(layoutConfig.sections, documentPayload);
  const activeTabDefinitions = layoutConfig.tabs;
  const tabs = activeTabDefinitions[activeSection] || [];
  const activeTab = activeTabs[activeSection] || tabs[0]?.key || "";
  const projectBadges = buildProjectBadges(summary);
  const effectiveArchitectureReviews = architectureReviews || { groups: documentPayload?.architecture_review_details || [] };
  const filteredArchitectureReviews = filterArchitectureReviewPayload(
    effectiveArchitectureReviews,
    layoutConfig.architectureReviewKeys,
  );
  const approvalDetailItems = normalizeApprovalDetailItems(approvalDetails);
  const approvalTimestampText = approvalDetails?.generated_at
    ? `${approvalSource === "history" ? "上次审批时间" : "本次审批时间"}: ${formatApprovalTimestamp(approvalDetails.generated_at)}`
    : "";
  const budgetSummary = buildBudgetSummary(documentPayload);
  const softwareScopeRows = normalizeSoftwareScopeRows(documentPayload);
  const useSoftwareScopeTable = EXCEL_VALUE_ONLY_SUBCATEGORIES.has(category) && softwareScopeRows.length > 0;
  const overviewBudgetData = documentPayload?.remote_snapshot?.endpoints?.budget?.data || {};
  const overviewBudgetYear = firstMeaningful(
    overviewBudgetData?.budgetYear,
    documentPayload?.remote_snapshot?.endpoints?.project_base_info?.data?.budgetYear,
    summary.budget_year,
    "-",
  );
  const overviewProjectBudget = firstMeaningful(
    overviewBudgetData?.proBudget,
    overviewBudgetData?.proBudgetYear,
    budgetSummary.requestBudget,
    0,
  );
  const fullWidthContent =
    activeSection === "budget" ||
    (activeSection === "project_content" && (isSystemProject || activeTab === "scope" || activeTab === "solution")) ||
    (activeSection === "project_content" && activeTab === "system_scope") ||
    activeSection === "project_value" ||
    activeSection === "architecture_review" ||
    activeSection === "tam_models" ||
    activeSection === "organization" ||
    activeSection === "milestones";

  const hideTabBar = activeSection === "milestones" || activeSection === "budget" || tabs.length <= 1;

  function renderProjectContent() {
    const section = documentPayload?.project_content?.[activeTab] || {};
    if (isSystemProject) {
      if (activeTab === "background") {
        return (
          <>
            <div id="viewer-content-panel" className="viewer-content-panel-wide">
              <ProjectContentBlocks
                sectionTitle="背景信息"
                titleLabel="背景标题"
                contentLabel="背景内容"
                items={normalizeList(section.items)}
                fallbackTitle={section.title}
                fallbackContent={section.content}
                fallbackImages={normalizeList(section.images)}
                onPreview={(url, title) => setPreviewImage({ url, title })}
              />
            </div>
            <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
          </>
        );
      }
      if (activeTab === "okr") {
        return (
          <>
            <div id="viewer-content-panel" className="viewer-content-panel-wide">
              <OkrBoard documentPayload={documentPayload} />
            </div>
            <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
          </>
        );
      }
      if (activeTab === "scope") {
        return (
          <>
            <div id="viewer-content-panel" className="viewer-content-panel-wide">
              <p className="category-meta">项目范围</p>
              <SystemProjectScopeBoard documentPayload={documentPayload} />
            </div>
            <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
          </>
        );
      }
      if (activeTab === "system_scope") {
        return (
          <>
            <div id="viewer-content-panel" className="viewer-content-panel-wide">
              <p className="category-meta">系统范围</p>
              <SystemScopeBoard documentPayload={documentPayload} />
            </div>
            <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
          </>
        );
      }
      if (activeTab === "solution") {
        return (
          <>
            <div id="viewer-content-panel" className="viewer-content-panel-wide">
              <ProjectSolutionBlocks section={section} onPreview={(url, title) => setPreviewImage({ url, title })} />
            </div>
            <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
          </>
        );
      }
    }
    if (activeTab === "scope") {
      return (
        <>
          <div id="viewer-content-panel" className="viewer-content-panel-wide">
            <p className="category-meta">项目范围</p>
            {useSoftwareScopeTable ? (
              <SoftwareScopeTable rows={softwareScopeRows} />
            ) : (
              <ScopeTable rows={normalizeScopeRows(documentPayload)} />
            )}
          </div>
          <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
        </>
      );
    }
    if (activeTab === "solution") {
      return (
        <>
          <div id="viewer-content-panel" className="viewer-content-panel-wide">
            <ProjectSolutionBlocks section={section} onPreview={(url, title) => setPreviewImage({ url, title })} />
          </div>
          <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
        </>
      );
    }
    return (
      <>
        <div id="viewer-content-panel">
          <p className="category-meta">标题</p>
          <h2>{section.title || "未填写"}</h2>
          <div className="viewer-article">{section.content || "暂无说明"}</div>
        </div>
        <div id="viewer-side-panel">
          <p className="category-meta">结构化条目</p>
          <ul>{normalizeList(section.items).map((item, index) => <li key={index}>{item.title || item.content || item.order || "-"}</li>)}</ul>
          <p className="category-meta" style={{ marginTop: 16 }}>附件与图片</p>
          <ImageGallery images={normalizeList(section.images)} onPreview={(url, title) => setPreviewImage({ url, title })} />
        </div>
      </>
    );
  }

  function renderProjectValue() {
    return (
      <>
        <div id="viewer-content-panel" className="viewer-content-panel-wide">
          <ProjectValueCards entries={buildProjectValueEntriesById(documentPayload, activeTab)} />
        </div>
        <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
      </>
    );
  }

  function renderChangeProjectTamModels() {
    return (
      <>
        <div id="viewer-content-panel" className="viewer-content-panel-wide">
          <TamModelBoard documentPayload={documentPayload} activeTab={activeTab} />
        </div>
        <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
      </>
    );
  }

  function renderArchitectureReview() {
    return (
      <>
        <div id="viewer-content-panel" className="viewer-content-panel-wide">
          <ArchitectureReviewPanel
            projectName={summary.project_name || documentPayload?.project_name || projectId}
            reviewPayload={filteredArchitectureReviews}
            loading={architectureReviewsLoading}
            error={architectureReviewsError}
            onOpenDetail={setActiveArchitectureReview}
          />
        </div>
        <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
      </>
    );
  }

  function renderOrganization() {
    return (
      <>
        <div id="viewer-content-panel" className="viewer-content-panel-wide">
          <OrganizationBoard documentPayload={documentPayload} />
        </div>
        <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
      </>
    );
  }

  function renderMilestones() {
    if (isSystemProject) {
      return (
        <>
          <div id="viewer-content-panel" className="viewer-content-panel-wide">
            <MilestoneTable documentPayload={documentPayload} />
          </div>
          <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
        </>
      );
    }

    const milestones = documentPayload?.milestones || {};
    const mapping = {
      approval_plan: { label: "立项计划", value: milestones.approval_plan },
      contract_plan: { label: "合同计划", value: milestones.contract_plan },
      target_plan: { label: "目标计划", value: milestones.target_plan },
    };
    const current = mapping[activeTab] || mapping.approval_plan;
    return (
      <>
        <div id="viewer-content-panel" className={isSystemProject ? "viewer-content-panel-wide" : ""}>
          <p className="category-meta">{current.label}</p>
          {definitionPairs([
            { label: "开始时间", value: current.value?.start },
            { label: "结束时间", value: current.value?.end },
          ])}
        </div>
        <div id="viewer-side-panel" className={isSystemProject ? "viewer-side-panel-hidden" : ""}>
          {!isSystemProject ? (
            <>
              <p className="category-meta">OKR 时间信息</p>
              {definitionPairs([
                { label: "目标开始", value: documentPayload?.okr?.time_range?.start },
                { label: "目标结束", value: documentPayload?.okr?.time_range?.end },
                { label: "关键结果数量", value: normalizeList(documentPayload?.okr?.key_results).length || 0 },
              ])}
            </>
          ) : null}
        </div>
      </>
    );
  }

  function renderBudget() {
    if (isSystemProject) {
      return (
        <>
          <div id="viewer-content-panel" className="viewer-content-panel-wide">
            <BudgetBoard documentPayload={documentPayload} />
          </div>
          <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
        </>
      );
    }

    const items = normalizeList(documentPayload?.budget?.cost_items);
    if (activeTab === "summary") {
      return (
        <>
          <div id="viewer-content-panel" className={isSystemProject ? "viewer-content-panel-wide" : ""}>
            <p className="category-meta">预算汇总</p>
            {definitionPairs([
              { label: "费用项数量", value: items.length },
              { label: "年度预算", value: documentPayload?.project_summary?.budget_year },
              { label: "固定项目", value: documentPayload?.project_summary?.fixed_project_label },
            ])}
          </div>
          <div id="viewer-side-panel" className={isSystemProject ? "viewer-side-panel-hidden" : ""}>
            {!isSystemProject ? (
              <>
                <p className="category-meta">预算科目列表</p>
                <ul>{items.map((item, index) => <li key={index}>{item.budget_subject || item.name || "-"}</li>)}</ul>
              </>
            ) : null}
          </div>
        </>
      );
    }
    return (
      <>
        <div id="viewer-content-panel" className={isSystemProject ? "viewer-content-panel-wide" : ""}>
          <p className="category-meta">费用项清单</p>
          <div className="viewer-detail-list">
            {items.length ? items.map((item, index) => (
              <article key={index} className="viewer-detail-card">
                <h3>{index + 1}. {item.name || "未命名费用项"}</h3>
                <dl className="viewer-mini-kv">
                  <div><dt>金额</dt><dd>{item.amount || "-"}</dd></div>
                  <div><dt>预算科目</dt><dd>{item.budget_subject || "-"}</dd></div>
                  <div><dt>测算依据</dt><dd>{item.calculation || "-"}</dd></div>
                  <div><dt>采购方式</dt><dd>{item.purchase_mode || "-"}</dd></div>
                </dl>
              </article>
            )) : <p className="viewer-empty">暂无预算信息</p>}
          </div>
        </div>
        <div id="viewer-side-panel" className={isSystemProject ? "viewer-side-panel-hidden" : ""}>
          {!isSystemProject ? definitionPairs([
            { label: "费用项数量", value: items.length },
            { label: "年度预算", value: documentPayload?.project_summary?.budget_year },
            { label: "固定项目", value: documentPayload?.project_summary?.fixed_project_label },
          ]) : null}
        </div>
      </>
    );
  }

  function renderCostChange() {
    const costChange = documentPayload?.cost_change || {};
    if (activeTab === "history") {
      return (
        <>
          <div id="viewer-content-panel">
            <p className="category-meta">历史投入分析</p>
            <HistoryInvestmentPanel documentPayload={documentPayload} />
          </div>
          <div id="viewer-side-panel">
            {definitionPairs([
              { label: "项目状态", value: documentPayload?.project_summary?.project_status_name },
              { label: "流程状态", value: documentPayload?.project_summary?.flow_status_name },
            ])}
          </div>
        </>
      );
    }
    return (
      <>
        <div id="viewer-content-panel">
          <p className="category-meta">变化说明</p>
          {definitionPairs([
            { label: "固定项目", value: costChange.fixed_project ? "是" : "否" },
            { label: "变化原因", value: costChange.reason || "暂无说明" },
          ])}
        </div>
        <div id="viewer-side-panel">
          {definitionPairs([
            { label: "项目状态", value: documentPayload?.project_summary?.project_status_name },
            { label: "流程状态", value: documentPayload?.project_summary?.flow_status_name },
            { label: "项目类别", value: documentPayload?.project_summary?.project_category_name },
          ])}
        </div>
      </>
    );
  }

  function renderExcelMilestones() {
    return (
      <>
        <div id="viewer-content-panel" className="viewer-content-panel-wide">
          <MilestoneTable documentPayload={documentPayload} />
        </div>
        <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
      </>
    );
  }

  function renderExcelBudget() {
    return (
      <>
        <div id="viewer-content-panel" className="viewer-content-panel-wide">
          <BudgetBoard documentPayload={documentPayload} />
        </div>
        <div id="viewer-side-panel" className="viewer-side-panel-hidden" />
      </>
    );
  }

  function renderBody() {
    if (!documentPayload) {
      return (
        <>
          <div id="viewer-content-panel"><p className="viewer-empty">暂无数据</p></div>
          <div id="viewer-side-panel"><p className="viewer-empty">暂无数据</p></div>
        </>
      );
    }
    if (activeSection === "project_content") {
      return renderProjectContent();
    }
    if (activeSection === "project_value") {
      return renderProjectValue();
    }
    if (activeSection === "architecture_review") {
      return renderArchitectureReview();
    }
    if (activeSection === "tam_models") {
      return renderChangeProjectTamModels();
    }
    if (activeSection === "organization") {
      return renderOrganization();
    }
    if (activeSection === "milestones") {
      return renderExcelMilestones();
    }
    if (activeSection === "budget") {
      return renderExcelBudget();
    }
    return renderCostChange();
  }

  return (
    <PageLayout wide>
      <header className="viewer-overview">
        <section className="card viewer-title-bar">
          <div className="viewer-title-main">
            <span className="viewer-title-dot" aria-hidden="true" />
            <div>
              <h1 className="viewer-title">{summary.project_name || documentPayload?.project_name || projectId}</h1>
              <div className="viewer-badge-row">
                {projectBadges.length
                  ? projectBadges.map((item) => (
                      <span key={item} className="viewer-pill">
                        {item}
                      </span>
                    ))
                  : <span className="viewer-pill viewer-pill-muted">未识别分类</span>}
              </div>
            </div>
          </div>
          <div className="viewer-actions">
            <select value={category} onChange={(event) => setCategory(event.target.value)}>
              {(rules?.categories || []).map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name} / {item.group}
                </option>
              ))}
            </select>
            <Link className="nav-link" to={`/workbench?projectId=${encodeURIComponent(projectId)}`}>
              打开管理配置
            </Link>
            <button className="primary-button" type="button" onClick={runApproval} disabled={approvalBusy}>
              {approvalBusy ? "审批执行中..." : "执行远程审批"}
            </button>
          </div>
        </section>

        {approvalDetails ? (
          <section className={`card viewer-decision-banner ${approvalToneClass(approvalDetails.decision)}`}>
            <div className="viewer-decision-banner-head">
              <span className={`viewer-decision-pill ${approvalToneClass(approvalDetails.decision)}`}>
                {approvalDetails.decision || "-"}
              </span>
              {approvalDetails?.baseline?.statistics?.total_rules ? (
                <span className="viewer-approval-score">
                  {approvalDetails.baseline.statistics.passed_rules || 0}/{approvalDetails.baseline.statistics.total_rules} 规则通过
                </span>
              ) : null}
            </div>
            {approvalTimestampText ? <p className="viewer-approval-meta">{approvalTimestampText}</p> : null}
            <p className="viewer-approval-summary">{approvalDetails.summary || "-"}</p>
          </section>
        ) : null}

        <section className="viewer-card-grid viewer-card-grid-overview">
          <article className="card viewer-card dark">
            <p className="panel-label">Ownership</p>
            <h2>项目所属</h2>
            {renderOverviewItems([
              { label: "项目编码", value: summary.project_code },
              { label: "项目经理", value: summary.project_manager_name },
              { label: "业务部门", value: summary.department_name },
              { label: "归属领域", value: summary.domain_name },
            ])}
          </article>

          <article className="card viewer-card viewer-card-soft">
            <p className="panel-label">Classification</p>
            <h2>项目分类</h2>
            {renderOverviewItems([
              { label: "业务类别", value: summary.business_category_name || summary.project_category_name },
              { label: "项目类别", value: summary.project_type_name },
              { label: "业务子类", value: summary.business_subcategory_name || summary.project_category_name },
              { label: "项目等级", value: summary.project_level_name },
            ])}
          </article>

          <article className="card viewer-card viewer-budget-card">
            <div className="viewer-budget-head">
              <div>
                <p className="panel-label">Budget</p>
                <h2>项目预算</h2>
              </div>
              <span className="viewer-budget-pill">{budgetSummary.budgetTypeName}</span>
            </div>
            <div className="viewer-budget-grid">
              <div className="viewer-budget-item">
                <span>项目预算（元）</span>
                <strong>{formatCurrency(overviewProjectBudget)}</strong>
              </div>
              <div className="viewer-budget-item">
                <span>申请项目预算(元/不含税)</span>
                <strong>{formatCurrency(budgetSummary.requestBudget)}</strong>
              </div>
              <div className="viewer-budget-item">
                <span>项目年度</span>
                <strong>{formatValue(overviewBudgetYear)}</strong>
              </div>
              <div className="viewer-budget-item">
                <span>剩余金额(元/不含税)</span>
                <strong>{formatCurrency(budgetSummary.remainingBudget)}</strong>
              </div>
            </div>
          </article>
        </section>
      </header>

      <main className="grid">
        <section className="card span-full">
          {isSystemProject ? (
            <div className="viewer-phase-bar">
              <button type="button" className="viewer-phase-pill active">立项</button>
              <button type="button" className="viewer-phase-pill">验收</button>
            </div>
          ) : null}
          <div className="section-head viewer-progress-head">
            <div>
              <h2>立项进程</h2>
            </div>
            <div className="category-meta">所有必填项填写完成，可提交立项申请</div>
          </div>
          <div className="summary-strip">
            {activeSectionDefinitions.map((item) => {
              const valueMap = {
                project_content: documentPayload?.project_content?.background?.title ? "已填写" : "待补充",
                project_value: documentPayload?.project_value || normalizeList(documentPayload?.tam_models?.capability).length ? "已填写" : "待补充",
                architecture_review:
                  normalizeArchitectureReviewGroups(filteredArchitectureReviews).some((group) => group.ok || group.items.length)
                    ? "已填写"
                    : "待补充",
                tam_models:
                  normalizeList(documentPayload?.tam_models?.capability).length ||
                  normalizeList(documentPayload?.tam_models?.result).length ||
                  normalizeList(documentPayload?.tam_models?.management).length
                    ? "已填写"
                    : "待补充",
                organization: normalizeList(documentPayload?.organization?.members).length ? "已填写" : "待补充",
                milestones: documentPayload?.milestones?.approval_plan?.start ? "已填写" : "待补充",
                budget:
                  normalizeList(documentPayload?.remote_snapshot?.endpoints?.budget?.data?.partInfos).length ||
                  normalizeList(documentPayload?.budget?.cost_items).length
                    ? "已填写"
                    : "待补充",
                cost_change: documentPayload?.cost_change?.reason ? "已填写" : "待补充",
              };
              return (
                <button
                  key={item.key}
                  className={`summary-tile viewer-summary-item ${activeSection === item.key ? "active" : ""}`}
                  type="button"
                  onClick={() => setActiveSection(item.key)}
                >
                  <p className="viewer-summary-label">{item.label}</p>
                  <strong>{valueMap[item.key] || "待补充"}</strong>
                </button>
              );
            })}
          </div>
        </section>

        <section className={`card ${isChangeProject ? "span-full" : "span-2"} viewer-content-block`}>
          <div className="section-head">
            <div>
              <p className="panel-label">Section</p>
              <h2>{activeSectionDefinitions.find((item) => item.key === activeSection)?.label || "项目内容"}</h2>
            </div>
          </div>
          <div className={`viewer-tab-bar ${tabs.length && !hideTabBar ? "" : "is-hidden"}`}>
            {tabs.map((tab) => (
              <button
                key={tab.key}
                className={`viewer-tab ${activeTab === tab.key ? "active" : ""}`}
                type="button"
                onClick={() => setActiveTabs((current) => ({ ...current, [activeSection]: tab.key }))}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className={`viewer-layout ${fullWidthContent ? "viewer-layout-scope" : ""}`}>{renderBody()}</div>
        </section>

        {!isChangeProject ? (
          isSystemProject ? (
            <ApprovalInfoCard
              projectId={projectId}
              approvalResult={approvalResult}
              approvalDetails={approvalDetails}
              approvalSource={approvalSource}
            />
          ) : (
            <ApprovalInfoCard
              projectId={projectId}
              approvalResult={approvalResult}
              approvalDetails={approvalDetails}
              approvalSource={approvalSource}
            />
          )
        ) : null}
      </main>

      {activeArchitectureReview ? (
        <ArchitectureReviewDetailDialog
          review={activeArchitectureReview}
          projectName={summary.project_name || documentPayload?.project_name || projectId}
          onClose={() => setActiveArchitectureReview(null)}
        />
      ) : null}

      {previewImage ? (
        <div className="viewer-image-modal" onClick={() => setPreviewImage(null)}>
          <div className="viewer-image-modal-dialog" onClick={(event) => event.stopPropagation()}>
            <div className="section-head">
              <h2>{previewImage.title}</h2>
              <button className="ghost-button" type="button" onClick={() => setPreviewImage(null)}>
                关闭
              </button>
            </div>
            <img className="viewer-image-modal-img" src={previewImage.url} alt={previewImage.title} />
            <a className="viewer-image-link" href={previewImage.url} target="_blank" rel="noreferrer">
              新页打开
            </a>
          </div>
        </div>
      ) : null}
    </PageLayout>
  );
}
