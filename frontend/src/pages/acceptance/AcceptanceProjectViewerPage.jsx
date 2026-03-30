import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import PageLayout from "../../components/PageLayout";
import { normalizeScene, requestJson } from "../../api";

import {
  INITIATION_SECTIONS,
  TASK_ORDER_PHASE,
  TASK_ORDER_SECTIONS,
  ACCEPTANCE_PROJECT_REVIEW_TAB_KEYS,
  ACCEPTANCE_PROJECT_REVIEW_TABS,
  SECTION_TABS,
  ACCEPTANCE_ORDER_SECTIONS,
  normalizeList,
  formatValue,
  formatCurrency,
  formatCurrencyAllowZero,
  formatPercent,
  formatCompactDate,
  formatCurrencyWithUnit,
  approvalToneClass,
  detailStatusTone,
  normalizeApprovalDetailItems,
  firstMeaningful,
  imageUrlOf,
  hasUploadSectionContent,
  hasReviewTabContent,
  sectionStatus,
  buildProjectBadges,
  acceptanceSectionTitle,
  buildAcceptanceVisibility,
  normalizeNumber,
  toTextItems,
  isTruthyFlag,
  acceptanceScopeTaskStatus,
  buildTaskOrderDrawerReasonOptions,
  buildTaskOrderDrawerWorkItems,
  buildTaskOrderDrawerCriteriaItems,
  buildTaskOrderDrawerEvaluationRows,
  buildTaskOrderDrawerStaffingMatrix,
  buildAcceptanceDetailProcessRows,
  buildAcceptanceDetailMemberRows,
  buildTaskOrders,
  buildTaskOrderViewModel,
  resolveAcceptanceContractIdentity,
  buildAcceptanceContractViewModel,
  taskOrderSectionStatus,
  DefinitionGrid,
  DataTable,
  MachineScopeTable,
  looksLikeMachineScopeRows,
  UploadSection,
  TamModelBoard,
  normalizeProjectReviewBlocks,
  buildProjectReviewGoalGroups,
  buildProjectReviewSystemScopeGroups,
  buildAcceptanceDeliverableStats,
  buildAcceptanceStandardDeliverableRows,
  buildAcceptanceTaskDeliverableGroups,
  AcceptanceDeliverablesBoard,
  AcceptanceDeliverablesDialog,
  ArchitectureReviewPanel,
} from "./projectViewerShared";

const CONFIDENTIAL_SCOPE_CATEGORY_KEYWORDS = ["保密服务", "保密"];
const NON_RESEARCH_TOOL_ANNUAL_MODEL_CATEGORY_KEYWORDS = ["非研发工具许可购买"];

function matchesCategoryKeyword(category, keywords) {
  const normalizedCategory = String(category || "").trim();
  if (!normalizedCategory) {
    return false;
  }
  return keywords.some((keyword) => normalizedCategory === keyword || normalizedCategory.includes(keyword));
}

function scopeYearLabels(budgetYear) {
  const numericYear = Number(String(budgetYear || "").replace(/[^\d]/g, ""));
  if (Number.isFinite(numericYear) && numericYear > 2000) {
    return { previous: numericYear - 1, current: numericYear };
  }
  return { previous: "上一年", current: "当年" };
}

function normalizeStandardScopeRows(rows) {
  return normalizeList(rows)
    .filter((row) => row && typeof row === "object")
    .map((row, index) => ({
      id: row.id || `scope-row-${index + 1}`,
      applicationParty: firstMeaningful(row.applicationParty, row.softName),
      resourceType: firstMeaningful(row.resourceType, row.purchaseType, row.type),
      businessDescription: firstMeaningful(row.businessDescription, row.softDesc, row.name),
      subType: firstMeaningful(row.subType, row.code, row.softName),
      previousQuantity: firstMeaningful(row.previousQuantity, row.pastYearNum),
      previousCost: firstMeaningful(row.previousCost, row.pastYearCost),
      currentQuantity: firstMeaningful(row.currentQuantity, row.budgetYearNum, row.currentYearNum),
      quantityChange: firstMeaningful(row.quantityChange, row.budgetChangeRate),
      currentCost: firstMeaningful(row.currentCost, row.budgetYearCost, row.currentYearCost),
      costChange: firstMeaningful(row.costChange, row.budgetChangeRate),
      changeExplain: firstMeaningful(row.changeExplain, row.machineDesc),
    }));
}

function renderStandardScopeTable(rows, budgetYear) {
  if (!rows.length) {
    return <p className="viewer-empty">暂无项目范围数据</p>;
  }
  const yearLabels = scopeYearLabels(budgetYear);
  return (
    <div className="acceptance-project-review-table-wrap">
      <table className="acceptance-project-review-table">
        <thead>
          <tr>
            <th rowSpan="2">应用方</th>
            <th rowSpan="2">资源类型</th>
            <th rowSpan="2">业务描述</th>
            <th rowSpan="2">子类型</th>
            <th colSpan="2">{yearLabels.previous}年费用(元)</th>
            <th colSpan="4">{yearLabels.current}年费用(元)</th>
            <th rowSpan="2">变化说明</th>
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
              <td>{formatValue(row.applicationParty)}</td>
              <td>{formatValue(row.resourceType)}</td>
              <td>{formatValue(row.businessDescription)}</td>
              <td>{formatValue(row.subType)}</td>
              <td>{formatValue(row.previousQuantity)}</td>
              <td>{formatCurrencyAllowZero(row.previousCost)}</td>
              <td>{formatValue(row.currentQuantity)}</td>
              <td>{formatValue(row.quantityChange)}</td>
              <td>{formatCurrencyAllowZero(row.currentCost)}</td>
              <td>{formatValue(row.costChange)}</td>
              <td>{formatValue(row.changeExplain)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function normalizeSoftwareScopeRows(rows) {
  return normalizeList(rows)
    .filter((row) => row && typeof row === "object")
    .filter((row) => row.softName || row.softDesc || row.purchaseType || row.reverageUseRate !== undefined || row.maxUseRate !== undefined)
    .map((row, index) => ({
      id: row.id || `software-scope-${index + 1}`,
      softwareName: firstMeaningful(row.softName, row.name),
      purchaseType: firstMeaningful(row.purchaseType, row.type),
      maxUseRate: row.maxUseRate,
      averageUseRate: row.reverageUseRate,
      description: firstMeaningful(row.softDesc, row.businessDescription),
    }));
}

function renderSoftwareScopeTable(rows) {
  if (!rows.length) {
    return <p className="viewer-empty">暂无项目范围数据</p>;
  }
  return (
    <div className="acceptance-project-review-stack">
      <div style={{ color: "#d93025", fontSize: 14 }}>以下数据均来源于软件中心，请上软件中心确认数据。</div>
      <div className="acceptance-project-review-table-wrap">
        <table className="acceptance-project-review-table">
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
                <td>{formatValue(row.softwareName)}</td>
                <td>{formatValue(row.purchaseType)}</td>
                <td>{formatValue(row.maxUseRate)}</td>
                <td>{formatValue(row.averageUseRate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>软件描述:</div>
        {rows.map((row) => (
          <section key={`${row.id}-description`} style={{ marginBottom: 12 }}>
            <div style={{ lineHeight: 1.75, whiteSpace: "pre-wrap" }}>{formatValue(row.description)}</div>
          </section>
        ))}
      </div>
    </div>
  );
}

function buildAnnualModelProcessRows(documentPayload) {
  return normalizeList(documentPayload?.scope?.business_processes)
    .filter((row) => row && typeof row === "object")
    .map((row, index) => ({
      id: row.id || `annual-process-${index + 1}`,
      code: firstMeaningful(row.processSchemaCode, row.code),
      name: firstMeaningful(row.name, row.processName),
      level: row.level,
      version: firstMeaningful(row.processVersion, row.version),
      roleName: firstMeaningful(row.roleName, row.businessRoleName),
      created: firstMeaningful(row.processCreatedTime, row.created, row.createTime),
      type: firstMeaningful(row.type, row.categoryName),
    }));
}

function buildAnnualModelSystemRows(documentPayload) {
  const seen = new Set();
  return [
    ...normalizeList(documentPayload?.scope?.microservices),
    ...normalizeList(documentPayload?.scope?.microapps),
  ]
    .filter((row) => row && typeof row === "object")
    .map((row, index) => ({
      id: firstMeaningful(row.id, row.subCode, row.code, `annual-system-${index + 1}`),
      name: firstMeaningful(row.systemName, row.applicationSystemName, row.subName, row.name),
      code: firstMeaningful(row.systemCode, row.subCode, row.code),
    }))
    .filter((row) => {
      const uniqueKey = `${row.name}::${row.code}`;
      if (seen.has(uniqueKey)) {
        return false;
      }
      seen.add(uniqueKey);
      return true;
    });
}

function renderAnnualModelAssociationTables(processRows, systemRows) {
  return (
    <div className="acceptance-project-review-stack">
      <article className="acceptance-project-review-panel">
        <div className="acceptance-project-review-panel-title">关联业务流程列表</div>
        <div className="acceptance-project-review-table-wrap">
          <table className="acceptance-project-review-table">
            <thead>
              <tr>
                <th>流程架构编码</th>
                <th>流程名称</th>
                <th>流程级别</th>
                <th>当前版本号</th>
                <th>业务角色</th>
                <th>创建时间</th>
                <th>开发类别</th>
              </tr>
            </thead>
            <tbody>
              {processRows.length ? processRows.map((row) => (
                <tr key={row.id}>
                  <td>{formatValue(row.code)}</td>
                  <td>{formatValue(row.name)}</td>
                  <td>{formatValue(row.level)}</td>
                  <td>{formatValue(row.version)}</td>
                  <td>{formatValue(row.roleName)}</td>
                  <td>{formatValue(formatCompactDate(row.created))}</td>
                  <td>{formatValue(row.type)}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan="7" className="viewer-empty-cell">暂无关联业务流程数据</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </article>
      <article className="acceptance-project-review-panel">
        <div className="acceptance-project-review-panel-title">关联系统列表</div>
        <div className="acceptance-project-review-table-wrap">
          <table className="acceptance-project-review-table">
            <thead>
              <tr>
                <th>序号</th>
                <th>系统名称</th>
                <th>系统编号</th>
              </tr>
            </thead>
            <tbody>
              {systemRows.length ? systemRows.map((row, index) => (
                <tr key={row.id}>
                  <td>{index + 1}</td>
                  <td>{formatValue(row.name)}</td>
                  <td>{formatValue(row.code)}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan="3" className="viewer-empty-cell">暂无关联系统数据</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </article>
    </div>
  );
}

export default function ProjectViewerPage() {
  const { projectId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const scene = normalizeScene("acceptance");
  const viewerPhase = "acceptance";
  const [rules, setRules] = useState(null);
  const [acceptanceTabConfig, setAcceptanceTabConfig] = useState(null);
  const [category, setCategory] = useState(searchParams.get("category") || "");
  const [documentPayload, setDocumentPayload] = useState(null);
  const [architecturePayload, setArchitecturePayload] = useState(null);
  const [latestApproval, setLatestApproval] = useState(null);
  const [approvalDetailOpen, setApprovalDetailOpen] = useState(false);
  const [taskOrderItems, setTaskOrderItems] = useState([]);
  const [taskOrderDetail, setTaskOrderDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [taskOrderLoading, setTaskOrderLoading] = useState(false);
  const [taskOrderError, setTaskOrderError] = useState("");
  const [acceptanceTaskDrawerTask, setAcceptanceTaskDrawerTask] = useState(null);
  const [acceptanceTaskDrawerDetail, setAcceptanceTaskDrawerDetail] = useState(null);
  const [acceptanceTaskDrawerLoading, setAcceptanceTaskDrawerLoading] = useState(false);
  const [acceptanceTaskDrawerError, setAcceptanceTaskDrawerError] = useState("");
  const [acceptanceContractDrawerContract, setAcceptanceContractDrawerContract] = useState(null);
  const [acceptanceContractDrawerDetail, setAcceptanceContractDrawerDetail] = useState(null);
  const [acceptanceContractDrawerLoading, setAcceptanceContractDrawerLoading] = useState(false);
  const [acceptanceContractDrawerError, setAcceptanceContractDrawerError] = useState("");
  const [acceptanceDetailTaskId, setAcceptanceDetailTaskId] = useState("");
  const [acceptanceDetailTaskDetail, setAcceptanceDetailTaskDetail] = useState(null);
  const [acceptanceDetailTaskLoading, setAcceptanceDetailTaskLoading] = useState(false);
  const [acceptanceDetailTaskError, setAcceptanceDetailTaskError] = useState("");
  const [acceptanceDetailViewMode, setAcceptanceDetailViewMode] = useState("processes");
  const [deliverablesDialogOpen, setDeliverablesDialogOpen] = useState(false);
  const [deliverablesDialogTab, setDeliverablesDialogTab] = useState("standard");
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [approvalMessage, setApprovalMessage] = useState("");
  const [activeProjectReviewGoalId, setActiveProjectReviewGoalId] = useState("");
  const [activeProjectReviewSystemKey, setActiveProjectReviewSystemKey] = useState("");
  const [projectReviewSystemSearch, setProjectReviewSystemSearch] = useState("");
  const [activeSection, setActiveSection] = useState(viewerPhase === "acceptance" ? "acceptance_stage" : viewerPhase === TASK_ORDER_PHASE ? "basic_info" : "project_content");
  const [activeTabs, setActiveTabs] = useState({
    project_content: "background",
    project_review: "background",
    project_value: "overview",
    tam_models: "capability",
    milestones: "approval_plan",
    budget: "items",
    cost_change: "reason",
    acceptance_scope: "tasks",
    acceptance_detail: "task_acceptance",
  });

  const summary = documentPayload?.project_summary || {};
  const acceptance = documentPayload?.acceptance || {};
  const acceptanceBudgetSummary = useMemo(() => {
    const mappedSummary = documentPayload?.budget?.summary || {};
    const rawBudget = documentPayload?.remote_snapshot?.endpoints?.budget?.data || {};
    const requestBudget = normalizeNumber(
      firstMeaningful(
        mappedSummary.request_budget,
        mappedSummary.project_budget_no_tax,
        rawBudget.applyTotalBudget,
        rawBudget.applyBudget,
        rawBudget.proBudget,
        summary.applyBudget,
        summary.applyTotalBudget,
        summary.proBudget,
        0,
      ),
    );
    const projectBudget = normalizeNumber(
      firstMeaningful(
        mappedSummary.project_budget,
        mappedSummary.request_budget,
        rawBudget.proBudget,
        rawBudget.applyTotalBudget,
        summary.projectBudget,
        summary.applyTotalBudget,
        summary.applyBudget,
        summary.proBudget,
        0,
      ),
    );
    const projectYearBudget = normalizeNumber(
      firstMeaningful(
        mappedSummary.project_year_budget,
        rawBudget.applyBudgetYear,
        rawBudget.proBudgetYear,
        summary.applyYearBudget,
        summary.projectYearBudget,
        summary.proBudgetYear,
        0,
      ),
    );
    const projectUsedBudget = normalizeNumber(
      firstMeaningful(
        mappedSummary.project_used_budget,
        rawBudget.usedBudget,
        summary.acceptanceAmount,
        summary.acceptTotalFeeNoTax,
        0,
      ),
    );
    const remainingBudget = normalizeNumber(
      firstMeaningful(
        mappedSummary.remainingBudget,
        mappedSummary.remaining_budget,
        Math.max((requestBudget || projectBudget) - projectUsedBudget, 0),
      ),
    );
    return {
      ...mappedSummary,
      project_budget: firstMeaningful(mappedSummary.project_budget, projectBudget),
      request_budget: firstMeaningful(mappedSummary.request_budget, requestBudget),
      project_budget_no_tax: firstMeaningful(mappedSummary.project_budget_no_tax, requestBudget),
      project_year_budget: firstMeaningful(mappedSummary.project_year_budget, projectYearBudget),
      project_used_budget: firstMeaningful(mappedSummary.project_used_budget, projectUsedBudget),
      remainingBudget: firstMeaningful(mappedSummary.remainingBudget, remainingBudget),
      remaining_budget: firstMeaningful(mappedSummary.remaining_budget, remainingBudget),
    };
  }, [documentPayload, summary]);
  const acceptanceInfoList = normalizeList(acceptance.info_list);
  const syntheticTaskOrders = useMemo(() => buildTaskOrders(documentPayload), [documentPayload]);
  const taskOrders = taskOrderItems.length ? taskOrderItems : syntheticTaskOrders;
  const selectedTaskOrderId = String(searchParams.get("taskOrderId") || "").trim();
  const selectedTaskOrder = useMemo(
    () => taskOrders.find((item) => String(item?.id || "").trim() === selectedTaskOrderId) || taskOrders[0] || null,
    [selectedTaskOrderId, taskOrders],
  );
  const selectedAcceptId = String(searchParams.get("acceptId") || "").trim();
  const selectedAcceptance = useMemo(
    () => acceptanceInfoList.find((item) => String(item?.acceptId || item?.id || "").trim() === selectedAcceptId) || null,
    [acceptanceInfoList, selectedAcceptId],
  );
  const effectiveCategory =
    category ||
    documentPayload?.resolved_category ||
    summary?.business_subcategory_name ||
    summary?.project_category_name ||
    summary?.project_type_name ||
    "";
  const acceptanceVisibilitySource = useMemo(() => {
    const hasDynamicTabs =
      normalizeList(acceptanceTabConfig?.sections).length
      || normalizeList(acceptanceTabConfig?.project_review_tabs).length
      || normalizeList(acceptanceTabConfig?.tam_tabs).length;
    return hasDynamicTabs ? acceptanceTabConfig : rules;
  }, [acceptanceTabConfig, rules]);
  const acceptanceVisibility = useMemo(
    () => buildAcceptanceVisibility(acceptanceVisibilitySource, effectiveCategory),
    [acceptanceVisibilitySource, effectiveCategory],
  );
  const hasExplicitAcceptanceProjectReviewTabs = normalizeList(acceptanceTabConfig?.project_review_tabs).length > 0;
  const acceptanceProjectReviewTabs = useMemo(() => {
    const visibleTabs = normalizeList(acceptanceVisibility.visibleProjectReviewTabs);
    if (hasExplicitAcceptanceProjectReviewTabs && visibleTabs.length) {
      return visibleTabs;
    }
    const filtered = visibleTabs.filter((tab) => ACCEPTANCE_PROJECT_REVIEW_TAB_KEYS.has(tab.key));
    return filtered.length ? filtered : ACCEPTANCE_PROJECT_REVIEW_TABS;
  }, [acceptanceVisibility.visibleProjectReviewTabs, hasExplicitAcceptanceProjectReviewTabs]);
  const projectReviewGoalGroups = useMemo(() => buildProjectReviewGoalGroups(documentPayload), [documentPayload]);
  const projectReviewSystemGroups = useMemo(() => buildProjectReviewSystemScopeGroups(documentPayload), [documentPayload]);
  const sectionDefinitions = viewerPhase === "acceptance"
    ? acceptanceVisibility.visibleSections
    : viewerPhase === TASK_ORDER_PHASE
      ? TASK_ORDER_SECTIONS
      : INITIATION_SECTIONS;
  const tabs =
    viewerPhase === "acceptance" && activeSection === "project_review"
      ? acceptanceProjectReviewTabs
      : viewerPhase === "acceptance" && activeSection === "tam_models"
        ? acceptanceVisibility.visibleTamTabs
        : SECTION_TABS[activeSection] || [];
  const activeTab = activeTabs[activeSection] || tabs[0]?.key || "";
  const projectBadges = buildProjectBadges(summary);
  const approvalDetailItems = useMemo(() => normalizeApprovalDetailItems(latestApproval), [latestApproval]);
  const debugIds = documentPayload?.debug_ids || {};
  const taskOrderView = useMemo(
    () => buildTaskOrderViewModel(selectedTaskOrder, taskOrderDetail, documentPayload),
    [documentPayload, selectedTaskOrder, taskOrderDetail],
  );
  const acceptanceTaskDrawerId = String(
    firstMeaningful(acceptanceTaskDrawerTask?.id, acceptanceTaskDrawerTask?.taskId, acceptanceTaskDrawerTask?.taskOrderId),
  ).trim();
  const acceptanceTaskDrawerView = useMemo(
    () => buildTaskOrderViewModel(acceptanceTaskDrawerTask, acceptanceTaskDrawerDetail, documentPayload),
    [acceptanceTaskDrawerDetail, acceptanceTaskDrawerTask, documentPayload],
  );
  const acceptanceContractDrawerIdentity = useMemo(
    () => resolveAcceptanceContractIdentity(acceptanceContractDrawerContract, { allowRowId: true }),
    [acceptanceContractDrawerContract],
  );
  const acceptanceContractDrawerView = useMemo(
    () => buildAcceptanceContractViewModel(acceptanceContractDrawerContract, acceptanceContractDrawerDetail, documentPayload),
    [acceptanceContractDrawerContract, acceptanceContractDrawerDetail, documentPayload],
  );
  const acceptanceDetailTaskRows = useMemo(
    () => filterByAcceptId(acceptance.task_acceptance_list),
    [acceptance.task_acceptance_list, selectedAcceptId],
  );
  const selectedAcceptanceDetailTask = useMemo(
    () => acceptanceDetailTaskRows.find((item) => String(item?.id || item?.taskId || "").trim() === acceptanceDetailTaskId) || acceptanceDetailTaskRows[0] || null,
    [acceptanceDetailTaskId, acceptanceDetailTaskRows],
  );
  const acceptanceDetailTaskView = useMemo(
    () => buildTaskOrderViewModel(selectedAcceptanceDetailTask, acceptanceDetailTaskDetail, documentPayload),
    [acceptanceDetailTaskDetail, documentPayload, selectedAcceptanceDetailTask],
  );
  const acceptanceDeliverableSummary = useMemo(
    () => filterByAcceptId(acceptance.deliverables)[0] || null,
    [acceptance.deliverables, selectedAcceptId],
  );
  const acceptanceStandardDeliverableRows = useMemo(
    () => buildAcceptanceStandardDeliverableRows(acceptance),
    [acceptance.standard_deliverables],
  );
  const acceptanceTaskDeliverableGroups = useMemo(
    () => buildAcceptanceTaskDeliverableGroups(
      selectedAcceptanceDetailTask,
      acceptanceDetailTaskView,
      documentPayload,
      acceptanceDeliverableSummary,
      acceptance.task_deliverables,
      acceptanceStandardDeliverableRows,
    ),
    [
      acceptance.task_deliverables,
      acceptanceDeliverableSummary,
      acceptanceDetailTaskView,
      acceptanceStandardDeliverableRows,
      documentPayload,
      selectedAcceptanceDetailTask,
    ],
  );
  const initiationProjectId = viewerPhase === "acceptance"
    ? String(debugIds.establishment_project_id || projectId)
    : String(projectId);
  const acceptanceProjectId = viewerPhase === "acceptance"
    ? String(debugIds.budget_project_id || projectId)
    : String(projectId);

  useEffect(() => {
    setApprovalDetailOpen(false);
  }, [latestApproval?.generated_at, latestApproval?.decision, projectId]);

  useEffect(() => {
    if (!["project_content", "project_review"].includes(activeSection) || !tabs.length) {
      return;
    }
    const currentTab = activeTabs[activeSection];
    const currentTabExists = tabs.some((tab) => tab.key === currentTab);
    const preferredTab =
      tabs.find((tab) => hasReviewTabContent(documentPayload, tab.key))?.key ||
      tabs[0]?.key ||
      "";
    if (preferredTab && (!currentTab || !currentTabExists)) {
      setActiveTabs((current) => ({ ...current, [activeSection]: preferredTab }));
    }
  }, [activeSection, activeTabs, documentPayload, tabs]);

  useEffect(() => {
    let alive = true;
    requestJson(`/api/rules?scene=${encodeURIComponent(scene)}`)
      .then((payload) => {
        if (!alive) {
          return;
        }
        setRules(payload);
        if (!category) {
          const firstCategory = payload?.categories?.[0]?.name || "";
          if (firstCategory) {
            setCategory(firstCategory);
          }
        }
      })
      .catch(() => {
        if (alive) {
          setRules(null);
        }
      });
    return () => {
      alive = false;
    };
  }, [scene]);

  useEffect(() => {
    if (scene !== "acceptance" || !projectId) {
      setAcceptanceTabConfig(null);
      return;
    }
    let alive = true;
    requestJson(`/api/projects/${encodeURIComponent(projectId)}/acceptance-tabs`)
      .then((payload) => {
        if (alive) {
          setAcceptanceTabConfig(payload);
        }
      })
      .catch(() => {
        if (alive) {
          setAcceptanceTabConfig(null);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, scene]);

  useEffect(() => {
    setActiveSection(viewerPhase === "acceptance" ? "acceptance_stage" : viewerPhase === TASK_ORDER_PHASE ? "basic_info" : "project_content");
  }, [viewerPhase]);

  useEffect(() => {
    if (scene !== "acceptance" || !selectedAcceptId) {
      return;
    }
    const exists = acceptanceInfoList.some((item) => String(item?.acceptId || item?.id || "").trim() === selectedAcceptId);
    if (!exists) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("acceptId");
      setSearchParams(nextParams, { replace: true });
    }
  }, [acceptanceInfoList, scene, searchParams, selectedAcceptId, setSearchParams]);

  useEffect(() => {
    if (viewerPhase !== "acceptance" || selectedAcceptId || !acceptanceInfoList.length) {
      return;
    }
    if (acceptanceInfoList.length === 1) {
      const nextAcceptId = String(acceptanceInfoList[0]?.acceptId || acceptanceInfoList[0]?.id || "").trim();
      if (nextAcceptId) {
        const nextParams = new URLSearchParams(searchParams);
        nextParams.set("acceptId", nextAcceptId);
        setSearchParams(nextParams, { replace: true });
      }
    }
  }, [acceptanceInfoList, searchParams, selectedAcceptId, setSearchParams, viewerPhase]);

  useEffect(() => {
    if (viewerPhase !== TASK_ORDER_PHASE) {
      setTaskOrderItems([]);
      setTaskOrderDetail(null);
      setTaskOrderError("");
      return;
    }
    let alive = true;
    setTaskOrderLoading(true);
    setTaskOrderError("");
    requestJson(`/api/projects/${encodeURIComponent(projectId)}/task-orders`)
      .then((payload) => {
        if (!alive) {
          return;
        }
        setTaskOrderItems(normalizeList(payload?.items));
      })
      .catch((loadError) => {
        if (alive) {
          setTaskOrderItems([]);
          setTaskOrderError(loadError.message || "加载任务单列表失败");
        }
      })
      .finally(() => {
        if (alive) {
          setTaskOrderLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, viewerPhase]);

  useEffect(() => {
    if (viewerPhase !== TASK_ORDER_PHASE || !taskOrders.length) {
      return;
    }
    const exists = taskOrders.some((item) => String(item?.id || "").trim() === selectedTaskOrderId);
    if (selectedTaskOrderId && !exists) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete("taskOrderId");
      setSearchParams(nextParams, { replace: true });
      return;
    }
    if (!selectedTaskOrderId) {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set("taskOrderId", String(taskOrders[0].id));
      setSearchParams(nextParams, { replace: true });
    }
  }, [searchParams, selectedTaskOrderId, setSearchParams, taskOrders, viewerPhase]);

  useEffect(() => {
    if (viewerPhase !== TASK_ORDER_PHASE || !selectedTaskOrder?.id) {
      setTaskOrderDetail(null);
      return;
    }
    let alive = true;
    setTaskOrderLoading(true);
    requestJson(
      `/api/task-orders/${encodeURIComponent(selectedTaskOrder.id)}/detail?project_id=${encodeURIComponent(projectId)}`,
    )
      .then((payload) => {
        if (alive) {
          setTaskOrderDetail(payload);
        }
      })
      .catch(() => {
        if (alive) {
          setTaskOrderDetail(null);
        }
      })
      .finally(() => {
        if (alive) {
          setTaskOrderLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, selectedTaskOrder?.id, viewerPhase]);

  useEffect(() => {
    if (!acceptanceTaskDrawerId) {
      setAcceptanceTaskDrawerDetail(null);
      setAcceptanceTaskDrawerError("");
      setAcceptanceTaskDrawerLoading(false);
      return;
    }
    let alive = true;
    setAcceptanceTaskDrawerDetail(null);
    setAcceptanceTaskDrawerLoading(true);
    setAcceptanceTaskDrawerError("");
    requestJson(
      `/api/task-orders/${encodeURIComponent(acceptanceTaskDrawerId)}/detail?project_id=${encodeURIComponent(initiationProjectId || projectId)}`,
    )
      .then((payload) => {
        if (alive) {
          setAcceptanceTaskDrawerDetail(payload);
        }
      })
      .catch((loadError) => {
        if (alive) {
          setAcceptanceTaskDrawerDetail(null);
          setAcceptanceTaskDrawerError(loadError.message || "加载任务单详情失败");
        }
      })
      .finally(() => {
        if (alive) {
          setAcceptanceTaskDrawerLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [acceptanceTaskDrawerId, initiationProjectId, projectId]);

  useEffect(() => {
    if (!acceptanceTaskDrawerId) {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setAcceptanceTaskDrawerTask(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [acceptanceTaskDrawerId]);

  useEffect(() => {
    const { contractId, contractNumber } = acceptanceContractDrawerIdentity;
    if (!contractId && !contractNumber) {
      setAcceptanceContractDrawerDetail(null);
      setAcceptanceContractDrawerError("");
      setAcceptanceContractDrawerLoading(false);
      return;
    }
    let alive = true;
    const query = new URLSearchParams();
    if (contractNumber) {
      query.set("contract_number", contractNumber);
    }
    setAcceptanceContractDrawerDetail(null);
    setAcceptanceContractDrawerLoading(true);
    setAcceptanceContractDrawerError("");
    requestJson(
      `/api/contracts/${encodeURIComponent(contractId || contractNumber)}/detail${query.toString() ? `?${query.toString()}` : ""}`,
    )
      .then((payload) => {
        if (alive) {
          setAcceptanceContractDrawerDetail(payload);
        }
      })
      .catch((loadError) => {
        if (alive) {
          setAcceptanceContractDrawerDetail(null);
          setAcceptanceContractDrawerError(loadError.message || "加载合同明细失败");
        }
      })
      .finally(() => {
        if (alive) {
          setAcceptanceContractDrawerLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [acceptanceContractDrawerIdentity]);

  useEffect(() => {
    if (!acceptanceTaskDrawerId && !acceptanceContractDrawerContract && !deliverablesDialogOpen) {
      return undefined;
    }
    document.body.classList.add("viewer-modal-open");
    return () => {
      document.body.classList.remove("viewer-modal-open");
    };
  }, [acceptanceContractDrawerContract, acceptanceTaskDrawerId, deliverablesDialogOpen]);

  useEffect(() => {
    if (!deliverablesDialogOpen) {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setDeliverablesDialogOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [deliverablesDialogOpen]);

  useEffect(() => {
    if (!acceptanceContractDrawerContract) {
      return undefined;
    }
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setAcceptanceContractDrawerContract(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [acceptanceContractDrawerContract]);

  useEffect(() => {
    if (!acceptanceDetailTaskRows.length) {
      setAcceptanceDetailTaskId("");
      setAcceptanceDetailTaskDetail(null);
      setAcceptanceDetailTaskError("");
      setAcceptanceDetailTaskLoading(false);
      return;
    }
    const exists = acceptanceDetailTaskRows.some((item) => String(item?.id || item?.taskId || "").trim() === acceptanceDetailTaskId);
    if (!acceptanceDetailTaskId || !exists) {
      setAcceptanceDetailTaskId(String(acceptanceDetailTaskRows[0]?.id || acceptanceDetailTaskRows[0]?.taskId || ""));
    }
  }, [acceptanceDetailTaskId, acceptanceDetailTaskRows]);

  useEffect(() => {
    const selectedTaskId = String(selectedAcceptanceDetailTask?.id || selectedAcceptanceDetailTask?.taskId || "").trim();
    if (!selectedTaskId) {
      setAcceptanceDetailTaskDetail(null);
      setAcceptanceDetailTaskError("");
      setAcceptanceDetailTaskLoading(false);
      return;
    }
    let alive = true;
    setAcceptanceDetailTaskDetail(null);
    setAcceptanceDetailTaskLoading(true);
    setAcceptanceDetailTaskError("");
    requestJson(
      `/api/task-orders/${encodeURIComponent(selectedTaskId)}/detail?project_id=${encodeURIComponent(initiationProjectId || projectId)}`,
    )
      .then((payload) => {
        if (alive) {
          setAcceptanceDetailTaskDetail(payload);
        }
      })
      .catch((loadError) => {
        if (alive) {
          setAcceptanceDetailTaskDetail(null);
          setAcceptanceDetailTaskError(loadError.message || "加载任务单验收明细失败");
        }
      })
      .finally(() => {
        if (alive) {
          setAcceptanceDetailTaskLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [initiationProjectId, projectId, selectedAcceptanceDetailTask]);

  useEffect(() => {
    if (!sectionDefinitions.some((item) => item.key === activeSection)) {
      setActiveSection(
        sectionDefinitions[0]?.key
          || (viewerPhase === "acceptance" ? "project_review" : viewerPhase === TASK_ORDER_PHASE ? "basic_info" : "project_content"),
      );
    }
  }, [activeSection, sectionDefinitions, viewerPhase]);

  useEffect(() => {
    if (!tabs.length) {
      return;
    }
    if (!tabs.some((tab) => tab.key === activeTab)) {
      setActiveTabs((current) => ({ ...current, [activeSection]: tabs[0]?.key || "" }));
    }
  }, [activeSection, activeTab, tabs]);

  useEffect(() => {
    let alive = true;
    const categoryQuery = category ? `&category=${encodeURIComponent(category)}` : "";
    const refreshQuery = scene === "acceptance" ? "&refresh=true" : "";
    setLoading(true);
    setError("");
    setArchitecturePayload(null);
    Promise.all([
      requestJson(
        `/api/projects/${encodeURIComponent(projectId)}/document?scene=${encodeURIComponent(scene)}${categoryQuery}${refreshQuery}&include_architecture_reviews=false`,
      ),
      requestJson(`/api/projects/${encodeURIComponent(projectId)}/latest-approval?scene=${encodeURIComponent(scene)}${categoryQuery}`).catch(() => null),
    ])
      .then(([documentResult, approvalResult]) => {
        if (!alive) {
          return;
        }
        setDocumentPayload(documentResult);
        setLatestApproval(approvalResult?.result || null);
        if (documentResult?.resolved_category && documentResult.resolved_category !== category) {
          setCategory(documentResult.resolved_category);
        }
      })
      .catch((fetchError) => {
        if (alive) {
          setError(fetchError.message || "加载项目详情失败");
          setDocumentPayload(null);
          setArchitecturePayload(null);
        }
      })
      .finally(() => {
        if (alive) {
          setLoading(false);
        }
      });
    return () => {
      alive = false;
    };
  }, [projectId, scene, category]);

  useEffect(() => {
    if (activeSection !== "architecture_review" || architecturePayload) {
      return undefined;
    }
    let alive = true;
    const categoryQuery = category ? `&category=${encodeURIComponent(category)}` : "";
    requestJson(`/api/projects/${encodeURIComponent(projectId)}/architecture-reviews?scene=${encodeURIComponent(scene)}${categoryQuery}`)
      .then((payload) => {
        if (alive) {
          setArchitecturePayload(payload);
        }
      })
      .catch(() => {
        if (alive) {
          setArchitecturePayload({ groups: [] });
        }
      });
    return () => {
      alive = false;
    };
  }, [activeSection, architecturePayload, category, projectId, scene]);

  const reviewGroups = useMemo(
    () => normalizeList(architecturePayload?.groups || documentPayload?.architecture_review_details),
    [architecturePayload, documentPayload],
  );

  async function runApproval() {
    try {
      setApprovalBusy(true);
      setApprovalMessage("正在执行远程审批...");
      const result = await requestJson("/api/approve/remote-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId, category, scene }),
      });
      setLatestApproval(result);
      setApprovalMessage(result.summary || result.decision || "审批完成");
    } catch (runError) {
      setApprovalMessage(runError.message || "审批执行失败");
    } finally {
      setApprovalBusy(false);
    }
  }

  function updateTaskOrderId(nextTaskOrderId) {
    const nextParams = new URLSearchParams(searchParams);
    if (nextTaskOrderId) {
      nextParams.set("taskOrderId", String(nextTaskOrderId));
      nextParams.set("scene", TASK_ORDER_PHASE);
      nextParams.delete("phase");
      nextParams.delete("acceptId");
    } else {
      nextParams.delete("taskOrderId");
    }
    setSearchParams(nextParams, { replace: false });
  }

  function updateAcceptId(nextAcceptId) {
    const nextParams = new URLSearchParams(searchParams);
    if (nextAcceptId) {
      nextParams.set("acceptId", String(nextAcceptId));
    } else {
      nextParams.delete("acceptId");
    }
    setSearchParams(nextParams, { replace: false });
  }

  function filterByAcceptId(rows) {
    const items = normalizeList(rows);
    if (!selectedAcceptId) {
      return items;
    }
    const filtered = items.filter((item) => {
      if (!item || typeof item !== "object") {
        return false;
      }
      const rowAcceptId = String(item.acceptId || item.acceptid || item.accept_id || item.id || "").trim();
      return !rowAcceptId || rowAcceptId === selectedAcceptId;
    });
    return filtered;
  }

  function renderTaskOrderOverview() {
    const budgetOverview = taskOrderView?.budget_overview || {};
    const ownership = taskOrderView?.project_ownership || {};
    const classification = taskOrderView?.classification || {};
    return (
      <section className="task-order-overview-grid">
        <article className="card task-order-overview-card task-order-overview-card-dark">
          <div className="task-order-overview-head">
            <span className="task-order-overview-icon" aria-hidden="true">◉</span>
            <h2>项目所属</h2>
          </div>
          <DefinitionGrid
            items={[
              { label: "项目编码", value: ownership.project_code },
              { label: "项目经理", value: ownership.project_manager },
              { label: "业务部门", value: ownership.department_name },
              { label: "归属领域", value: ownership.domain_name },
            ]}
          />
        </article>
        <article className="card task-order-overview-card task-order-overview-card-soft">
          <div className="task-order-overview-head">
            <span className="task-order-overview-icon" aria-hidden="true">◫</span>
            <h2>项目分类</h2>
          </div>
          <DefinitionGrid
            items={[
              { label: "项目类别", value: classification.project_category_name },
              { label: "业务类别", value: classification.business_category_name },
              { label: "业务子类", value: classification.business_subcategory_name },
              { label: "项目等级", value: classification.project_level_name },
            ]}
          />
        </article>
        <article className="card task-order-overview-card task-order-overview-card-budget">
          <div className="task-order-overview-head">
            <span className="task-order-overview-icon" aria-hidden="true">◩</span>
            <h2>项目预算（不含税）</h2>
          </div>
          <DefinitionGrid
            items={[
              { label: "项目预算（元）", value: formatCurrency(budgetOverview.project_budget) },
              { label: "项目年度预算（元）", value: formatCurrency(budgetOverview.project_year_budget) },
              { label: "项目占用预算（元）", value: formatCurrency(budgetOverview.project_used_budget) },
              { label: "项目剩余预算（元）", value: formatCurrency(budgetOverview.project_remaining_budget) },
            ]}
          />
        </article>
      </section>
    );
  }

  function renderOverview() {
    if (viewerPhase === "acceptance") {
      const currentAcceptance = selectedAcceptance || acceptanceInfoList[0] || null;
      const projectBudgetNoTax = normalizeNumber(
        firstMeaningful(
          summary.applyBudget,
          summary.applyTotalBudget,
          acceptanceBudgetSummary.request_budget,
          acceptanceBudgetSummary.project_budget_no_tax,
          acceptanceBudgetSummary.proBudget,
          0,
        ),
      );
      const currentAcceptanceAmountNoTax = normalizeNumber(
        firstMeaningful(
          currentAcceptance?.acceptTotalFeeNoTax,
          currentAcceptance?.acceptTotalFee,
          acceptance?.acceptanceAmount,
          summary.acceptanceAmount,
          acceptance?.acceptTotalFeeNoTax,
          0,
        ),
      );
      const accumulatedAcceptedAmountNoTax = 0;
      const remainingBudgetNoTax = Math.max(projectBudgetNoTax - currentAcceptanceAmountNoTax, 0);
      const acceptanceBudget = {
        projectBudgetNoTax,
        accumulatedAcceptedAmountNoTax,
        currentAcceptanceAmountNoTax,
        remainingBudgetNoTax,
      };
      return (
        <section className="acceptance-overview-grid">
          <article className="card acceptance-overview-card acceptance-overview-card-dark">
            <div className="acceptance-overview-head">
              <span className="acceptance-overview-icon" aria-hidden="true">▣</span>
              <h2>项目所属</h2>
            </div>
            <DefinitionGrid
              items={[
                { label: "项目编码", value: summary.project_code },
                { label: "项目经理", value: summary.project_manager_name },
                { label: "业务部门", value: summary.department_name },
                { label: "归属领域", value: summary.domain_name },
              ]}
            />
          </article>
          <article className="card acceptance-overview-card acceptance-overview-card-soft">
            <div className="acceptance-overview-head">
              <span className="acceptance-overview-icon" aria-hidden="true">◫</span>
              <h2>项目分类</h2>
            </div>
            <DefinitionGrid
              items={[
                { label: "业务类别", value: summary.business_category_name },
                { label: "项目类别", value: summary.project_type_name || summary.project_category_name },
                { label: "业务子类", value: summary.business_subcategory_name },
                { label: "项目等级", value: summary.project_level_name },
              ]}
            />
          </article>
          <article className="card acceptance-overview-card acceptance-overview-card-budget">
            <div className="acceptance-overview-head">
              <span className="acceptance-overview-icon" aria-hidden="true">◩</span>
              <h2>项目预算</h2>
            </div>
            <DefinitionGrid
              items={[
                { label: "申请项目预算(元/不含税)", value: formatCurrency(acceptanceBudget.projectBudgetNoTax) },
                { label: "累计验收金额(元/不含税)", value: formatCurrencyAllowZero(acceptanceBudget.accumulatedAcceptedAmountNoTax) },
                { label: "申请验收金额(元/不含税)", value: formatCurrency(acceptanceBudget.currentAcceptanceAmountNoTax) },
                { label: "剩余金额(元/不含税)", value: formatCurrency(acceptanceBudget.remainingBudgetNoTax) },
              ]}
            />
          </article>
        </section>
      );
    }
    if (viewerPhase === TASK_ORDER_PHASE) {
      return renderTaskOrderOverview();
    }
    return (
      <section className="viewer-card-grid viewer-card-grid-overview">
        <article className="card viewer-card dark">
          <p className="panel-label">Ownership</p>
          <h2>项目归属</h2>
          <DefinitionGrid
            items={[
              { label: "项目编码", value: summary.project_code },
              { label: "项目经理", value: summary.project_manager_name },
              { label: "业务部门", value: summary.department_name },
              { label: "领域", value: summary.domain_name },
            ]}
          />
        </article>
        <article className="card viewer-card viewer-card-soft">
          <p className="panel-label">Classification</p>
          <h2>项目分类</h2>
          <DefinitionGrid
            items={[
              { label: "项目类型", value: summary.project_type_name },
              { label: "业务分类", value: summary.business_category_name },
              { label: "业务子类", value: summary.business_subcategory_name },
              { label: "项目状态", value: summary.project_status_name },
            ]}
          />
        </article>
        <article className="card viewer-card viewer-budget-card">
          <p className="panel-label">Budget</p>
          <h2>项目预算</h2>
          <DefinitionGrid
            items={[
              { label: "项目预算（元）", value: formatCurrency(firstMeaningful(acceptanceBudgetSummary.project_budget, acceptanceBudgetSummary.request_budget)) },
              { label: "申请项目预算(元/不含税)", value: formatCurrency(firstMeaningful(acceptanceBudgetSummary.request_budget, acceptanceBudgetSummary.project_budget_no_tax)) },
              { label: "项目年度", value: formatValue(summary.budget_year) },
              { label: "剩余金额(元/不含税)", value: formatCurrency(firstMeaningful(acceptanceBudgetSummary.remainingBudget, acceptanceBudgetSummary.remaining_budget)) },
            ]}
          />
        </article>
      </section>
    );
  }

  function renderProjectReviewGoalTabs() {
    if (!projectReviewGoalGroups.length) {
      return null;
    }
    const activeGoalId = projectReviewGoalGroups.some((item) => item.id === activeProjectReviewGoalId)
      ? activeProjectReviewGoalId
      : projectReviewGoalGroups[0]?.id;
    return (
      <div className="viewer-scope-goal-tabs acceptance-project-review-goal-tabs">
        {projectReviewGoalGroups.map((group) => {
          const isActive = group.id === activeGoalId;
          return (
            <button
              key={group.id}
              className={`viewer-scope-goal-tab ${isActive ? "active" : ""}`}
              type="button"
              onClick={() => setActiveProjectReviewGoalId(group.id)}
            >
              {group.buttonLabel}
              {group.statusLabel ? <span className="acceptance-project-review-goal-status">{group.statusLabel}</span> : null}
            </button>
          );
        })}
      </div>
    );
  }

  function renderProjectReviewImageList(images, emptyText = "暂无图片") {
    const normalizedImages = normalizeList(images).map(imageUrlOf).filter(Boolean);
    if (!normalizedImages.length) {
      return <div className="acceptance-project-review-image-empty">{emptyText}</div>;
    }
    return (
      <div className="acceptance-project-review-image-list">
        {normalizedImages.map((image, index) => (
          <a key={`${image}-${index}`} href={image} target="_blank" rel="noreferrer" className="acceptance-project-review-image-card">
            <img src={image} alt={`project-review-${index + 1}`} className="acceptance-project-review-image" />
          </a>
        ))}
      </div>
    );
  }

  function renderProjectReviewUploadBlocks(section, options = {}) {
    const blocks = normalizeProjectReviewBlocks(section);
    if (!blocks.length) {
      return <p className="viewer-empty">{options.emptyText || "暂无项目回顾数据"}</p>;
    }
    return (
      <div className="acceptance-project-review-stack">
        {blocks.map((block, index) => (
          <section key={block.id || index} className="acceptance-project-review-model">
            {options.showModelLabel ? <div className="acceptance-project-review-model-label">模型</div> : null}
            <div className="acceptance-project-review-split">
              <div className="acceptance-project-review-fields">
                <label className="acceptance-project-review-field">
                  <span>{options.titleLabel || "标题"}</span>
                  <div className="acceptance-project-review-box">{formatValue(block.title)}</div>
                </label>
                <label className="acceptance-project-review-field">
                  <span>{options.contentLabel || "内容"}</span>
                  <div className="acceptance-project-review-box acceptance-project-review-box-large">{formatValue(block.content)}</div>
                </label>
              </div>
              <div className="acceptance-project-review-media">
                <div className="acceptance-project-review-media-label">{options.imageLabel || "添加图片"}</div>
                {renderProjectReviewImageList(block.images, options.imageEmptyText)}
              </div>
            </div>
          </section>
        ))}
      </div>
    );
  }

  function renderAcceptanceProjectReview() {
    const activeGoalGroup = projectReviewGoalGroups.find((item) => item.id === activeProjectReviewGoalId) || projectReviewGoalGroups[0] || null;
    const scopeRows = normalizeList(documentPayload?.scope?.content_list);
    const annualModelRows = normalizeList(documentPayload?.scope?.business_processes);
    const shouldUseMachineScopeTable = looksLikeMachineScopeRows(scopeRows);
    const shouldUseConfidentialScopeTable = matchesCategoryKeyword(effectiveCategory, CONFIDENTIAL_SCOPE_CATEGORY_KEYWORDS);
    const shouldUseNonResearchToolAnnualModel = matchesCategoryKeyword(
      effectiveCategory,
      NON_RESEARCH_TOOL_ANNUAL_MODEL_CATEGORY_KEYWORDS,
    );
    const standardScopeRows = normalizeStandardScopeRows(scopeRows);
    const softwareScopeRows = normalizeSoftwareScopeRows(scopeRows);
    const annualModelProcessRows = buildAnnualModelProcessRows(documentPayload);
    const annualModelSystemRows = buildAnnualModelSystemRows(documentPayload);
    const relatedProducts = normalizeList(documentPayload?.okr?.related_products)
      .map((item) => firstMeaningful(item?.productName, item?.name, item?.label))
      .filter(Boolean);
    const keyResults = normalizeList(documentPayload?.okr?.key_results)
      .map((item) => firstMeaningful(item?.keyResult, item?.krName, item?.name, item?.title, item?.description))
      .filter(Boolean);
    const normalizedSearch = String(projectReviewSystemSearch || "").trim().toLowerCase();
    const visibleSystemGroups = projectReviewSystemGroups.filter((group) => {
      if (!normalizedSearch) {
        return true;
      }
      return String(group.name || "").toLowerCase().includes(normalizedSearch) || group.items.some((item) =>
        [item.code, item.name, item.type, item.owner].some((value) => String(value || "").toLowerCase().includes(normalizedSearch)),
      );
    });
    const activeSystemGroup = projectReviewSystemGroups.find((group) => group.key === activeProjectReviewSystemKey)
      || visibleSystemGroups[0]
      || projectReviewSystemGroups[0]
      || null;

    if (activeTab === "background") {
      return renderProjectReviewUploadBlocks(documentPayload?.project_content?.background, {
        titleLabel: "标题",
        contentLabel: "内容",
        imageLabel: "添加图片",
        emptyText: "暂无项目背景数据",
      });
    }

    if (activeTab === "target") {
      return renderProjectReviewUploadBlocks(documentPayload?.project_content?.target, {
        showModelLabel: true,
        titleLabel: "目标标题",
        contentLabel: "目标内容",
        imageLabel: "添加图片",
        emptyText: "暂无项目目标数据",
      });
    }

    if (activeTab === "okr") {
      return (
        <div className="acceptance-project-review-okr-layout">
          <aside className="acceptance-project-review-side">
            <label className="acceptance-project-review-side-field">
              <span>产品链</span>
              <div className="acceptance-project-review-side-box">{formatValue(documentPayload?.okr?.product_chain)}</div>
            </label>
            <div className="acceptance-project-review-side-field">
              <span>已关联产品</span>
              <div className="acceptance-project-review-related-list">
                {(relatedProducts.length ? relatedProducts : activeGoalGroup?.productNames || []).map((item, index) => (
                  <div key={`${item}-${index}`} className="acceptance-project-review-related-item">
                    {item}
                  </div>
                ))}
                {!(relatedProducts.length || activeGoalGroup?.productNames?.length) ? (
                  <div className="acceptance-project-review-image-empty">暂无关联产品</div>
                ) : null}
              </div>
            </div>
          </aside>
          <div className="acceptance-project-review-main">
            {renderProjectReviewGoalTabs()}
            <article className="acceptance-project-review-panel">
              <div className="acceptance-project-review-panel-title">项目目标</div>
              <div className="acceptance-project-review-form-grid">
                <label className="acceptance-project-review-field acceptance-project-review-field-wide">
                  <span>项目目标</span>
                  <div className="acceptance-project-review-box">{formatValue(documentPayload?.okr?.objective)}</div>
                </label>
                <label className="acceptance-project-review-field">
                  <span>关联战队OKR</span>
                  <div className="acceptance-project-review-box">{formatValue(documentPayload?.okr?.squad_okr)}</div>
                </label>
                <label className="acceptance-project-review-field">
                  <span>时间范围</span>
                  <div className="acceptance-project-review-box">
                    {`${formatValue(firstMeaningful(documentPayload?.okr?.time_range?.start, "-"))} 至 ${formatValue(firstMeaningful(documentPayload?.okr?.time_range?.end, "-"))}`}
                  </div>
                </label>
              </div>
              <div className="acceptance-project-review-kr-board">
                <div className="acceptance-project-review-panel-subtitle">关键结果 KR</div>
                <div className="acceptance-project-review-kr-list">
                  {keyResults.length ? keyResults.map((item, index) => (
                    <div key={`${item}-${index}`} className="acceptance-project-review-kr-item">
                      <div className="acceptance-project-review-kr-index">{index + 1}</div>
                      <div className="acceptance-project-review-box">{item}</div>
                    </div>
                  )) : <div className="acceptance-project-review-image-empty">暂无 KR 数据</div>}
                </div>
              </div>
            </article>
          </div>
        </div>
      );
    }

    if (activeTab === "scope") {
      if (shouldUseNonResearchToolAnnualModel) {
        return (
          <article className="acceptance-project-review-panel">
            <div className="acceptance-project-review-panel-title">项目范围</div>
            {renderSoftwareScopeTable(softwareScopeRows)}
          </article>
        );
      }
      if (shouldUseConfidentialScopeTable) {
        return (
          <article className="acceptance-project-review-panel">
            <div className="acceptance-project-review-panel-title">项目范围</div>
            {renderStandardScopeTable(standardScopeRows, summary.budget_year)}
          </article>
        );
      }
      if (shouldUseMachineScopeTable) {
        return (
          <article className="acceptance-project-review-panel">
            <div className="acceptance-project-review-panel-title">项目范围</div>
            <MachineScopeTable rows={scopeRows} budgetYear={summary.budget_year} emptyText="暂无项目范围数据" />
          </article>
        );
      }
      const rows = normalizeList(activeGoalGroup?.rows);
      return (
        <div className="acceptance-project-review-stack">
          {renderProjectReviewGoalTabs()}
          <article className="acceptance-project-review-panel">
            <div className="acceptance-project-review-scope-title">{activeGoalGroup?.buttonLabel || "项目目标"}</div>
            <div className="acceptance-project-review-scope-meta">
              <span>业务流程总数: {activeGoalGroup?.processCount || 0}</span>
              <span>业务单元总数: {activeGoalGroup?.businessUnitCount || 0}</span>
            </div>
            <div className="acceptance-project-review-table-wrap">
              <table className="acceptance-project-review-table">
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
                  {rows.length ? rows.map((row, index) => (
                    <tr key={row.id || `${index}`}>
                      <td>{index + 1}</td>
                      <td>{formatValue(firstMeaningful(row?.productName, row?.productFullName))}</td>
                      <td>{formatValue(firstMeaningful(row?.code, row?.processCode))}</td>
                      <td>{formatValue(firstMeaningful(row?.name, row?.processName))}</td>
                      <td>{formatValue(firstMeaningful(row?.roleName, row?.businessRoleName))}</td>
                      <td>{formatValue(firstMeaningful(row?.busNum, row?.businessUnitCount))}</td>
                      <td>{formatValue(firstMeaningful(row?.type, row?.categoryName))}</td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan="7" className="viewer-empty-cell">暂无项目范围数据</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        </div>
      );
    }

    if (activeTab === "system_scope") {
      return (
        <div className="acceptance-project-review-system-layout">
          <aside className="acceptance-project-review-system-side">
            <div className="acceptance-project-review-system-head">选择关联系统</div>
            <div className="acceptance-project-review-system-search">
              <input
                type="text"
                value={projectReviewSystemSearch}
                onChange={(event) => setProjectReviewSystemSearch(event.target.value)}
                placeholder="请输入关联系统"
              />
              <button type="button" className="ghost-button">搜索</button>
            </div>
            <div className="acceptance-project-review-system-list">
              {(visibleSystemGroups.length ? visibleSystemGroups : projectReviewSystemGroups).map((group) => {
                const isActive = group.key === (activeSystemGroup?.key || "");
                return (
                  <button
                    key={group.key}
                    className={`acceptance-project-review-system-item ${isActive ? "active" : ""}`}
                    type="button"
                    onClick={() => setActiveProjectReviewSystemKey(group.key)}
                  >
                    <span>{group.name}</span>
                    <span className="acceptance-project-review-system-count">{group.items.length}</span>
                  </button>
                );
              })}
              {!projectReviewSystemGroups.length ? <div className="acceptance-project-review-image-empty">暂无关联系统</div> : null}
            </div>
          </aside>
          <section className="acceptance-project-review-system-main">
            <div className="acceptance-project-review-system-tabs">
              {projectReviewSystemGroups.map((group) => (
                <button
                  key={group.key}
                  type="button"
                  className={`acceptance-project-review-system-tab ${group.key === (activeSystemGroup?.key || "") ? "active" : ""}`}
                  onClick={() => setActiveProjectReviewSystemKey(group.key)}
                >
                  {group.name}
                </button>
              ))}
            </div>
            <div className="acceptance-project-review-system-caption">关联系统微应用/微服务列表</div>
            <div className="acceptance-project-review-table-wrap">
              <table className="acceptance-project-review-table">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>编号</th>
                    <th>名称</th>
                    <th>类型</th>
                    <th>负责人</th>
                  </tr>
                </thead>
                <tbody>
                  {normalizeList(activeSystemGroup?.items).length ? normalizeList(activeSystemGroup?.items).map((item, index) => (
                    <tr key={item.id || `${index}`}>
                      <td>{index + 1}</td>
                      <td>{formatValue(item.code)}</td>
                      <td>{formatValue(item.name)}</td>
                      <td>{formatValue(item.type)}</td>
                      <td>{formatValue(item.owner)}</td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan="5" className="viewer-empty-cell">暂无系统范围数据</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      );
    }

    if (activeTab === "panorama") {
      return renderProjectReviewUploadBlocks(documentPayload?.project_content?.panorama, {
        showModelLabel: true,
        titleLabel: "全景标题",
        contentLabel: "全景内容",
        imageLabel: "添加图片",
        emptyText: "暂无业务全景图数据",
      });
    }

    if (activeTab === "annual_model") {
      if (shouldUseNonResearchToolAnnualModel) {
        return renderAnnualModelAssociationTables(annualModelProcessRows, annualModelSystemRows);
      }
      if (hasUploadSectionContent(documentPayload?.project_content?.annual_model)) {
        return renderProjectReviewUploadBlocks(documentPayload?.project_content?.annual_model, {
          showModelLabel: true,
          titleLabel: "模型标题",
          contentLabel: "模型内容",
          imageLabel: "添加图片",
          emptyText: "暂无年度管理模型数据",
        });
      }
      return (
        <article className="acceptance-project-review-panel">
          <div className="acceptance-project-review-panel-title">年度管理模型</div>
          <DataTable
            rows={annualModelRows}
            preferredKeys={["name", "code", "level", "processVersion", "type", "futureTime", "actualTime"]}
            emptyText="暂无年度管理模型数据"
          />
        </article>
      );
    }

    if (activeTab === "solution") {
      return renderProjectReviewUploadBlocks(documentPayload?.project_content?.solution, {
        showModelLabel: true,
        titleLabel: "项目方案",
        contentLabel: "方案内容",
        imageLabel: "添加图片",
        emptyText: "暂无项目方案数据",
      });
    }

    if (activeTab === "acceptance_plan") {
      return renderProjectReviewUploadBlocks(documentPayload?.project_content?.acceptance_plan, {
        showModelLabel: true,
        titleLabel: "方案标题",
        contentLabel: "方案内容",
        imageLabel: "添加图片",
        emptyText: "暂无验收方案数据",
      });
    }

    return <p className="viewer-empty">暂无项目回顾数据</p>;
  }

  function renderProjectContent(sectionKey) {
    if (sectionKey === "project_review") {
      return renderAcceptanceProjectReview();
    }
    if (activeTab === "okr") {
      return (
        <article className="card viewer-card-soft">
          <h3>项目OKR</h3>
          <DefinitionGrid
            items={[
              { label: "产品链", value: documentPayload?.okr?.product_chain },
              { label: "目标O", value: documentPayload?.okr?.objective },
              { label: "团队OKR", value: documentPayload?.okr?.squad_okr },
              { label: "关联产品", value: documentPayload?.okr?.related_products },
              { label: "时间范围", value: documentPayload?.okr?.time_range },
              { label: "关键结果KR", value: documentPayload?.okr?.key_results },
            ]}
          />
        </article>
      );
    }
    if (activeTab === "scope") {
      return (
        <article className="card viewer-card-soft">
          <h3>范围明细</h3>
          <MachineScopeTable rows={documentPayload?.scope?.content_list} budgetYear={summary.budget_year} />
        </article>
      );
    }
    if (activeTab === "system_scope") {
      return (
        <div className="stack-md">
          <article className="card viewer-card-soft">
            <h3>系统范围</h3>
            <DataTable
              rows={documentPayload?.scope?.microservices}
              preferredKeys={["name", "code", "systemName", "applicationSystemName", "type", "categoryName"]}
              emptyText="暂无系统范围数据"
            />
          </article>
          <article className="card viewer-card-soft">
            <h3>微应用</h3>
            <DataTable
              rows={documentPayload?.scope?.microapps}
              preferredKeys={["name", "code", "systemName", "applicationSystemName", "type", "categoryName"]}
              emptyText="暂无微应用数据"
            />
          </article>
        </div>
      );
    }
    if (activeTab === "annual_model") {
      return (
        <article className="card viewer-card-soft">
          <h3>年度管理模型</h3>
          <DataTable
            rows={documentPayload?.scope?.business_processes}
            preferredKeys={["name", "code", "level", "processVersion", "type", "futureTime", "actualTime"]}
            emptyText="暂无年度管理模型数据"
          />
        </article>
      );
    }
    return <UploadSection section={documentPayload?.project_content?.[activeTab]} emptyText={`${sectionKey === "project_review" ? "项目回顾" : "项目内容"}暂无数据`} />;
  }

  function renderProjectValue() {
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <h3>价值说明</h3>
          <p>{documentPayload?.project_value || "暂无项目价值说明"}</p>
        </article>
      </div>
    );
  }

  function renderTamModels() {
    return <TamModelBoard documentPayload={documentPayload} activeTab={activeTab} />;
  }

  function renderOrganization() {
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <h3>成员信息</h3>
          <DataTable rows={documentPayload?.organization?.members} preferredKeys={["name", "role", "department", "team", "phone"]} emptyText="暂无组织成员" />
        </article>
        <article className="card viewer-card-soft">
          <h3>团队信息</h3>
          <DataTable rows={documentPayload?.organization?.teams} preferredKeys={["teamName", "leader", "memberCount", "partyLabel"]} emptyText="暂无团队数据" />
        </article>
      </div>
    );
  }

  function renderMilestones() {
    const value = documentPayload?.milestones?.[activeTab];
    if (Array.isArray(value)) {
      return <DataTable rows={value} emptyText="暂无里程碑数据" />;
    }
    if (value && typeof value === "object") {
      return <DefinitionGrid items={Object.entries(value).map(([label, fieldValue]) => ({ label, value: fieldValue }))} />;
    }
    return <p className="viewer-empty">暂无里程碑数据</p>;
  }

  function renderBudget() {
    if (activeTab === "summary") {
      return <DefinitionGrid items={Object.entries(documentPayload?.budget?.summary || {}).map(([label, value]) => ({ label, value }))} />;
    }
    return <DataTable rows={documentPayload?.budget?.cost_items} preferredKeys={["costTypeName", "costName", "amount", "taxIncludedAmount", "remark"]} emptyText="暂无预算明细" />;
  }

  function renderCostChange() {
    if (activeTab === "history") {
      return <DataTable rows={documentPayload?.cost_change?.history_items} preferredKeys={["projectName", "projectCode", "totalCost", "status"]} emptyText="暂无历史投入" />;
    }
    return (
      <article className="card viewer-card-soft">
        <h3>变化说明</h3>
        <p>{documentPayload?.cost_change?.reason || "暂无变化说明"}</p>
      </article>
    );
  }

  function renderTaskOrderBasicInfo() {
    const basicInfo = taskOrderView?.basic_info || {};
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft task-order-form-card">
          <div className="section-head">
            <div>
              <h3>基本信息</h3>
            </div>
          </div>
          <div className="task-order-form-grid">
            {[
              { label: "任务单名称", value: basicInfo.task_name, wide: true },
              { label: "任务单编号", value: basicInfo.task_no },
              { label: "开始时间", value: basicInfo.start_date },
              { label: "结束时间", value: basicInfo.end_date },
              { label: "供应商", value: basicInfo.supplier_name },
              { label: "合同名称", value: basicInfo.contract_name },
              { label: "合同编号", value: basicInfo.contract_no },
            ].map((item) => (
              <div key={item.label} className={`task-order-form-item ${item.wide ? "wide" : ""}`}>
                <span className="task-order-form-label">{item.label}</span>
                <div className="task-order-form-value">{formatValue(item.value)}</div>
              </div>
            ))}
          </div>
        </article>
        <article className="card viewer-card-soft">
          <h3>关联目标</h3>
          {normalizeList(basicInfo.target_list).length ? (
            <div className="viewer-tag-grid">
              {normalizeList(basicInfo.target_list).map((item, index) => (
                <span key={`${item}-${index}`} className="viewer-tag">{String(item)}</span>
              ))}
            </div>
          ) : (
            <p className="viewer-empty">暂无关联目标</p>
          )}
        </article>
        <article className="card viewer-card-soft">
          <h3>关联产品与采购说明</h3>
          <DefinitionGrid
            items={[
              { label: "关联产品", value: normalizeList(basicInfo.related_products).join("、") },
              { label: "选择供应商原因", value: basicInfo.supplier_reason },
              { label: "采购说明", value: basicInfo.procurement_note },
            ]}
          />
        </article>
      </div>
    );
  }

  function renderTaskOrderBusinessArchitecture() {
    const businessArchitecture = taskOrderView?.business_architecture || {};
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <h3>业务单元清单</h3>
          <DataTable
            rows={businessArchitecture.business_units}
            preferredKeys={["business_object", "business_unit", "business_process"]}
            emptyText="暂无业务单元清单"
          />
        </article>
        <article className="card viewer-card-soft">
          <h3>审批节点</h3>
          <DataTable
            rows={businessArchitecture.approval_nodes}
            preferredKeys={["function_name", "removed_nodes", "description"]}
            emptyText="暂无审批节点数据"
          />
        </article>
      </div>
    );
  }

  function renderTaskOrderAssignment() {
    const taskAssignment = taskOrderView?.task_assignment || {};
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <h3>业务流程清单</h3>
          <DataTable
            rows={taskAssignment.process_rows}
            preferredKeys={["process_name", "process_code", "owner", "output"]}
            emptyText="暂无业务流程"
          />
        </article>
        <article className="card viewer-card-soft">
          <h3>任务列表</h3>
          <DataTable
            rows={taskAssignment.task_rows}
            preferredKeys={["task_name", "task_owner", "deliverable", "complete_standard"]}
            emptyText="暂无任务明细"
          />
        </article>
        <article className="card viewer-card-soft">
          <h3>指标列表</h3>
          <DataTable
            rows={taskAssignment.metric_rows}
            preferredKeys={["metric_name", "metric_type", "target_value"]}
            emptyText="暂无指标数据"
          />
        </article>
      </div>
    );
  }

  function renderTaskOrderStaffing() {
    const staffing = taskOrderView?.staffing || {};
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <DefinitionGrid
            items={[
              { label: "开发模式", value: staffing.development_mode },
              { label: "投入人数", value: normalizeList(staffing.rows).length },
              { label: "预计人天", value: staffing.total_days },
              { label: "预计费用", value: formatCurrency(staffing.total_cost) },
            ]}
          />
        </article>
        <article className="card viewer-card-soft">
          <h3>人员配置及费用</h3>
          <DataTable
            rows={staffing.rows}
            preferredKeys={["name", "post_name", "level_name", "expected_days", "unit_price", "estimated_cost", "department_name"]}
            emptyText="暂无人员配置"
          />
        </article>
      </div>
    );
  }

  function renderTaskOrderCostEstimation() {
    const costEstimation = taskOrderView?.cost_estimation || {};
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <DefinitionGrid
            items={[
              { label: "本次任务单费用", value: formatCurrency(costEstimation.total_cost) },
              { label: "历史任务单费用", value: formatCurrency(costEstimation.history_total_cost) },
              { label: "历史任务单数量", value: normalizeList(costEstimation.history_rows).length },
            ]}
          />
        </article>
        <article className="card viewer-card-soft">
          <h3>本次任务单费用</h3>
          <DataTable
            rows={costEstimation.current_rows}
            preferredKeys={["post_name", "level_name", "expected_days", "unit_price", "estimated_cost"]}
            emptyText="暂无本次任务费用"
          />
        </article>
        <article className="card viewer-card-soft">
          <h3>历史任务单费用</h3>
          <DataTable
            rows={costEstimation.history_rows}
            preferredKeys={["task_name", "task_code", "total_cost", "status"]}
            emptyText="暂无历史任务费用"
          />
        </article>
      </div>
    );
  }

  function renderTaskOrderTechnicalRequirements() {
    const technicalRequirements = taskOrderView?.technical_requirements || {};
    const requirementItems = [
      { label: "系统功能需求", value: technicalRequirements.system_function },
      { label: "系统架构需求", value: technicalRequirements.system_architecture },
      { label: "系统集成与接口要求", value: technicalRequirements.integration_requirements },
      { label: "数据库要求", value: technicalRequirements.database_requirements },
      { label: "性能要求", value: technicalRequirements.performance_requirements },
      { label: "安全性要求", value: technicalRequirements.security_requirements },
      { label: "扩展性要求", value: technicalRequirements.scalability_requirements },
      { label: "技术栈要求", value: technicalRequirements.tech_stack_requirements },
      { label: "前端设计要求", value: technicalRequirements.frontend_requirements },
      { label: "兼容性要求", value: technicalRequirements.compatibility_requirements },
      { label: "质量要求", value: technicalRequirements.quality_requirements },
      { label: "进度要求", value: technicalRequirements.schedule_requirements },
      { label: "交接维要求", value: technicalRequirements.handover_requirements },
      { label: "交接物明细", value: technicalRequirements.handover_items },
      { label: "项目验收条件", value: technicalRequirements.acceptance_criteria },
    ];
    return (
      <div className="task-order-requirement-grid">
        {requirementItems.map((item) => (
            <article key={item.label} className="card viewer-card-soft task-order-requirement-card">
            <p className="panel-label">Requirement</p>
            <h3>{item.label}</h3>
            <p>{item.value || "待补充"}</p>
          </article>
        ))}
        {normalizeList(technicalRequirements.spec_rows).length ? (
          <article className="card viewer-card-soft task-order-requirement-card task-order-requirement-card-wide">
            <p className="panel-label">Source</p>
            <h3>技术要求明细</h3>
            <DataTable rows={technicalRequirements.spec_rows} emptyText="暂无技术要求明细" />
          </article>
        ) : null}
      </div>
    );
  }

  function renderTaskOrderProgress() {
    return (
      <section className="card span-full task-order-progress-card">
        <div className="section-head task-order-progress-head">
          <div>
            <h2>任务单进程</h2>
          </div>
          <div className="category-meta">
            {taskOrderView
              ? `当前任务单：${taskOrderView.task_name}`
              : "请选择一个任务单后查看详情。"}
          </div>
        </div>
        <div className="task-order-selector-bar">
          <div className="task-order-selector-meta">
            <strong>任务单选择</strong>
            <span>{taskOrders.length ? `共 ${taskOrders.length} 个任务单` : "暂无任务单"}</span>
            {taskOrderLoading ? <span>明细加载中...</span> : null}
            {taskOrderError ? <span>{taskOrderError}</span> : null}
          </div>
          <div className="task-order-selector-actions">
            <select
              value={selectedTaskOrder?.id || ""}
              onChange={(event) => updateTaskOrderId(event.target.value)}
              disabled={!taskOrders.length}
            >
              {taskOrders.map((item) => (
                <option key={item.id} value={item.id}>
                  {firstMeaningful(item.taskOrderName, item.taskName, item.task_name, item.id)}
                </option>
              ))}
            </select>
            {taskOrderView ? (
              <div className="task-order-selector-summary">
                <span>{taskOrderView.task_no || "-"}</span>
                <span>{taskOrderView.supplier_name || "-"}</span>
              </div>
            ) : null}
          </div>
        </div>
        <div className="task-order-stepper">
          {sectionDefinitions.map((item, index) => {
            const status = taskOrderSectionStatus(taskOrderView, item.key);
            const isActive = activeSection === item.key;
            return (
              <button
                key={item.key}
                className={`task-order-step ${isActive ? "active" : ""}`}
                type="button"
                onClick={() => setActiveSection(item.key)}
              >
                <span className="task-order-step-node">{index + 1}</span>
                <span className="task-order-step-label">{item.label}</span>
                <span className={`task-order-step-status ${status === "已填写" ? "done" : status === "待补充" ? "partial" : ""}`}>
                  {status}
                </span>
              </button>
            );
          })}
        </div>
      </section>
    );
  }

  function renderAcceptanceScope() {
    const openAcceptanceContract = (row, options = {}) => {
      const identity = resolveAcceptanceContractIdentity(row, options);
      if (!identity.contractId && !identity.contractNumber) {
        return;
      }
      setAcceptanceContractDrawerContract(row);
    };

    if (activeTab === "contracts") {
      const contractRows = filterByAcceptId(acceptance.contract_list);
      if (!contractRows.length) {
        return <p className="viewer-empty">暂无验收范围数据</p>;
      }
      return (
        <article className="acceptance-scope-card">
          <div className="acceptance-scope-board-title">合同展示</div>
          <div className="acceptance-scope-table-wrap">
            <table className="acceptance-scope-table acceptance-scope-contract-table">
              <thead>
                <tr>
                  <th>序号</th>
                  <th>验收单</th>
                  <th>合同名称</th>
                  <th>合同编号</th>
                  <th>合同状态</th>
                  <th>验收状态</th>
                  <th>签约供应商</th>
                  <th>合同金额(含税)</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {contractRows.map((row, index) => (
                  <tr key={row?.contractId || row?.id || `${index}`}>
                    <td>{index + 1}</td>
                    <td>{formatValue(row?.acceptName)}</td>
                    <td>{formatValue(firstMeaningful(row?.contractName, row?.name))}</td>
                    <td>{formatValue(firstMeaningful(row?.contractNo, row?.contractCode))}</td>
                    <td>{formatValue(firstMeaningful(row?.contractStatusName, row?.statusName, row?.status))}</td>
                    <td>{formatValue(row?.acceptStatusName)}</td>
                    <td>{formatValue(row?.supplierName)}</td>
                    <td>{formatCurrency(firstMeaningful(row?.amountTax, row?.amount, row?.contractAmountTax, row?.contractAmount))}</td>
                    <td>
                      <button
                        type="button"
                        className="acceptance-scope-action-link"
                        onClick={() => openAcceptanceContract(row, { allowRowId: true })}
                      >
                        查看合同
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      );
      return (
        <DataTable
          rows={filterByAcceptId(acceptance.contract_list)}
          preferredKeys={["acceptId", "acceptName", "contractName", "contractNo", "contractStatusName", "acceptStatusName", "supplierName", "amount"]}
          emptyText="暂无验收范围数据"
        />
      );
    }

    const taskRows = filterByAcceptId(normalizeList(acceptance.task_list).length ? acceptance.task_list : acceptance.task_acceptance_list);
    if (!taskRows.length) {
      return <p className="viewer-empty">暂无验收范围数据</p>;
    }

    return (
      <article className="acceptance-scope-card">
        <div className="acceptance-scope-board-title">任务单展示</div>
        <div className="acceptance-scope-table-wrap">
          <table className="acceptance-scope-table">
            <thead>
              <tr>
                <th>序号</th>
                <th>任务单来源</th>
                <th>任务单编码</th>
                <th>任务单名称</th>
                <th>供应商</th>
                <th>是否IT资源池</th>
                <th>任务单金额(元/含税)</th>
                <th>任务单验收金额(元/含税)</th>
                <th>任务单状态</th>
                <th>是否有条</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {taskRows.map((row, index) => (
                <tr key={row?.id || `${index}`}>
                  <td>{index + 1}</td>
                  <td>{firstMeaningful(row?.sourceName, row?.taskSourceName, "系统获取")}</td>
                  <td>{formatValue(firstMeaningful(row?.taskCode, row?.taskNo, row?.serialNo))}</td>
                  <td>{formatValue(firstMeaningful(row?.taskName, row?.name))}</td>
                  <td>{formatValue(row?.supplierName)}</td>
                  <td>{isTruthyFlag(row?.isItResource) ? "是" : "否"}</td>
                  <td>{formatCurrency(firstMeaningful(row?.taskAmountTax, row?.totalCost, row?.planTotalCost))}</td>
                  <td>{formatCurrency(firstMeaningful(row?.acceptanceAmountTax, row?.totalAcceptCost, row?.acceptTotalFeeHasTax))}</td>
                  <td>{acceptanceScopeTaskStatus(row)}</td>
                  <td>{isTruthyFlag(row?.acceptProblem ?? row?.flag ?? row?.isChose) ? "是" : "否"}</td>
                  <td>
                    <div className="acceptance-scope-actions">
                      <span className="acceptance-scope-action-link">查看合同</span>
                      <button
                        type="button"
                        className="acceptance-scope-action-link"
                        onClick={() => openAcceptanceContract(row)}
                      >
                        查看合同
                      </button>
                      <button
                        type="button"
                        className="acceptance-scope-action-link"
                        onClick={() => setAcceptanceTaskDrawerTask(row)}
                      >
                        查看任务单
                      </button>
                      <span className="acceptance-scope-action-link">查看任务单说明</span>
                      <span className="acceptance-scope-action-link">查看项目目标</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    );
  }

  function renderAcceptanceContractDrawer() {
    if (!acceptanceContractDrawerContract) {
      return null;
    }

    const drawerView = acceptanceContractDrawerView;
    const partyRows = normalizeList(drawerView?.parties);
    const fields = [
      { label: "合同名称", value: drawerView?.contract_name },
      { label: "合同编号", value: drawerView?.contract_number },
      { label: "合同主体", value: drawerView?.contract_subject },
      { label: "合同金额（含税）", value: formatCurrencyWithUnit(drawerView?.contract_amount_tax) },
      { label: "合同金额（不含税）", value: formatCurrencyWithUnit(drawerView?.contract_amount_no_tax) },
      { label: "所属合同类别", value: drawerView?.contract_category },
      { label: "合同子类", value: drawerView?.contract_subcategory },
      { label: "签约供应商", value: drawerView?.supplier_name },
      { label: "实际需求部门", value: drawerView?.demand_department },
      { label: "实际需求人", value: drawerView?.demand_user },
      { label: "合同类型", value: drawerView?.contract_type },
      { label: "合同开始时间", value: formatCompactDate(drawerView?.start_time) },
      { label: "合同截止时间", value: formatCompactDate(drawerView?.end_time) },
      { label: "是否涉及履约", value: drawerView?.involves_performance },
      { label: "税率（%）", value: formatPercent(drawerView?.tax_rate) },
      { label: "", value: "" },
    ];

    return (
      <div className="acceptance-contract-modal" role="dialog" aria-modal="true" aria-label="合同基本信息">
        <button
          type="button"
          className="acceptance-contract-modal-backdrop"
          aria-label="关闭合同详情"
          onClick={() => setAcceptanceContractDrawerContract(null)}
        />
        <section className="acceptance-contract-sheet">
          <header className="acceptance-contract-sheet-head">
            <div className="acceptance-contract-sheet-head-main">
              <h2>合同基本信息</h2>
              <span className="acceptance-contract-sheet-status">已完成</span>
            </div>
            <button
              type="button"
              className="acceptance-contract-sheet-close"
              aria-label="关闭"
              onClick={() => setAcceptanceContractDrawerContract(null)}
            >
              ×
            </button>
          </header>
          <div className="acceptance-contract-sheet-body">
            {acceptanceContractDrawerLoading ? <p className="acceptance-contract-sheet-hint">合同明细加载中...</p> : null}
            {acceptanceContractDrawerError ? (
              <p className="acceptance-contract-sheet-error">合同明细接口加载失败，当前先展示已有字段。{acceptanceContractDrawerError}</p>
            ) : null}
            <div className="acceptance-contract-grid">
              {fields.map((item, index) => (
                <div
                  key={`${item.label || "blank"}-${index}`}
                  className={`acceptance-contract-field ${!item.label && !item.value ? "is-blank" : ""}`}
                >
                  <span>{item.label || " "}</span>
                  <strong>{formatValue(item.value)}</strong>
                </div>
              ))}
            </div>
            <div className="acceptance-contract-party-block">
              <table className="acceptance-contract-party-table">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>相对方名称</th>
                    <th>相对方地址</th>
                    <th>法定代表人</th>
                    <th>相对方性质</th>
                  </tr>
                </thead>
                <tbody>
                  {partyRows.length ? (
                    partyRows.map((row, index) => (
                      <tr key={row?.id || `${index}`}>
                        <td>{index + 1}</td>
                        <td>{formatValue(row?.name)}</td>
                        <td>{formatValue(row?.address)}</td>
                        <td>{formatValue(row?.legalPerson)}</td>
                        <td>{formatValue(row?.nature)}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="acceptance-contract-party-empty">
                        暂无相对方信息
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    );
  }

  function renderAcceptanceTaskDrawer() {
    if (!acceptanceTaskDrawerTask) {
      return null;
    }

    const drawerView = acceptanceTaskDrawerView;
    const basicInfo = drawerView?.basic_info || {};
    const ownership = drawerView?.project_ownership || {};
    const workItems = buildTaskOrderDrawerWorkItems(drawerView);
    const criteriaItems = buildTaskOrderDrawerCriteriaItems(drawerView);
    const reasonItems = buildTaskOrderDrawerReasonOptions(drawerView);
    const evaluationRows = buildTaskOrderDrawerEvaluationRows(drawerView);
    const staffingMatrix = buildTaskOrderDrawerStaffingMatrix(drawerView);
    const taskDateText = [formatCompactDate(drawerView?.start_date), formatCompactDate(drawerView?.end_date)]
      .filter(Boolean)
      .join(" 至 ");
    const taskDepartment = firstMeaningful(
      basicInfo.task_department,
      acceptanceTaskDrawerTask?.putDepartmentName,
      acceptanceTaskDrawerTask?.taskPutDeptName,
      acceptanceTaskDrawerTask?.taskDeptName,
      acceptanceTaskDrawerTask?.departmentName,
      ownership.department_name,
    );
    const supplierContact = firstMeaningful(basicInfo.supplier_contact, acceptanceTaskDrawerTask?.supplierManageName);
    const procurementItems = toTextItems(basicInfo.procurement_note);

    return (
      <div className="acceptance-task-drawer-shell" role="dialog" aria-modal="true" aria-label="任务单详情">
        <button
          type="button"
          className="acceptance-task-drawer-backdrop"
          aria-label="关闭任务单详情"
          onClick={() => setAcceptanceTaskDrawerTask(null)}
        />
        <aside className="acceptance-task-drawer">
          <div className="acceptance-task-drawer-head">
            <div>
              <p className="acceptance-task-drawer-eyebrow">任务单详情</p>
              <h2>开发服务任务单</h2>
              <p className="acceptance-task-drawer-meta">{formatValue(drawerView?.task_no)}</p>
            </div>
            <div className="acceptance-task-drawer-head-actions">
              {acceptanceTaskDrawerLoading ? <span className="acceptance-task-drawer-status">加载中...</span> : null}
              <button
                type="button"
                className="acceptance-task-drawer-close"
                aria-label="关闭"
                onClick={() => setAcceptanceTaskDrawerTask(null)}
              >
                ×
              </button>
            </div>
          </div>
          <div className="acceptance-task-drawer-body">
            {acceptanceTaskDrawerError ? (
              <p className="acceptance-task-drawer-error">
                任务单明细接口加载失败，当前先展示已有字段。{acceptanceTaskDrawerError}
              </p>
            ) : null}

            <section className="acceptance-task-sheet">
              <div className="acceptance-task-sheet-title">开发服务任务单</div>
              <div className="acceptance-task-sheet-grid acceptance-task-sheet-grid-double">
                <div className="acceptance-task-sheet-field">
                  <span>项目名称</span>
                  <strong>{formatValue(firstMeaningful(drawerView?.project_name, summary.project_name, documentPayload?.project_name))}</strong>
                </div>
                <div className="acceptance-task-sheet-field">
                  <span>项目编号</span>
                  <strong>{formatValue(firstMeaningful(ownership.project_code, summary.project_code, documentPayload?.project_id))}</strong>
                </div>
              </div>
              <div className="acceptance-task-sheet-grid acceptance-task-sheet-grid-triple">
                <div className="acceptance-task-sheet-field">
                  <span>项目预算</span>
                  <strong>{formatValue(formatCurrencyWithUnit(firstMeaningful(drawerView?.request_budget, drawerView?.budget_overview?.project_budget)))}</strong>
                </div>
                <div className="acceptance-task-sheet-field">
                  <span>项目年度预算</span>
                  <strong>{formatValue(formatCurrencyWithUnit(firstMeaningful(drawerView?.annual_budget, drawerView?.budget_overview?.project_year_budget)))}</strong>
                </div>
                <div className="acceptance-task-sheet-field">
                  <span>项目负责人</span>
                  <strong>{formatValue(firstMeaningful(ownership.project_manager, summary.project_manager_name))}</strong>
                </div>
              </div>
              <div className="acceptance-task-sheet-grid acceptance-task-sheet-grid-double">
                <div className="acceptance-task-sheet-field">
                  <span>服务提供方</span>
                  <strong>{formatValue(firstMeaningful(basicInfo.supplier_name, drawerView?.supplier_name))}</strong>
                </div>
                <div className="acceptance-task-sheet-field">
                  <span>服务提供方负责人</span>
                  <strong>{formatValue(supplierContact)}</strong>
                </div>
              </div>
              <div className="acceptance-task-sheet-grid acceptance-task-sheet-grid-double">
                <div className="acceptance-task-sheet-field">
                  <span>合同名称</span>
                  <strong>{formatValue(basicInfo.contract_name)}</strong>
                </div>
                <div className="acceptance-task-sheet-field">
                  <span>合同编号</span>
                  <strong>{formatValue(basicInfo.contract_no)}</strong>
                </div>
              </div>
              <div className="acceptance-task-sheet-grid acceptance-task-sheet-grid-double">
                <div className="acceptance-task-sheet-field">
                  <span>任务单名称</span>
                  <strong>{formatValue(firstMeaningful(basicInfo.task_name, drawerView?.task_name))}</strong>
                </div>
                <div className="acceptance-task-sheet-field">
                  <span>任务单编号</span>
                  <strong>{formatValue(firstMeaningful(basicInfo.task_no, drawerView?.task_no))}</strong>
                </div>
              </div>
              <div className="acceptance-task-sheet-grid acceptance-task-sheet-grid-double">
                <div className="acceptance-task-sheet-field">
                  <span>任务日期</span>
                  <strong>{formatValue(taskDateText || formatCompactDate(acceptanceTaskDrawerTask?.taskStartTime))}</strong>
                </div>
                <div className="acceptance-task-sheet-field">
                  <span>任务提出部门</span>
                  <strong>{formatValue(taskDepartment)}</strong>
                </div>
              </div>

              <div className="acceptance-task-sheet-block">
                <div className="acceptance-task-sheet-block-label">工作任务</div>
                <div className="acceptance-task-sheet-block-body">
                  <p className="acceptance-task-sheet-subtitle">任务描述：</p>
                  {workItems.length ? (
                    <ol className="acceptance-task-sheet-list">
                      {workItems.map((item, index) => (
                        <li key={`work-${index}`}>{item.replace(/^\d+\.\s*/, "")}</li>
                      ))}
                    </ol>
                  ) : (
                    <p className="acceptance-task-sheet-empty">-</p>
                  )}
                  <p className="acceptance-task-sheet-subtitle">验收标准：</p>
                  {criteriaItems.length ? (
                    <ol className="acceptance-task-sheet-list">
                      {criteriaItems.map((item, index) => (
                        <li key={`criteria-${index}`}>{item.replace(/^\d+\.\s*/, "")}</li>
                      ))}
                    </ol>
                  ) : (
                    <p className="acceptance-task-sheet-empty">-</p>
                  )}
                </div>
              </div>

              <div className="acceptance-task-sheet-block">
                <div className="acceptance-task-sheet-block-label">选择此供应商原因</div>
                <div className="acceptance-task-sheet-block-body">
                  <ul className="acceptance-task-sheet-checklist">
                    {reasonItems.map((item) => (
                      <li key={item.key}>
                        <span className={`acceptance-task-sheet-checkbox ${item.checked ? "checked" : ""}`} aria-hidden="true">
                          {item.checked ? "✓" : ""}
                        </span>
                        <span>{item.label}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              <div className="acceptance-task-sheet-block">
                <div className="acceptance-task-sheet-block-label">采购说明</div>
                <div className="acceptance-task-sheet-block-body">
                  {procurementItems.length ? (
                    procurementItems.map((item, index) => (
                      <p key={`procurement-${index}`} className="acceptance-task-sheet-paragraph">{item}</p>
                    ))
                  ) : (
                    <p className="acceptance-task-sheet-empty">-</p>
                  )}
                </div>
              </div>

              <div className="acceptance-task-sheet-block">
                <div className="acceptance-task-sheet-block-label">工作量评估</div>
                <div className="acceptance-task-sheet-block-body">
                  <div className="acceptance-task-sheet-table-wrap">
                    <table className="acceptance-task-sheet-table">
                      <thead>
                        <tr>
                          <th>子任务</th>
                          <th>开始时间</th>
                          <th>结束时间</th>
                        </tr>
                      </thead>
                      <tbody>
                        {evaluationRows.map((item) => (
                          <tr key={item.id}>
                            <td>{formatValue(item.task_name)}</td>
                            <td>{formatValue(item.start_date)}</td>
                            <td>{formatValue(item.end_date)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>

              <div className="acceptance-task-sheet-block">
                <div className="acceptance-task-sheet-block-label">工作量明细（计划）</div>
                <div className="acceptance-task-sheet-block-body">
                  {staffingMatrix.length ? (
                    <div className="acceptance-task-sheet-table-wrap">
                      <table className="acceptance-task-sheet-table acceptance-task-sheet-matrix">
                        <thead>
                          <tr>
                            <th>人员指标</th>
                            {staffingMatrix.map((item) => (
                              <th key={item.key}>{item.key}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          <tr>
                            <td>人员需求数量</td>
                            {staffingMatrix.map((item) => (
                              <td key={`${item.key}-people`}>{item.people}</td>
                            ))}
                          </tr>
                          <tr>
                            <td>工作量（人天）</td>
                            {staffingMatrix.map((item) => (
                              <td key={`${item.key}-days`}>{item.days || "-"}</td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="acceptance-task-sheet-empty">-</p>
                  )}
                </div>
              </div>
            </section>
          </div>
        </aside>
      </div>
    );
  }

  function renderAcceptanceStage() {
    const currentAcceptance = selectedAcceptance || acceptanceInfoList[0] || null;
    const isFinalAcceptance = Number(firstMeaningful(currentAcceptance?.isFinalAccept, summary?.isFinalAcceptLast, 0)) === 1;
    const stageLabel = isFinalAcceptance ? "终验收(本次验收)" : "阶段验收(本次验收)";
    const progressValue = Math.max(
      0,
      Math.min(
        100,
        Number(
          firstMeaningful(
            currentAcceptance?.budgetProcessDetails,
            summary?.budgetExecutionRate,
            summary?.budgetProcess,
            0,
          ),
        ) || 0,
      ),
    );
    const progressText = formatPercent(progressValue);

    return (
      <section className="acceptance-stage-card">
        <div className="acceptance-stage-tab-row">
          <button type="button" className="acceptance-stage-tab active">
            {stageLabel}
          </button>
        </div>
        <div className="acceptance-stage-progress-shell">
          <div className="acceptance-stage-progress-label">验收金额占比</div>
          <div className="acceptance-stage-progress-track">
            <div className="acceptance-stage-progress-fill" style={{ width: `${progressValue}%` }}>
              <span className="acceptance-stage-progress-inline">{progressText}</span>
            </div>
          </div>
          <div className="acceptance-stage-progress-value">{progressText}</div>
        </div>
      </section>
    );
  }

  function renderAcceptanceDetailBoard() {
    if (activeTab === "contract_acceptance") {
      return (
        <DataTable
          rows={filterByAcceptId(acceptance.contract_acceptance_list)}
          preferredKeys={["acceptId", "acceptName", "contractName", "contractNo", "acceptStatusName", "result", "conclusion"]}
          emptyText="暂无合同验收明细数据"
        />
      );
    }

    if (!acceptanceDetailTaskRows.length || !selectedAcceptanceDetailTask) {
      return <p className="viewer-empty">暂无任务单验收明细数据</p>;
    }

    const detailIndex = acceptanceDetailTaskRows.findIndex(
      (item) => String(item?.id || item?.taskId || "").trim() === String(selectedAcceptanceDetailTask?.id || selectedAcceptanceDetailTask?.taskId || "").trim(),
    );
    const previousTask = detailIndex > 0 ? acceptanceDetailTaskRows[detailIndex - 1] : null;
    const nextTask = detailIndex >= 0 && detailIndex < acceptanceDetailTaskRows.length - 1 ? acceptanceDetailTaskRows[detailIndex + 1] : null;
    const detailSummary = {
      title: firstMeaningful(selectedAcceptanceDetailTask?.taskName, acceptanceDetailTaskView?.task_name),
      taskNo: firstMeaningful(selectedAcceptanceDetailTask?.taskCode, selectedAcceptanceDetailTask?.taskNo, selectedAcceptanceDetailTask?.serialNo, acceptanceDetailTaskView?.task_no),
      supplier: firstMeaningful(selectedAcceptanceDetailTask?.supplierName, acceptanceDetailTaskView?.supplier_name),
      amount: formatCurrency(firstMeaningful(selectedAcceptanceDetailTask?.acceptanceAmountTax, selectedAcceptanceDetailTask?.totalAcceptCost, selectedAcceptanceDetailTask?.acceptTotalFeeHasTax)),
      period: `${formatCompactDate(firstMeaningful(selectedAcceptanceDetailTask?.taskAduitTime, selectedAcceptanceDetailTask?.taskStartTime, acceptanceDetailTaskView?.start_date)) || "-"} /至今`.replace(" /", "/"),
    };
    const processRows = buildAcceptanceDetailProcessRows(
      selectedAcceptanceDetailTask,
      acceptanceDetailTaskView,
      documentPayload,
      acceptanceDeliverableSummary,
    );
    const memberRows = buildAcceptanceDetailMemberRows(acceptanceDetailTaskView);

    return (
      <section className="acceptance-detail-card">
        <div className="acceptance-detail-board-title">任务单验收</div>
        <div className="acceptance-detail-task-strip">
          <button
            type="button"
            className="acceptance-detail-strip-nav"
            onClick={() => previousTask && setAcceptanceDetailTaskId(String(previousTask?.id || previousTask?.taskId || ""))}
            disabled={!previousTask}
            aria-label="上一条任务单"
          >
            ‹
          </button>
          <div className="acceptance-detail-task-summary">
            <button
              type="button"
              className="acceptance-detail-task-title"
              onClick={() => setAcceptanceDetailViewMode("processes")}
            >
              {detailSummary.title}
            </button>
            <div className="acceptance-detail-task-meta">
              <div>
                <span>任务单编号</span>
                <strong>{formatValue(detailSummary.taskNo)}</strong>
              </div>
              <div>
                <span>供应商</span>
                <strong>{formatValue(detailSummary.supplier)}</strong>
              </div>
              <div>
                <span>任务单金额（含税）</span>
                <strong>{formatValue(detailSummary.amount)}</strong>
              </div>
              <div>
                <span>时间周期</span>
                <strong>{formatValue(detailSummary.period)}</strong>
              </div>
            </div>
          </div>
          <button
            type="button"
            className="acceptance-detail-strip-nav"
            onClick={() => nextTask && setAcceptanceDetailTaskId(String(nextTask?.id || nextTask?.taskId || ""))}
            disabled={!nextTask}
            aria-label="下一条任务单"
          >
            ›
          </button>
        </div>
        {acceptanceDetailTaskError ? (
          <p className="acceptance-detail-error">
            任务单详情接口加载失败，当前先用项目资料生成验收明细。{acceptanceDetailTaskError}
          </p>
        ) : null}
        <div className="acceptance-detail-layout">
          <div className="acceptance-detail-side">
            <button
              type="button"
              className={`acceptance-detail-side-tab ${acceptanceDetailViewMode === "processes" ? "active" : ""}`}
              onClick={() => setAcceptanceDetailViewMode("processes")}
            >
              选择流程
            </button>
            <button
              type="button"
              className={`acceptance-detail-side-tab ${acceptanceDetailViewMode === "members" ? "active" : ""}`}
              onClick={() => setAcceptanceDetailViewMode("members")}
            >
              人员组织
            </button>
          </div>
          <div className="acceptance-detail-main">
            {acceptanceDetailTaskLoading ? <p className="acceptance-detail-loading">任务单明细加载中...</p> : null}
            {acceptanceDetailViewMode === "processes" ? (
              <div className="acceptance-detail-table-wrap">
                <table className="acceptance-detail-table acceptance-detail-table-process">
                  <thead>
                    <tr>
                      <th>序号</th>
                      <th>业务流程编号</th>
                      <th>业务流程</th>
                      <th>业务级别</th>
                      <th>业务角色</th>
                      <th>任务总数</th>
                      <th>已完成任务数</th>
                      <th>创建时间</th>
                      <th>开发类别</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {processRows.map((item, index) => (
                      <tr key={item.id}>
                        <td>{index + 1}</td>
                        <td>{formatValue(item.process_code)}</td>
                        <td>{formatValue(item.process_name)}</td>
                        <td>{formatValue(item.process_level)}</td>
                        <td>{formatValue(item.process_role)}</td>
                        <td>{formatValue(item.total_task_count)}</td>
                        <td>{formatValue(item.completed_task_count)}</td>
                        <td>{formatValue(item.created_at)}</td>
                        <td>{formatValue(item.develop_category)}</td>
                        <td>
                          <div className="acceptance-detail-actions">
                            <span className="acceptance-detail-action-link">查看任务</span>
                            <span className="acceptance-detail-action-link">查看指标</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="acceptance-detail-table-wrap">
                <table className="acceptance-detail-table acceptance-detail-table-members">
                  <thead>
                    <tr>
                      <th>序号</th>
                      <th>姓名</th>
                      <th>归属</th>
                      <th>岗位</th>
                      <th>职级</th>
                      <th>部门</th>
                      <th>效能评分</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {memberRows.map((item, index) => (
                      <tr key={item.id}>
                        <td>{index + 1}</td>
                        <td>{formatValue(item.name)}</td>
                        <td>
                          <span className={`acceptance-detail-owner-pill ${item.ownership === "三方" ? "is-third" : ""}`}>
                            {item.ownership}
                          </span>
                        </td>
                        <td>{formatValue(item.position)}</td>
                        <td>{formatValue(item.level)}</td>
                        <td>{formatValue(item.department)}</td>
                        <td>
                          <span className="acceptance-detail-score">
                            <span className="acceptance-detail-score-dot" aria-hidden="true" />
                            {formatValue(item.efficiency_score)}
                          </span>
                        </td>
                        <td>
                          <div className="acceptance-detail-actions">
                            <span className="acceptance-detail-action-link">查看工时任务</span>
                            <span className="acceptance-detail-action-link">任务描述</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </section>
    );
  }

  function renderAcceptanceDetail() {
    const rows = filterByAcceptId(activeTab === "contract_acceptance" ? acceptance.contract_acceptance_list : acceptance.task_acceptance_list);
    const preferredKeys = activeTab === "contract_acceptance"
      ? ["acceptId", "acceptName", "contractName", "contractNo", "acceptStatusName", "result", "conclusion"]
      : ["acceptId", "acceptName", "taskName", "taskNo", "acceptStatusName", "result", "conclusion"];
    return <DataTable rows={rows} preferredKeys={preferredKeys} emptyText="暂无验收明细数据" />;
  }

  function renderAcceptanceDeliverables() {
    return <DataTable rows={filterByAcceptId(acceptance.deliverables)} preferredKeys={["acceptId", "acceptName", "deliverableName", "deliverName", "name", "deliverStatusName", "result", "remark"]} emptyText="暂无上传备证数据" />;
  }

  function renderAcceptanceDeliverablesBoard() {
    const acceptanceBoard = (
      <AcceptanceDeliverablesBoard
        currentAcceptance={selectedAcceptance || acceptanceInfoList[0] || null}
        summary={summary}
        stats={buildAcceptanceDeliverableStats(documentPayload, acceptanceDeliverableSummary)}
        onOpenStandard={() => {
          setDeliverablesDialogTab("standard");
          setDeliverablesDialogOpen(true);
        }}
        onOpenTask={() => {
          setDeliverablesDialogTab("task");
          setDeliverablesDialogOpen(true);
        }}
      />
    );
    return acceptanceBoard;

    const currentAcceptance = selectedAcceptance || acceptanceInfoList[0] || null;
    const isFinalAcceptance = Number(firstMeaningful(currentAcceptance?.isFinalAccept, summary?.isFinalAcceptLast, 0)) === 1;
    const stageLabel = isFinalAcceptance ? "终验收(本次验收)" : "阶段验收(本次验收)";
    const stats = buildAcceptanceDeliverableStats(documentPayload, acceptanceDeliverableSummary);
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
            <button type="button" className="acceptance-deliverables-upload-button">查看备证</button>
          </div>
          <div className="acceptance-deliverables-stats">
            {[stats.task, stats.standard].map((item) => (
              <article key={item.label} className="acceptance-deliverables-stat-card">
                <div className="acceptance-deliverables-stat-head">
                  <span>{item.label}</span>
                  <strong>{`${item.uploaded}/${item.total || 0}`}</strong>
                </div>
                <div className="acceptance-deliverables-progress-row">
                  <div className="acceptance-deliverables-progress-track">
                    <div className="acceptance-deliverables-progress-fill" style={{ width: `${item.rate}%` }} />
                  </div>
                  <span>{`已上传${formatPercent(item.rate)}`}</span>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>
    );
  }

  function renderAcceptanceProgress() {
    return (
      <section className="card span-full acceptance-progress-card">
        <div className="section-head acceptance-progress-head">
          <div>
            <h2>验收进程</h2>
          </div>
          <div className="category-meta">
            {selectedAcceptId
              ? `当前验收单：${selectedAcceptance?.acceptName || selectedAcceptId}`
              : "所有必填项填写完成后，可提交验收申请。"}
          </div>
        </div>
        <div className="acceptance-stepper">
          {sectionDefinitions.map((item, index) => {
            const status = sectionStatus(documentPayload, { groups: reviewGroups }, scene, item.key);
            const isActive = activeSection === item.key;
            return (
              <button
                key={item.key}
                className={`acceptance-step ${isActive ? "active" : ""}`}
                type="button"
                onClick={() => setActiveSection(item.key)}
              >
                <span className="acceptance-step-node">{index + 1}</span>
                <span className="acceptance-step-label">{item.label}</span>
                <span className={`acceptance-step-status ${status === "已填充" ? "done" : ""}`}>
                  {status === "已填充" ? "已填写" : status}
                </span>
              </button>
            );
          })}
        </div>
      </section>
    );
  }

  function renderBody() {
    if (loading) {
      return <p className="viewer-empty">加载中...</p>;
    }
    if (error) {
      return <p className="viewer-empty">{error}</p>;
    }
    if (!documentPayload) {
      return <p className="viewer-empty">暂无项目数据</p>;
    }
    if (viewerPhase === TASK_ORDER_PHASE && !taskOrderView) {
      return <p className="viewer-empty">暂无任务单数据</p>;
    }
    if (viewerPhase === "acceptance" && ACCEPTANCE_ORDER_SECTIONS.has(activeSection) && !selectedAcceptId) {
      return renderAcceptanceStage();
    }
    if (activeSection === "project_content" || activeSection === "project_review") {
      return renderProjectContent(activeSection);
    }
    if (activeSection === "project_value") {
      return renderProjectValue();
    }
    if (activeSection === "architecture_review") {
      return <ArchitectureReviewPanel groups={reviewGroups} scene={scene} />;
    }
    if (activeSection === "tam_models") {
      return renderTamModels();
    }
    if (activeSection === "organization") {
      return renderOrganization();
    }
    if (activeSection === "milestones") {
      return renderMilestones();
    }
    if (activeSection === "budget") {
      return renderBudget();
    }
    if (activeSection === "cost_change") {
      return renderCostChange();
    }
    if (activeSection === "basic_info") {
      return renderTaskOrderBasicInfo();
    }
    if (activeSection === "business_architecture") {
      return renderTaskOrderBusinessArchitecture();
    }
    if (activeSection === "task_assignment") {
      return renderTaskOrderAssignment();
    }
    if (activeSection === "staffing") {
      return renderTaskOrderStaffing();
    }
    if (activeSection === "cost_estimation") {
      return renderTaskOrderCostEstimation();
    }
    if (activeSection === "technical_requirements") {
      return renderTaskOrderTechnicalRequirements();
    }
    if (activeSection === "acceptance_scope") {
      return renderAcceptanceScope();
    }
    if (activeSection === "acceptance_stage") {
      return renderAcceptanceStage();
    }
    if (activeSection === "acceptance_detail") {
      return renderAcceptanceDetailBoard();
    }
    if (activeSection === "acceptance_deliverables") {
      return renderAcceptanceDeliverablesBoard();
    }
    return <p className="viewer-empty">暂无内容</p>;
  }

  return (
    <PageLayout wide scene={scene} section="projects">
      <header className="viewer-overview">
        <section className={`card viewer-title-bar ${viewerPhase === "acceptance" ? "acceptance-title-bar" : viewerPhase === TASK_ORDER_PHASE ? "task-order-title-bar" : ""}`}>
          <div className="viewer-title-main">
            <span className={`viewer-title-dot ${viewerPhase === "acceptance" ? "acceptance-title-dot" : viewerPhase === TASK_ORDER_PHASE ? "task-order-title-dot" : ""}`} aria-hidden="true" />
            <div>
              <h1 className={`viewer-title ${viewerPhase === "acceptance" ? "acceptance-page-title" : viewerPhase === TASK_ORDER_PHASE ? "task-order-page-title" : ""}`}>
                {viewerPhase === TASK_ORDER_PHASE
                  ? taskOrderView?.task_name || "任务单详情"
                  : summary.project_name || documentPayload?.project_name || projectId}
              </h1>
              <div className="viewer-badge-row">
                {projectBadges.length
                  ? projectBadges.map((item) => (
                      <span key={item} className="viewer-pill">{item}</span>
                    ))
                  : <span className="viewer-pill viewer-pill-muted">未识别分类</span>}
              </div>
              {viewerPhase === TASK_ORDER_PHASE && taskOrderView ? (
                <div className="viewer-debug-meta">
                  <span>任务单编号: {taskOrderView.task_no || "-"}</span>
                  <span>供应商: {taskOrderView.supplier_name || "-"}</span>
                  <span>计划时间: {taskOrderView.start_date || "-"} / {taskOrderView.end_date || "-"}</span>
                </div>
              ) : null}
              {viewerPhase === "acceptance" && (debugIds.budget_project_id || debugIds.establishment_project_id) ? (
                <div className="viewer-debug-meta">
                  {debugIds.budget_project_id ? <span>预算ID: {debugIds.budget_project_id}</span> : null}
                  {debugIds.establishment_project_id ? <span>立项ID: {debugIds.establishment_project_id}</span> : null}
                </div>
              ) : null}
            </div>
          </div>
          <div className="viewer-actions">
            {viewerPhase === "acceptance" && selectedAcceptId ? (
              <span className="viewer-pill">当前验收单: {selectedAcceptance?.acceptName || selectedAcceptId}</span>
            ) : null}
            {viewerPhase === TASK_ORDER_PHASE ? (
              <span className="viewer-pill">任务单数量: {taskOrders.length}</span>
            ) : viewerPhase === "initiation" ? (
              <>
                <select value={category} onChange={(event) => setCategory(event.target.value)}>
                  {normalizeList(rules?.categories).map((item) => (
                    <option key={item.name} value={item.name}>{item.name} / {item.group}</option>
                  ))}
                </select>
                <Link className="nav-link" to={`/workbench?projectId=${encodeURIComponent(projectId)}`}>
                  打开管理配置
                </Link>
                <button className="primary-button" type="button" onClick={runApproval} disabled={approvalBusy}>
                  {approvalBusy ? "审批执行中..." : "执行远程审批"}
                </button>
              </>
            ) : (
              <>
                <select value={category} onChange={(event) => setCategory(event.target.value)}>
                  <option value="">自动识别分类</option>
                  {normalizeList(rules?.categories).map((item) => (
                    <option key={item.name} value={item.name}>{item.name}</option>
                  ))}
                </select>
                <button className="primary-button" type="button" onClick={runApproval} disabled={approvalBusy}>
                  {approvalBusy ? "审批执行中..." : "执行远程审批"}
                </button>
              </>
            )}
          </div>
        </section>

        {viewerPhase !== TASK_ORDER_PHASE && viewerPhase !== "initiation" && approvalMessage ? (
          <section className="card viewer-card-soft">
            <p className="panel-label">Approval</p>
            <p>{approvalMessage}</p>
          </section>
        ) : null}

        {viewerPhase === "initiation" && latestApproval ? (
          <section className={`card viewer-decision-banner ${approvalToneClass(latestApproval.decision)}`}>
            <div className="viewer-decision-banner-head">
              <span className={`viewer-decision-pill ${approvalToneClass(latestApproval.decision)}`}>
                {latestApproval.decision || "-"}
              </span>
            </div>
            <p className="viewer-approval-summary">{latestApproval.summary || "-"}</p>
          </section>
        ) : null}

        {viewerPhase !== TASK_ORDER_PHASE && viewerPhase !== "initiation" && latestApproval ? (
          <section className="card viewer-card-soft">
            <p className="panel-label">Latest Approval</p>
            <DefinitionGrid
              items={[
                { label: "结论", value: latestApproval.decision },
                { label: "摘要", value: latestApproval.summary },
                { label: "分类", value: latestApproval.resolved_category || latestApproval.category },
              ]}
            />
            {approvalDetailItems.length ? (
              <div className="viewer-approval-actions">
                <button className="ghost-button" type="button" onClick={() => setApprovalDetailOpen((current) => !current)}>
                  {approvalDetailOpen ? "收起规则明细" : "查看规则明细"}
                </button>
              </div>
            ) : null}
            {approvalDetailOpen && approvalDetailItems.length ? (
              <div className="viewer-approval-detail-panel">
                <div className="viewer-approval-detail-head">
                  <h3>审批规则明细</h3>
                  <span>{approvalDetailItems.length} 项检查</span>
                </div>
                <div className="viewer-approval-detail-list">
                  {approvalDetailItems.map((item) => (
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
                          <strong>为什么是这个结果</strong>
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
          </section>
        ) : null}

        {renderOverview()}
      </header>

      <main className="grid">
        {viewerPhase === "acceptance" ? (
          renderAcceptanceProgress()
        ) : viewerPhase === TASK_ORDER_PHASE ? (
          <>
            <section className="card span-full">
              <div className="viewer-phase-bar">
                <Link className={`viewer-phase-pill ${viewerPhase === "initiation" ? "active" : ""}`} to={`/project/${encodeURIComponent(initiationProjectId)}?scene=initiation${category ? `&category=${encodeURIComponent(category)}` : ""}`}>
                  立项
                </Link>
                <Link className={`viewer-phase-pill ${viewerPhase === TASK_ORDER_PHASE ? "active" : ""}`} to={`/project/${encodeURIComponent(projectId)}?scene=${TASK_ORDER_PHASE}${category ? `&category=${encodeURIComponent(category)}` : ""}`}>
                  任务单
                </Link>
                <Link className={`viewer-phase-pill ${viewerPhase === "acceptance" ? "active" : ""}`} to={`/project/${encodeURIComponent(acceptanceProjectId)}?scene=acceptance${category ? `&category=${encodeURIComponent(category)}` : ""}`}>
                  验收
                </Link>
              </div>
            </section>
            {renderTaskOrderProgress()}
          </>
        ) : (
          <section className="card span-full">
            <div className="section-head viewer-progress-head">
              <div>
                <h2>立项进程</h2>
              </div>
              <div className="category-meta">按当前立项材料核对项目内容、评审、组织、里程碑和预算。</div>
            </div>
            <div className="summary-strip">
              {sectionDefinitions.map((item) => (
                <button
                  key={item.key}
                  className={`summary-tile viewer-summary-item ${activeSection === item.key ? "active" : ""}`}
                  type="button"
                  onClick={() => setActiveSection(item.key)}
                >
                  <p className="viewer-summary-label">{item.label}</p>
                  <strong>{sectionStatus(documentPayload, { groups: reviewGroups }, scene, item.key)}</strong>
                </button>
              ))}
            </div>
          </section>
        )}

        <section className={`card span-full viewer-content-block ${viewerPhase === "acceptance" ? "acceptance-content-block" : viewerPhase === TASK_ORDER_PHASE ? "task-order-content-block" : ""}`}>
          <div className="section-head">
            <div>
              <p className="panel-label">
                {viewerPhase === "acceptance" ? "Acceptance Section" : viewerPhase === TASK_ORDER_PHASE ? "Task Order Section" : "Section"}
              </p>
              <h2>
                {viewerPhase === "acceptance"
                  ? acceptanceSectionTitle(activeSection, sectionDefinitions.find((item) => item.key === activeSection)?.label)
                  : sectionDefinitions.find((item) => item.key === activeSection)?.label || "项目内容"}
              </h2>
            </div>
          </div>
          <div className={`viewer-tab-bar ${tabs.length && viewerPhase !== TASK_ORDER_PHASE ? "" : "is-hidden"} ${viewerPhase === "acceptance" ? "acceptance-tab-bar" : ""}`}>
            {tabs.map((tab) => (
              <button
                key={tab.key}
                className={`viewer-tab ${activeTab === tab.key ? "active" : ""} ${viewerPhase === "acceptance" ? "acceptance-tab" : ""}`}
                type="button"
                onClick={() => setActiveTabs((current) => ({ ...current, [activeSection]: tab.key }))}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className={`viewer-layout ${viewerPhase === "acceptance" && activeSection === "project_review" ? "viewer-layout-project-review" : ""}`}>{renderBody()}</div>
        </section>
      </main>
      <AcceptanceDeliverablesDialog
        open={deliverablesDialogOpen}
        activeTab={deliverablesDialogTab}
        onClose={() => setDeliverablesDialogOpen(false)}
        onTabChange={setDeliverablesDialogTab}
        currentAcceptance={selectedAcceptance || acceptanceInfoList[0] || null}
        summary={summary}
        standardRows={acceptanceStandardDeliverableRows}
        standardSummary={acceptance.standard_deliverables}
        taskGroups={acceptanceTaskDeliverableGroups}
      />
      {renderAcceptanceContractDrawer()}
      {renderAcceptanceTaskDrawer()}
    </PageLayout>
  );
}
