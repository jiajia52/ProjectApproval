import { Fragment, useEffect, useState } from "react";
import PageLayout from "../../components/PageLayout";
import { buildUiUrl, normalizeScene, projectDisplayValue, requestJson } from "../../api";

const initialFilters = {
  project_name: "",
  project_code: "",
  task_order_no: "",
  task_order_name: "",
  supplier: "",
  project_manager: "",
  domain: "",
  department: "",
  project_category: "",
  project_type: "",
  fixed_project: "",
  project_status: "",
  flow_status: "",
  task_order_status: "",
};

function buildProjectListStatus(result) {
  const currentCount = (result.projects || []).length;
  const filteredCount = result.filtered_total ?? currentCount;
  const sourceLabel = result.source === "cache" ? "本地缓存" : "远程接口";
  const warning = result.warning ? ` ${result.warning}` : "";
  const extra = result.page_source || result.total_source
    ? ` 当前页来源: ${result.page_source || sourceLabel}，总数来源: ${result.total_source || sourceLabel}。`
    : "";
  return `数据来源: ${sourceLabel}。总数 ${result.total || 0}，当前页 ${currentCount}，筛选后 ${filteredCount}。${extra}${warning}`;
}

function optionLabel(option) {
  return option?.label || option?.name || option?.value || "";
}

function optionValue(option) {
  return option?.label || option?.name || option?.value || "";
}

function formatRate(value) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "-";
  }
  if (text.includes("%")) {
    return text;
  }
  const numeric = Number(text);
  if (!Number.isFinite(numeric)) {
    return text;
  }
  return `${numeric}%`;
}

function uniqueOptions(items, ...keys) {
  const seen = new Set();
  return items
    .map((item) => projectDisplayValue(item, ...keys))
    .filter((value) => {
      const text = String(value || "").trim();
      if (!text || seen.has(text)) {
        return false;
      }
      seen.add(text);
      return true;
    });
}

function buildOptionItems(items, ...keys) {
  return uniqueOptions(items, ...keys).map((item) => ({ label: item, value: item, name: item }));
}

export default function AcceptanceApprovalPage() {
  const activeScene = normalizeScene("acceptance");
  const isAcceptanceScene = activeScene === "acceptance";
  const isTaskOrderScene = activeScene === "task_order";
  const [filters, setFilters] = useState(initialFilters);
  const [filterOptions, setFilterOptions] = useState({
    domain: [],
    project_category: [],
    project_type: [],
    project_status: [],
    task_order_status: [],
    supplier: [],
  });
  const [projects, setProjects] = useState([]);
  const [statusText, setStatusText] = useState("等待查询。");
  const [pageNum, setPageNum] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [filteredTotal, setFilteredTotal] = useState(0);
  const [expandedProjectId, setExpandedProjectId] = useState("");
  const [acceptanceInfoMap, setAcceptanceInfoMap] = useState({});
  const [acceptanceInfoLoading, setAcceptanceInfoLoading] = useState({});

  const totalPages = Math.max(1, Math.ceil((total || 0) / Math.max(pageSize, 1)));

  async function loadProjects(nextPage = pageNum, nextFilters = filters) {
    const params = new URLSearchParams({
      page_num: String(nextPage),
      page_size: String(pageSize),
      scene: activeScene,
    });
    Object.entries(nextFilters).forEach(([key, value]) => {
      if (value) {
        params.set(key, value);
      }
    });
    const result = await requestJson(`/api/projects?${params.toString()}`);
    setProjects(result.projects || []);
    setTotal(Number(result.total || 0));
    setFilteredTotal(Number(result.filtered_total ?? (result.projects || []).length));
    setPageNum(nextPage);
    setStatusText(buildProjectListStatus(result));
  }

  useEffect(() => {
    let alive = true;
    Promise.all([
      requestJson(`/api/project-filter-options?scene=${encodeURIComponent(activeScene)}`),
      requestJson(`/api/projects?page_num=1&page_size=${pageSize}&scene=${encodeURIComponent(activeScene)}`),
    ])
      .then(([optionsPayload, projectsPayload]) => {
        if (!alive) {
          return;
        }
        setFilterOptions({
          domain: optionsPayload.items?.domain || [],
          project_category: optionsPayload.items?.project_category || [],
          project_type: optionsPayload.items?.project_type || [],
          project_status: optionsPayload.items?.project_status || [],
          task_order_status: optionsPayload.items?.task_order_status || [],
          supplier: optionsPayload.items?.supplier || [],
        });
        setProjects(projectsPayload.projects || []);
        setTotal(Number(projectsPayload.total || 0));
        setFilteredTotal(Number(projectsPayload.filtered_total ?? (projectsPayload.projects || []).length));
        setStatusText(buildProjectListStatus(projectsPayload));
      })
      .catch((error) => {
        if (alive) {
          setStatusText(error.message || "加载列表失败");
        }
      });
    return () => {
      alive = false;
    };
  }, [activeScene, pageSize]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function resetFilters() {
    setFilters(initialFilters);
    loadProjects(1, initialFilters).catch((error) => setStatusText(error.message || "重置失败"));
  }

  function openViewer(projectId, acceptId = "", taskOrderId = "") {
    window.open(
      buildUiUrl(`/project/${encodeURIComponent(projectId)}`, { scene: activeScene, acceptId, taskOrderId }),
      "_blank",
      "noopener,noreferrer",
    );
  }

  function exportTaskOrders() {
    const headers = [
      "序号",
      "任务单编号",
      "任务单名称",
      "供应商",
      "项目名称",
      "申请总预算",
      "申请年度预算",
      "归属领域",
      "开始时间",
      "结束时间",
      "任务单审批通过时间",
      "金额首次预警时间",
      "任务总人天",
      "任务单下发金额（含税）",
      "任务单下发金额（不含税）",
      "实际投入人天",
      "任务单验收金额（含税）",
      "任务单验收金额（不含税）",
      "任务单执行率",
      "任务单状态",
    ];
    const rows = projects.map((project, index) => [
      (pageNum - 1) * pageSize + index + 1,
      projectDisplayValue(project, "taskOrderNo", "taskSerialCode", "taskNo", "serialNo", "taskCode") || "-",
      projectDisplayValue(project, "taskOrderName", "taskName", "name") || "-",
      projectDisplayValue(project, "supplierName", "supplier", "vendorName") || "-",
      projectDisplayValue(project, "projectName", "projectInfoName") || "-",
      projectDisplayValue(project, "applyTotalBudget", "applyBudgetTotal", "applyBudget") || "-",
      projectDisplayValue(project, "applyYearBudget", "applyBudgetYear") || "-",
      projectDisplayValue(project, "domainName", "belongTeamName", "belongDomainName", "domain") || "-",
      projectDisplayValue(project, "startTime", "planStartTime", "startDate", "beginTime", "taskStartTime") || "-",
      projectDisplayValue(project, "endTime", "planEndTime", "endDate", "finishTime") || "-",
      projectDisplayValue(project, "approvalPassTime", "taskAduitTime", "approvalTime", "approveTime") || "-",
      projectDisplayValue(project, "amountWarningTime", "taskEndTime", "firstWarningTime", "firstWarnTime") || "-",
      projectDisplayValue(project, "taskTotalManday", "taskCostDay", "taskManday", "totalManDay") || "-",
      projectDisplayValue(project, "issueAmountTax", "taskAmountTax", "assignAmountTax", "taskIssueAmountTax") || "-",
      projectDisplayValue(project, "issueAmountNoTax", "taskAmountNoTax", "assignAmountNoTax", "taskIssueAmountNoTax") || "-",
      projectDisplayValue(project, "actualManday", "actualCostDay", "realManday", "actualManDay") || "-",
      projectDisplayValue(project, "acceptanceAmountTax", "settlementAmount", "taskAcceptAmountTax", "acceptAmountTax") || "-",
      projectDisplayValue(project, "acceptanceAmountNoTax", "settlementAmountNoTax", "acceptanceCosts", "taskAcceptAmountNoTax", "acceptAmountNoTax") || "-",
      formatRate(projectDisplayValue(project, "executionRate", "taskExecuteRate", "taskExecutionRate", "executeRate")),
      projectDisplayValue(project, "taskOrderStatus", "taskStatusName", "taskOrderStatusName", "statusName", "taskStatus") || "-",
    ]);
    const csv = [headers, ...rows]
      .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, "\"\"")}"`).join(","))
      .join("\n");
    const blob = new Blob([`\ufeff${csv}`], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `task-orders-page-${pageNum}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  }

  async function toggleAcceptanceProject(projectId) {
    const nextProjectId = String(projectId || "").trim();
    if (!nextProjectId) {
      return;
    }
    if (expandedProjectId === nextProjectId) {
      setExpandedProjectId("");
      return;
    }
    setExpandedProjectId(nextProjectId);
    if (acceptanceInfoMap[nextProjectId] || acceptanceInfoLoading[nextProjectId]) {
      return;
    }
    setAcceptanceInfoLoading((current) => ({ ...current, [nextProjectId]: true }));
    try {
      const result = await requestJson(`/api/projects/${encodeURIComponent(nextProjectId)}/acceptance-info-list`);
      setAcceptanceInfoMap((current) => ({ ...current, [nextProjectId]: result.items || [] }));
    } catch {
      setAcceptanceInfoMap((current) => ({ ...current, [nextProjectId]: [] }));
    } finally {
      setAcceptanceInfoLoading((current) => ({ ...current, [nextProjectId]: false }));
    }
  }

  function renderAcceptanceStageRows(project) {
    const projectId = String(project?.id || "");
    const rows = acceptanceInfoMap[projectId] || [];
    if (acceptanceInfoLoading[projectId]) {
      return <p className="viewer-empty">验收单加载中...</p>;
    }
    if (!rows.length) {
      return <p className="viewer-empty">暂无验收阶段数据</p>;
    }
    return (
      <table className="compact-table acceptance-stage-table">
        <thead>
          <tr>
            <th>序号</th>
            <th>阶段名称</th>
            <th>申请验收金额(元/含税)</th>
            <th>申请验收金额(元/不含税)</th>
            <th>阶段预算执行率</th>
            <th>验收申请提交日期</th>
            <th>验收审批通过日期</th>
            <th>流程状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item, index) => {
            const acceptId = projectDisplayValue(item, "acceptId", "id");
            return (
              <tr key={acceptId || `${index}`}>
                <td>{index + 1}</td>
                <td>{projectDisplayValue(item, "acceptName", "acceptStageName", "stageName", "name") || "-"}</td>
                <td>{projectDisplayValue(item, "acceptApplyAmountTax", "applyAcceptAmountTax", "acceptTotalFeeHasTax", "acceptMoneyTax") || "-"}</td>
                <td>{projectDisplayValue(item, "acceptApplyAmount", "applyAcceptAmount", "acceptTotalFeeNoTax", "acceptMoneyNoTax") || "-"}</td>
                <td>{formatRate(projectDisplayValue(item, "budgetProcess", "budgetExecutionRate", "executionRate", "progressRate"))}</td>
                <td>{projectDisplayValue(item, "applyTime", "submitTime", "acceptApplyDate", "createTime") || "-"}</td>
                <td>{projectDisplayValue(item, "approvalTime", "approveTime", "passTime", "acceptPassTime") || "-"}</td>
                <td>{projectDisplayValue(item, "acceptStatusName", "flowStatusName", "statusName", "processStatusName", "status") || "-"}</td>
                <td>
                  <button className="table-button acceptance-action" type="button" onClick={() => openViewer(projectId, acceptId)}>
                    查看
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  function renderAcceptanceTable() {
    return (
      <table className="compact-table acceptance-table">
        <thead>
          <tr>
            <th></th>
            <th>序号</th>
            <th>项目名称</th>
            <th>项目编码</th>
            <th>项目经理</th>
            <th>领域</th>
            <th>业务类别</th>
            <th>业务子类</th>
            <th>申请项目预算</th>
            <th>申请项目年度预算</th>
            <th>累计验收金额（元/含税）</th>
            <th>累计验收金额（元/不含税）</th>
            <th>预算执行率</th>
            <th>项目状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project, index) => {
            const projectId = String(project.id || "");
            const isExpanded = expandedProjectId === projectId;
            return (
              <Fragment key={project.id || `${index}`}>
                <tr>
                  <td>
                    <button className="acceptance-expand-button" type="button" onClick={() => toggleAcceptanceProject(projectId)}>
                      {isExpanded ? "-" : "+"}
                    </button>
                  </td>
                  <td>{(pageNum - 1) * pageSize + index + 1}</td>
                  <td>{projectDisplayValue(project, "projectName", "name", "id")}</td>
                  <td>{projectDisplayValue(project, "projectCode", "serialNo") || "-"}</td>
                  <td>{projectDisplayValue(project, "managerName", "projectManagerName", "projectManager", "projectLeaderName", "projectLeader") || "-"}</td>
                  <td>{projectDisplayValue(project, "domainName", "belongTeamName", "businessDomainName") || "-"}</td>
                  <td>{projectDisplayValue(project, "businessCategoryName", "projectClassifyParentName", "projectCategoryName") || "-"}</td>
                  <td>{projectDisplayValue(project, "businessSubcategoryName", "projectClassifyName", "projectTypeName") || "-"}</td>
                  <td>{projectDisplayValue(project, "applyTotalBudget", "applyBudget", "requestBudget", "projectBudget", "proBudget") || "-"}</td>
                  <td>{projectDisplayValue(project, "applyYearBudget", "projectYearBudget", "proBudgetYear", "yearBudget") || "-"}</td>
                  <td>{projectDisplayValue(project, "acceptanceAmountTax", "acceptMoneyTax", "acceptanceTaxIncludedAmount", "totalAcceptAmountTax") || "-"}</td>
                  <td>{projectDisplayValue(project, "acceptanceAmount", "acceptMoneyNoTax", "acceptanceWithoutTaxAmount", "totalAcceptAmount") || "-"}</td>
                  <td>{formatRate(projectDisplayValue(project, "budgetExecutionRate", "executeRate", "progressRate", "budgetRate"))}</td>
                  <td>{projectDisplayValue(project, "projectStatusName", "projectStatus") || "-"}</td>
                  <td>
                    <button className="table-button acceptance-action" type="button" onClick={() => toggleAcceptanceProject(projectId)}>
                      验收详情
                    </button>
                  </td>
                </tr>
                {isExpanded ? (
                  <tr className="acceptance-stage-row">
                    <td colSpan={15}>
                      {renderAcceptanceStageRows(project)}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    );
  }

  function renderDefaultTable() {
    return (
      <table className="compact-table">
        <thead>
          <tr>
            <th>项目名称</th>
            <th>项目编码</th>
            <th>归属领域</th>
            <th>部门</th>
            <th>项目经理</th>
            <th>项目类型</th>
            <th>是否固定项目</th>
            <th>项目状态</th>
            <th>流程状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project, index) => (
            <tr key={project.id || `${index}`}>
              <td>{projectDisplayValue(project, "projectName", "name", "id")}</td>
              <td>{projectDisplayValue(project, "projectCode", "serialNo") || "-"}</td>
              <td>{projectDisplayValue(project, "domainName", "belongTeamName") || "-"}</td>
              <td>{projectDisplayValue(project, "departmentName", "belongDepartmentName") || "-"}</td>
              <td>{projectDisplayValue(project, "managerName", "projectManagerName", "projectLeaderName") || "-"}</td>
              <td>{projectDisplayValue(project, "projectCategoryName", "projectFeeTypeName", "projectTypeName") || "-"}</td>
              <td>{projectDisplayValue(project, "fixedProjectLabel") || "-"}</td>
              <td>{projectDisplayValue(project, "projectStatusName", "projectStatus") || "-"}</td>
              <td>{projectDisplayValue(project, "flowStatusDisplay", "flowStatusName", "flowStatus") || "-"}</td>
              <td>
                <button className="table-button" type="button" onClick={() => openViewer(project.id)}>
                  {isTaskOrderScene ? "查看任务单" : "查看项目"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  function renderTaskOrderFilters() {
    const domainOptions = uniqueOptions(projects, "domainName", "belongTeamName", "belongDomainName", "domain");
    const supplierOptions = filterOptions.supplier?.length
      ? filterOptions.supplier
      : uniqueOptions(projects, "supplierName", "supplier", "vendorName").map((item) => ({ label: item, value: item, name: item }));
    const statusOptions = filterOptions.task_order_status?.length
      ? filterOptions.task_order_status
      : uniqueOptions(projects, "taskStatusName", "taskOrderStatus", "taskOrderStatusName", "statusName", "taskStatus").map((item) => ({ label: item, value: item, name: item }));
    return (
      <>
        <div className="task-order-filter-hero">
          <div className="task-order-filter-grid">
            <label className="task-order-filter-field">
              <span>任务单编号</span>
              <input
                value={filters.task_order_no}
                onChange={(event) => updateFilter("task_order_no", event.target.value)}
                placeholder="请输入"
              />
            </label>
            <label className="task-order-filter-field">
              <span>任务单名称</span>
              <input
                value={filters.task_order_name}
                onChange={(event) => updateFilter("task_order_name", event.target.value)}
                placeholder="请输入"
              />
            </label>
            <label className="task-order-filter-field">
              <span>供应商</span>
              <select value={filters.supplier} onChange={(event) => updateFilter("supplier", event.target.value)}>
                <option value="">请选择</option>
                {supplierOptions.map((item, index) => (
                  <option key={`${optionValue(item)}-${index}`} value={optionValue(item)}>
                    {optionLabel(item)}
                  </option>
                ))}
              </select>
            </label>
            <label className="task-order-filter-field">
              <span>项目名称</span>
              <input
                value={filters.project_name}
                onChange={(event) => updateFilter("project_name", event.target.value)}
                placeholder="请输入"
              />
            </label>
            <label className="task-order-filter-field">
              <span>归属领域</span>
              <select value={filters.domain} onChange={(event) => updateFilter("domain", event.target.value)}>
                <option value="">请选择</option>
                {domainOptions.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className="task-order-filter-field">
              <span>任务单状态</span>
              <select value={filters.task_order_status} onChange={(event) => updateFilter("task_order_status", event.target.value)}>
                <option value="">请选择</option>
                {statusOptions.map((item) => (
                  <option key={optionValue(item)} value={optionValue(item)}>{optionLabel(item)}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="task-order-filter-actions">
            <button className="ghost-button" type="button" onClick={resetFilters}>重置</button>
            <button className="primary-button" type="button" onClick={() => loadProjects(1)}>查询</button>
          </div>
        </div>
      </>
    );
  }

  function renderTaskOrderTable() {
    return (
      <table className="compact-table task-order-management-table">
        <thead>
          <tr>
            <th>序号</th>
            <th>任务单编号</th>
            <th>任务单名称</th>
            <th>供应商</th>
            <th>项目名称</th>
            <th>申请总预算</th>
            <th>申请年度预算</th>
            <th>归属领域</th>
            <th>开始时间</th>
            <th>结束时间</th>
            <th>任务单审批通过时间</th>
            <th>金额首次预警时间</th>
            <th>任务总人天</th>
            <th>任务单下发金额（含税）</th>
            <th>任务单下发金额（不含税）</th>
            <th>实际投入人天</th>
            <th>任务单验收金额（含税）</th>
            <th>任务单验收金额（不含税）</th>
            <th>任务单执行率</th>
            <th>任务单状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project, index) => {
            const projectId = projectDisplayValue(
              project,
              "projectId",
              "projectBudgetId",
              "projectEstablishmentId",
              "projectInfoId",
              "id",
            );
            const taskOrderId = projectDisplayValue(project, "id", "taskId", "taskOrderId");
            return (
              <tr key={taskOrderId || `${index}`}>
                <td>{(pageNum - 1) * pageSize + index + 1}</td>
                <td>{projectDisplayValue(project, "taskOrderNo", "taskSerialCode", "taskNo", "serialNo", "taskCode") || "-"}</td>
                <td>{projectDisplayValue(project, "taskOrderName", "taskName", "name") || "-"}</td>
                <td>{projectDisplayValue(project, "supplierName", "supplier", "vendorName") || "-"}</td>
                <td>{projectDisplayValue(project, "projectName", "projectInfoName") || "-"}</td>
                <td>{projectDisplayValue(project, "applyTotalBudget", "applyBudgetTotal", "applyBudget") || "-"}</td>
                <td>{projectDisplayValue(project, "applyYearBudget", "applyBudgetYear") || "-"}</td>
                <td>{projectDisplayValue(project, "domainName", "belongTeamName", "belongDomainName", "domain") || "-"}</td>
                <td>{projectDisplayValue(project, "startTime", "planStartTime", "startDate", "beginTime", "taskStartTime") || "-"}</td>
                <td>{projectDisplayValue(project, "endTime", "planEndTime", "endDate", "finishTime", "taskEndTime") || "-"}</td>
                <td>{projectDisplayValue(project, "approvalPassTime", "taskAduitTime", "approvalTime", "approveTime") || "-"}</td>
                <td>{projectDisplayValue(project, "amountWarningTime", "taskEndTime", "firstWarningTime", "firstWarnTime") || "-"}</td>
                <td>{projectDisplayValue(project, "taskTotalManday", "taskCostDay", "taskManday", "totalManDay") || "-"}</td>
                <td>{projectDisplayValue(project, "issueAmountTax", "taskAmountTax", "assignAmountTax", "taskIssueAmountTax") || "-"}</td>
                <td>{projectDisplayValue(project, "issueAmountNoTax", "taskAmountNoTax", "assignAmountNoTax", "taskIssueAmountNoTax") || "-"}</td>
                <td>{projectDisplayValue(project, "actualManday", "actualCostDay", "realManday", "actualManDay") || "-"}</td>
                <td>{projectDisplayValue(project, "acceptanceAmountTax", "settlementAmount", "taskAcceptAmountTax", "acceptAmountTax") || "-"}</td>
                <td>{projectDisplayValue(project, "acceptanceAmountNoTax", "settlementAmountNoTax", "acceptanceCosts", "taskAcceptAmountNoTax", "acceptAmountNoTax") || "-"}</td>
                <td>{formatRate(projectDisplayValue(project, "executionRate", "taskExecuteRate", "taskExecutionRate", "executeRate"))}</td>
                <td>{projectDisplayValue(project, "taskOrderStatus", "taskStatusName", "taskOrderStatusName", "statusName", "taskStatus") || "-"}</td>
                <td>
                  <button className="table-button acceptance-action" type="button" onClick={() => openViewer(projectId || taskOrderId, "", taskOrderId)}>
                    详情
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }

  const acceptanceDomainOptions = filterOptions.domain?.length
    ? filterOptions.domain
    : buildOptionItems(projects, "domainName", "belongTeamName", "belongDomainName", "domain");
  const acceptanceCategoryOptions = filterOptions.project_category?.length
    ? filterOptions.project_category
    : buildOptionItems(projects, "projectCategoryName", "businessCategoryName", "projectFeeTypeName");
  const acceptanceTypeOptions = filterOptions.project_type?.length
    ? filterOptions.project_type
    : buildOptionItems(projects, "projectTypeName", "businessSubcategoryName", "projectFeeTypeName");
  const acceptanceStatusOptions = filterOptions.project_status?.length
    ? filterOptions.project_status
    : buildOptionItems(projects, "projectStatusName", "projectStatus");

  return (
    <PageLayout wide scene={activeScene} section="projects">
      {isAcceptanceScene ? (
        <header className="acceptance-list-header card">
          <div className="acceptance-list-titlebar">
            <div>
              <p className="eyebrow">Acceptance</p>
              <h1>验收管理</h1>
            </div>
          </div>
        </header>
      ) : isTaskOrderScene ? (
        <header className="acceptance-list-header card">
          <div className="acceptance-list-titlebar">
            <div>
              <p className="eyebrow">Task Order</p>
              <h1>任务单管理</h1>
            </div>
          </div>
        </header>
      ) : (
        <header className="hero">
          <div>
            <p className="eyebrow">Project List</p>
            <h1>真实项目列表</h1>
            <p className="hero-copy">列表页负责筛选、分页和打开项目详情，详情在新标签页展示。</p>
          </div>
          <div className="hero-panel">
            <p className="panel-label">Workspace</p>
            <h2>列表与配置分离</h2>
            <p className="hero-copy">列表页仅保留查询和跳转能力，配置操作放在独立页面。</p>
          </div>
        </header>
      )}

      <main className="grid">
        <section className={`card span-full ${isAcceptanceScene ? "acceptance-list-card" : ""}`}>
          <div className="section-head">
            <div>
              <p className="panel-label">{isAcceptanceScene ? "Acceptance Projects" : isTaskOrderScene ? "Task Orders" : "Projects"}</p>
              <h2>{isAcceptanceScene ? "项目验收列表" : isTaskOrderScene ? "任务单列表" : "项目列表"}</h2>
            </div>
            <div className="button-row">
              {isTaskOrderScene ? (
                <button className="ghost-button task-order-export-button" type="button" onClick={exportTaskOrders}>
                  导出任务单数据
                </button>
              ) : null}
              <button className="ghost-button" type="button" onClick={() => loadProjects(pageNum)}>
                刷新列表
              </button>
            </div>
          </div>

          {isTaskOrderScene ? renderTaskOrderFilters() : (
            <div className={isAcceptanceScene ? "acceptance-filter-grid" : "project-toolbar-row"}>
              <input value={filters.project_name} onChange={(event) => updateFilter("project_name", event.target.value)} placeholder="项目名称" />
              {isAcceptanceScene ? (
              <>
                <input value={filters.project_code} onChange={(event) => updateFilter("project_code", event.target.value)} placeholder="项目编码" />
                <input value={filters.project_manager} onChange={(event) => updateFilter("project_manager", event.target.value)} placeholder="项目经理" />
                <select value={filters.domain} onChange={(event) => updateFilter("domain", event.target.value)}>
                  <option value="">归属领域</option>
                  {acceptanceDomainOptions.map((item, index) => (
                    <option key={`${optionValue(item)}-${index}`} value={optionValue(item)}>
                      {optionLabel(item)}
                    </option>
                  ))}
                </select>
                <select value={filters.project_category} onChange={(event) => updateFilter("project_category", event.target.value)}>
                  <option value="">业务类别</option>
                  {acceptanceCategoryOptions.map((item, index) => (
                    <option key={`${optionValue(item)}-${index}`} value={optionValue(item)}>
                      {optionLabel(item)}
                    </option>
                  ))}
                </select>
                <select value={filters.project_type} onChange={(event) => updateFilter("project_type", event.target.value)}>
                  <option value="">业务子类 / 项目类型</option>
                  {acceptanceTypeOptions.map((item, index) => (
                    <option key={`${optionValue(item)}-${index}`} value={optionValue(item)}>
                      {optionLabel(item)}
                    </option>
                  ))}
                </select>
                <select value={filters.project_status} onChange={(event) => updateFilter("project_status", event.target.value)}>
                  <option value="">项目状态</option>
                  {acceptanceStatusOptions.map((item, index) => (
                    <option key={`${optionValue(item)}-${index}`} value={optionValue(item)}>
                      {optionLabel(item)}
                    </option>
                  ))}
                </select>
                <div className="acceptance-filter-actions">
                  <button className="ghost-button" type="button" onClick={resetFilters}>重置</button>
                  <button className="primary-button" type="button" onClick={() => loadProjects(1)}>查询</button>
                </div>
              </>
              ) : (
              <>
                <input value={filters.project_type} onChange={(event) => updateFilter("project_type", event.target.value)} placeholder="项目类型" />
                <select value={filters.fixed_project} onChange={(event) => updateFilter("fixed_project", event.target.value)}>
                  <option value="">是否固定项目</option>
                  <option value="true">是</option>
                  <option value="false">否</option>
                </select>
                <select value={filters.project_status} onChange={(event) => updateFilter("project_status", event.target.value)}>
                  <option value="">项目状态</option>
                  {filterOptions.project_status.map((item, index) => (
                    <option key={`${optionValue(item)}-${index}`} value={optionValue(item)}>
                      {optionLabel(item)}
                    </option>
                  ))}
                </select>
                <input value={filters.flow_status} onChange={(event) => updateFilter("flow_status", event.target.value)} placeholder="流程状态" />
                <input
                  className="compact-control"
                  type="number"
                  min="1"
                  max="200"
                  value={pageSize}
                  onChange={(event) => setPageSize(Number(event.target.value || 20))}
                  placeholder="每页数量"
                />
                <button className="primary-button" type="button" onClick={() => loadProjects(1)}>查询项目</button>
                </>
              )}
            </div>
          )}

          <div className="list-toolbar-meta">
            <div className="category-meta">{statusText}</div>
            {isAcceptanceScene || isTaskOrderScene ? (
              <div className="acceptance-page-size">
                <span>每页</span>
                <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value || 20))}>
                  {[20, 50, 100].map((size) => (
                    <option key={size} value={size}>{size}</option>
                  ))}
                </select>
                <span>条</span>
              </div>
            ) : null}
          </div>

          <div className="table-wrap">
            {isAcceptanceScene ? renderAcceptanceTable() : isTaskOrderScene ? renderTaskOrderTable() : renderDefaultTable()}
          </div>

          <div className="pagination-bar pagination-bar-bottom">
            <button className="ghost-button" type="button" disabled={pageNum <= 1} onClick={() => loadProjects(pageNum - 1)}>
              上一页
            </button>
            <span className="pagination-info">
              第 {pageNum} 页 / 共 {totalPages} 页{filteredTotal ? ` / 筛选后 ${filteredTotal}` : ""}
            </span>
            <button className="ghost-button" type="button" disabled={pageNum >= totalPages} onClick={() => loadProjects(pageNum + 1)}>
              下一页
            </button>
          </div>
        </section>
      </main>
    </PageLayout>
  );
}
