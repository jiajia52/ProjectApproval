import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import PageLayout from "../../components/PageLayout";
import { normalizeScene, requestJson } from "../../api";

import {
  INITIATION_SECTIONS,
  TASK_ORDER_PHASE,
  TASK_ORDER_SECTIONS,
  SECTION_TABS,
  ACCEPTANCE_ORDER_SECTIONS,
  normalizeList,
  formatValue,
  formatCurrency,
  approvalToneClass,
  firstMeaningful,
  hasReviewTabContent,
  sectionStatus,
  buildProjectBadges,
  acceptanceSectionTitle,
  buildAcceptanceVisibility,
  buildTaskOrderViewModel,
  taskOrderSectionStatus,
  DefinitionGrid,
  DataTable,
  MachineScopeTable,
  UploadSection,
  TamModelBoard,
  ArchitectureReviewPanel,
} from "./projectViewerShared";

function approvalTimestamp(record) {
  const value = record?.generated_at || record?.approvalGeneratedAt || "";
  const timestamp = value ? new Date(value).getTime() : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function pickNewerApproval(primary, fallback) {
  if (!primary) {
    return fallback || null;
  }
  if (!fallback) {
    return primary;
  }
  return approvalTimestamp(primary) >= approvalTimestamp(fallback) ? primary : fallback;
}

export default function ProjectViewerPage() {
  const { projectId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const scene = normalizeScene(TASK_ORDER_PHASE);
  const viewerPhase = TASK_ORDER_PHASE;
  const [rules, setRules] = useState(null);
  const [category, setCategory] = useState(searchParams.get("category") || "");
  const [documentPayload, setDocumentPayload] = useState(null);
  const [architecturePayload, setArchitecturePayload] = useState(null);
  const [latestApproval, setLatestApproval] = useState(null);
  const [taskOrderItems, setTaskOrderItems] = useState([]);
  const [taskOrderDetail, setTaskOrderDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [taskOrderLoading, setTaskOrderLoading] = useState(false);
  const [taskOrderError, setTaskOrderError] = useState("");
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [approvalMessage, setApprovalMessage] = useState("");
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
  const [taskOrderBusinessTab, setTaskOrderBusinessTab] = useState("business_units");
  const [taskOrderBusinessUnitTab, setTaskOrderBusinessUnitTab] = useState("object");
  const [taskOrderApprovalNodeTab, setTaskOrderApprovalNodeTab] = useState("removed");
  const [taskOrderCostTab, setTaskOrderCostTab] = useState("current");

  const summary = documentPayload?.project_summary || {};
  const acceptance = documentPayload?.acceptance || {};
  const acceptanceInfoList = normalizeList(acceptance.info_list);
  const taskOrders = taskOrderItems;
  const selectedTaskOrderId = String(searchParams.get("taskOrderId") || "").trim();
  const selectedTaskOrder = useMemo(
    () => taskOrders.find((item) => String(item?.id || "").trim() === selectedTaskOrderId) || taskOrders[0] || null,
    [selectedTaskOrderId, taskOrders],
  );
  const approvalTargetId = viewerPhase === TASK_ORDER_PHASE
    ? String(selectedTaskOrder?.id || "").trim()
    : String(projectId || "").trim();
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
  const acceptanceVisibility = useMemo(
    () => buildAcceptanceVisibility(rules, effectiveCategory),
    [rules, effectiveCategory],
  );
  const sectionDefinitions = viewerPhase === "acceptance"
    ? acceptanceVisibility.visibleSections
    : viewerPhase === TASK_ORDER_PHASE
      ? TASK_ORDER_SECTIONS
      : INITIATION_SECTIONS;
  const tabs =
    viewerPhase === "acceptance" && activeSection === "project_review"
      ? acceptanceVisibility.visibleProjectReviewTabs
      : viewerPhase === "acceptance" && activeSection === "tam_models"
        ? acceptanceVisibility.visibleTamTabs
        : SECTION_TABS[activeSection] || [];
  const activeTab = activeTabs[activeSection] || tabs[0]?.key || "";
  const projectBadges = buildProjectBadges(summary);
  const debugIds = documentPayload?.debug_ids || {};
  const taskOrderView = useMemo(
    () => buildTaskOrderViewModel(selectedTaskOrder, taskOrderDetail, documentPayload),
    [documentPayload, selectedTaskOrder, taskOrderDetail],
  );
  const initiationProjectId = viewerPhase === "acceptance"
    ? String(debugIds.establishment_project_id || projectId)
    : String(projectId);
  const acceptanceProjectId = viewerPhase === "acceptance"
    ? String(debugIds.budget_project_id || projectId)
    : String(projectId);

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
    setTaskOrderBusinessTab("business_units");
    setTaskOrderBusinessUnitTab("object");
    setTaskOrderApprovalNodeTab("removed");
    setTaskOrderCostTab("current");
  }, [selectedTaskOrder?.id]);

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
    const shouldFetchTaskOrderApproval = viewerPhase !== TASK_ORDER_PHASE || Boolean(approvalTargetId);
    setLoading(true);
    setError("");
    setArchitecturePayload(null);
    const approvalRequest = shouldFetchTaskOrderApproval
      ? requestJson(`/api/projects/${encodeURIComponent(approvalTargetId || projectId)}/latest-approval?scene=${encodeURIComponent(scene)}${categoryQuery}`).catch(() => null)
      : Promise.resolve(null);
    const projectApprovalRequest =
      viewerPhase === TASK_ORDER_PHASE && projectId && approvalTargetId && approvalTargetId !== projectId
        ? requestJson(`/api/projects/${encodeURIComponent(projectId)}/latest-approval?scene=${encodeURIComponent(scene)}${categoryQuery}`).catch(() => null)
        : Promise.resolve(null);
    Promise.all([
      requestJson(
        `/api/projects/${encodeURIComponent(projectId)}/document?scene=${encodeURIComponent(scene)}${categoryQuery}${refreshQuery}&include_architecture_reviews=false`,
      ),
      approvalRequest,
      projectApprovalRequest,
    ])
      .then(([documentResult, approvalResult, projectApprovalResult]) => {
        if (!alive) {
          return;
        }
        setDocumentPayload(documentResult);
        setLatestApproval(pickNewerApproval(approvalResult?.result || null, projectApprovalResult?.result || null));
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
  }, [projectId, approvalTargetId, scene, category]);

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
      if (viewerPhase === TASK_ORDER_PHASE && !selectedTaskOrder?.id) {
        setApprovalMessage("请先选择任务单后再执行审批");
        return;
      }
      const result = await requestJson("/api/approve/remote-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: viewerPhase === TASK_ORDER_PHASE ? String(projectId || "").trim() : approvalTargetId || projectId,
          taskOrderId: selectedTaskOrder?.id || "",
          category,
          scene,
        }),
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
      const acceptanceBudget = {
        requestBudgetTax: firstMeaningful(documentPayload?.budget?.summary?.request_budget, documentPayload?.budget?.summary?.project_budget),
        requestBudgetNoTax: firstMeaningful(summary.budget_year, documentPayload?.budget?.summary?.proBudget, documentPayload?.budget?.summary?.project_budget_no_tax),
        acceptBudgetTax: firstMeaningful(selectedAcceptance?.acceptTotalFeeHasTax, selectedAcceptance?.acceptTotalFee, acceptance?.acceptTotalFeeHasTax),
        acceptBudgetNoTax: firstMeaningful(selectedAcceptance?.acceptTotalFeeNoTax, selectedAcceptance?.acceptTotalFeeTax, acceptance?.acceptTotalFeeNoTax),
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
                { label: "申请项目预算(元/含税)", value: formatCurrency(acceptanceBudget.requestBudgetTax) },
                { label: "累计验收金额(元/含税)", value: formatCurrency(acceptanceBudget.acceptBudgetTax) },
                { label: "申请项目总金额(元/不含税)", value: formatCurrency(acceptanceBudget.requestBudgetNoTax) },
                { label: "累计验收金额(元/不含税)", value: formatCurrency(acceptanceBudget.acceptBudgetNoTax) },
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
              { label: "项目预算（元）", value: formatCurrency(firstMeaningful(documentPayload?.budget?.summary?.project_budget, documentPayload?.budget?.summary?.request_budget)) },
              { label: "申请项目预算(元/不含税)", value: formatCurrency(firstMeaningful(documentPayload?.budget?.summary?.request_budget, documentPayload?.budget?.summary?.project_budget_no_tax)) },
              { label: "项目年度", value: formatValue(summary.budget_year) },
              { label: "剩余金额(元/不含税)", value: formatCurrency(firstMeaningful(documentPayload?.budget?.summary?.remainingBudget, documentPayload?.budget?.summary?.remaining_budget)) },
            ]}
          />
        </article>
      </section>
    );
  }

  function renderProjectContent(sectionKey) {
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
    const supplierReasonList = (() => {
      const rawList = normalizeList(basicInfo.supplier_reason);
      if (rawList.length) {
        return rawList.map((item) => String(item || "").trim()).filter(Boolean);
      }
      const text = String(basicInfo.supplier_reason || "").trim();
      if (!text) {
        return [];
      }
      return text
        .split(/[；;。]/)
        .map((item) => item.trim())
        .filter(Boolean);
    })();
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
          <h3>关联的产品</h3>
          {normalizeList(basicInfo.related_products).length ? (
            <div className="viewer-tag-grid">
              {normalizeList(basicInfo.related_products).map((item, index) => (
                <span key={`${item}-${index}`} className="viewer-tag">{String(item)}</span>
              ))}
            </div>
          ) : (
            <p className="viewer-empty">暂无关联产品</p>
          )}
        </article>
        <article className="card viewer-card-soft">
          <h3>采购说明及原因</h3>
          <DefinitionGrid
            items={[
              { label: "选择供应商原因", value: supplierReasonList.length ? supplierReasonList.join("；") : basicInfo.supplier_reason },
              { label: "采购说明", value: basicInfo.procurement_note },
            ]}
          />
        </article>
      </div>
    );
  }

  function renderTaskOrderBusinessArchitecture() {
    const businessArchitecture = taskOrderView?.business_architecture || {};
    const businessUnitRows = normalizeList(businessArchitecture.business_units);
    const businessObjRows = normalizeList(businessArchitecture.object_rows);
    const businessRuleRows = normalizeList(businessArchitecture.rule_rows);
    const businessProcessRows = normalizeList(businessArchitecture.process_rows);
    const approvalNodeRows = normalizeList(businessArchitecture.approval_nodes);
    const businessUnitGroups = [
      {
        key: "object",
        label: "业务对象数字化",
        rows: businessObjRows.length ? businessObjRows : businessUnitRows.filter((row) => Number(row?.digitalType) === 0),
      },
      {
        key: "rule",
        label: "业务规则数字化",
        rows: businessRuleRows.length ? businessRuleRows : businessUnitRows.filter((row) => Number(row?.digitalType) === 1),
      },
      {
        key: "process",
        label: "业务过程数字化",
        rows: businessProcessRows.length ? businessProcessRows : businessUnitRows.filter((row) => Number(row?.digitalType) === 2),
      },
    ];
    const approvalNodeGroups = [
      {
        key: "removed",
        label: "审批节点消除情况",
        rows: approvalNodeRows.filter((row) => {
          const text = Object.values(row || {}).join(" ");
          return !text.includes("自动") && !text.includes("智能");
        }),
      },
      {
        key: "auto",
        label: "实现自动化/智能化审批节点情况",
        rows: approvalNodeRows.filter((row) => {
          const text = Object.values(row || {}).join(" ");
          return text.includes("自动") || text.includes("智能");
        }),
      },
    ];
    const activeBusinessUnitRows = businessUnitGroups.find((item) => item.key === taskOrderBusinessUnitTab)?.rows || businessUnitRows;
    const activeApprovalNodeRows = approvalNodeGroups.find((item) => item.key === taskOrderApprovalNodeTab)?.rows || approvalNodeRows;
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <div className="task-order-sub-tabs">
            <button
              className={`viewer-tab ${taskOrderBusinessTab === "business_units" ? "active" : ""}`}
              type="button"
              onClick={() => setTaskOrderBusinessTab("business_units")}
            >
              业务单元清单
            </button>
            <button
              className={`viewer-tab ${taskOrderBusinessTab === "approval_nodes" ? "active" : ""}`}
              type="button"
              onClick={() => setTaskOrderBusinessTab("approval_nodes")}
            >
              审批节点
            </button>
          </div>

          {taskOrderBusinessTab === "business_units" ? (
            <div className="task-order-split-panel">
              <aside className="task-order-side-tabs">
                {businessUnitGroups.map((group) => (
                  <button
                    key={group.key}
                    type="button"
                    className={`task-order-side-tab ${taskOrderBusinessUnitTab === group.key ? "active" : ""}`}
                    onClick={() => setTaskOrderBusinessUnitTab(group.key)}
                  >
                    <span>{group.label}</span>
                    <small>{group.rows.length} 条</small>
                  </button>
                ))}
              </aside>
              <div className="task-order-side-content">
                <DataTable
                  rows={activeBusinessUnitRows}
                  preferredKeys={["businessUnit", "businessFlow", "businessUnitCode", "roleName", "inputMaterial", "businessObject", "businessRuleDesc", "optimizeDesc"]}
                  emptyText="暂无业务单元清单"
                />
              </div>
            </div>
          ) : (
            <div className="task-order-split-panel">
              <aside className="task-order-side-tabs">
                {approvalNodeGroups.map((group) => (
                  <button
                    key={group.key}
                    type="button"
                    className={`task-order-side-tab ${taskOrderApprovalNodeTab === group.key ? "active" : ""}`}
                    onClick={() => setTaskOrderApprovalNodeTab(group.key)}
                  >
                    <span>{group.label}</span>
                    <small>{group.rows.length} 条</small>
                  </button>
                ))}
              </aside>
              <div className="task-order-side-content">
                <DataTable
                  rows={activeApprovalNodeRows}
                  preferredKeys={["functionName", "function_name", "removeNodeNum", "removed_nodes", "description", "desc", "remark"]}
                  emptyText="暂无审批节点数据"
                />
              </div>
            </div>
          )}
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
          <h3>人员配置</h3>
          <DataTable
            rows={staffing.rows}
            preferredKeys={["team_name", "post_name", "level_name", "sequence_role", "start_date", "end_date", "expected_days", "unit_price_tax", "unit_price", "estimated_cost_tax", "estimated_cost"]}
            emptyText="暂无人员配置"
          />
        </article>
      </div>
    );
  }

  function renderTaskOrderCostEstimation() {
    const costEstimation = taskOrderView?.cost_estimation || {};
    const currentRows = normalizeList(costEstimation.current_rows);
    const historyRows = normalizeList(costEstimation.history_rows);
    const currentNoTax = currentRows.reduce((sum, item) => sum + Number(item?.estimated_cost || 0), 0);
    const currentTax = currentRows.reduce(
      (sum, item) => sum + Number(item?.estimated_cost_tax || item?.estimated_cost * 1.06 || 0),
      0,
    );
    const historyNoTax = historyRows.reduce((sum, item) => sum + Number(item?.total_cost || 0), 0);
    const historyTax = historyRows.reduce(
      (sum, item) => sum + Number(item?.total_cost_tax || item?.total_cost * 1.06 || 0),
      0,
    );
    return (
      <div className="stack-md">
        <article className="card viewer-card-soft">
          <DefinitionGrid
            items={[
              { label: "任务单数量", value: historyRows.length || 1 },
              { label: "本次任务单下发金额(含税)", value: formatCurrency(currentTax || costEstimation.total_cost) },
              { label: "本次任务单下发金额(不含税)", value: formatCurrency(currentNoTax || costEstimation.total_cost) },
              { label: "历史任务单总金额(含税)", value: formatCurrency(historyTax || costEstimation.history_total_cost) },
              { label: "历史任务单总金额(不含税)", value: formatCurrency(historyNoTax || costEstimation.history_total_cost) },
            ]}
          />
        </article>
        <article className="card viewer-card-soft">
          <div className="task-order-sub-tabs">
            <button
              className={`viewer-tab ${taskOrderCostTab === "current" ? "active" : ""}`}
              type="button"
              onClick={() => setTaskOrderCostTab("current")}
            >
              本次任务单费用
            </button>
            <button
              className={`viewer-tab ${taskOrderCostTab === "history" ? "active" : ""}`}
              type="button"
              onClick={() => setTaskOrderCostTab("history")}
            >
              历史任务单费用
            </button>
          </div>
          {taskOrderCostTab === "current" ? (
            <DataTable
              rows={currentRows}
              preferredKeys={["post_name", "level_name", "sequence_role", "start_date", "end_date", "expected_days", "unit_price_tax", "unit_price", "estimated_cost_tax", "estimated_cost"]}
              emptyText="暂无本次任务费用"
            />
          ) : (
            <DataTable
              rows={historyRows}
              preferredKeys={["task_code", "task_name", "supplier_name", "resource_pool", "start_date", "end_date", "first_warning_time", "task_description", "status", "total_cost"]}
              emptyText="暂无历史任务费用"
            />
          )}
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
      <div className="stack-sm">
        {requirementItems.map((item) => (
            <article key={item.label} className="card viewer-card-soft task-order-tech-item">
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

  function renderTaskOrderTechnicalRequirementsV2() {
    const technicalRequirements = taskOrderView?.technical_requirements || {};
    const requirementItems = [
      { label: "系统功能要求", value: technicalRequirements.system_function },
      { label: "系统架构要求", value: technicalRequirements.system_architecture },
      { label: "系统集成与接口要求", value: technicalRequirements.integration_requirements },
      { label: "数据库要求", value: technicalRequirements.database_requirements },
      { label: "性能要求", value: technicalRequirements.performance_requirements },
      { label: "安全性要求", value: technicalRequirements.security_requirements },
      { label: "扩展要求", value: technicalRequirements.scalability_requirements },
      { label: "技术栈要求", value: technicalRequirements.tech_stack_requirements },
      { label: "前端设计要求", value: technicalRequirements.frontend_requirements },
      { label: "兼容性要求", value: technicalRequirements.compatibility_requirements },
      { label: "质量要求", value: technicalRequirements.quality_requirements },
      { label: "进度要求", value: technicalRequirements.schedule_requirements },
      { label: "交接要求", value: technicalRequirements.handover_requirements },
      { label: "交接物料", value: technicalRequirements.handover_items },
      { label: "项目验收条件", value: technicalRequirements.acceptance_criteria },
    ];
    return (
      <div className="stack-sm">
        {requirementItems.map((item) => (
          <article key={item.label} className="card viewer-card-soft task-order-tech-item">
            <h3>{item.label}</h3>
            <div className="task-order-tech-value">{item.value || "待补充"}</div>
            <div className="task-order-tech-counter">{String(item.value || "").length} / 1000</div>
          </article>
        ))}
        {normalizeList(technicalRequirements.spec_rows).length ? (
          <article className="card viewer-card-soft">
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
    const rows = filterByAcceptId(activeTab === "contracts" ? acceptance.contract_list : acceptance.task_list);
    const preferredKeys = activeTab === "contracts"
      ? ["acceptId", "acceptName", "contractName", "contractNo", "contractStatusName", "acceptStatusName", "supplierName", "amount"]
      : ["acceptId", "acceptName", "taskName", "taskNo", "taskStatusName", "acceptStatusName", "ownerName", "supplierName"];
    return <DataTable rows={rows} preferredKeys={preferredKeys} emptyText="暂无验收范围数据" />;
  }

  function renderAcceptanceStage() {
    return (
      <div className="stack-md">
        <DefinitionGrid
          items={[
            { label: "验收单数量", value: acceptanceInfoList.length || normalizeList(acceptance.acceptance_ids).length },
            { label: "任务单数量", value: normalizeList(acceptance.task_list).length },
            { label: "合同数量", value: normalizeList(acceptance.contract_list).length },
            { label: "任务单验收", value: normalizeList(acceptance.task_acceptance_list).length },
            { label: "合同验收", value: normalizeList(acceptance.contract_acceptance_list).length },
            { label: "备证数量", value: normalizeList(acceptance.deliverables).length },
          ]}
        />
        <article className="card viewer-card-soft">
          <div className="section-head">
            <div>
              <h3>验收单列表</h3>
              <p className="category-meta">先进入验收单，再查看对应的验收范围、验收明细和上传备证。</p>
            </div>
            {selectedAcceptId ? (
              <button className="ghost-button" type="button" onClick={() => updateAcceptId("")}>
                返回项目验收详情
              </button>
            ) : null}
          </div>
          {acceptanceInfoList.length ? (
            <div className="stack-sm">
              {acceptanceInfoList.map((item, index) => {
                const acceptId = String(item?.acceptId || item?.id || `accept-${index}`);
                const isActive = acceptId === selectedAcceptId;
                return (
                  <article key={acceptId} className="card viewer-card-soft">
                    <DefinitionGrid
                      items={[
                        { label: "验收单ID", value: acceptId },
                        { label: "验收单名称", value: item?.acceptName || item?.name || item?.acceptTitle },
                        { label: "验收状态", value: item?.acceptStatusName || item?.statusName || item?.acceptStatus },
                        { label: "验收类型", value: item?.acceptTypeName || item?.acceptType },
                      ]}
                    />
                    <div className="viewer-actions">
                      <button
                        className={isActive ? "ghost-button" : "primary-button"}
                        type="button"
                        onClick={() => {
                          updateAcceptId(acceptId);
                          setActiveSection("acceptance_detail");
                        }}
                      >
                        {isActive ? "当前验收单" : "进入验收单"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <p className="viewer-empty">暂无验收单列表数据</p>
          )}
        </article>
      </div>
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
      return renderTaskOrderTechnicalRequirementsV2();
    }
    if (activeSection === "acceptance_scope") {
      return renderAcceptanceScope();
    }
    if (activeSection === "acceptance_stage") {
      return renderAcceptanceStage();
    }
    if (activeSection === "acceptance_detail") {
      return renderAcceptanceDetail();
    }
    if (activeSection === "acceptance_deliverables") {
      return renderAcceptanceDeliverables();
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
              <>
                <span className="viewer-pill">任务单数量: {taskOrders.length}</span>
                <button className="primary-button" type="button" onClick={runApproval} disabled={approvalBusy}>
                  {approvalBusy ? "审批执行中..." : "执行远程审批"}
                </button>
              </>
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

        {viewerPhase !== "initiation" && approvalMessage ? (
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

        {viewerPhase !== "initiation" && latestApproval ? (
          <section className="card viewer-card-soft">
            <p className="panel-label">Latest Approval</p>
            <DefinitionGrid
              items={[
                { label: "结论", value: latestApproval.decision },
                { label: "摘要", value: latestApproval.summary },
                { label: "分类", value: latestApproval.resolved_category || latestApproval.category },
              ]}
            />
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
          <div className="viewer-layout">{renderBody()}</div>
        </section>
      </main>
    </PageLayout>
  );
}
