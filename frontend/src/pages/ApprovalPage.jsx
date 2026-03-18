import { useEffect, useState } from "react";
import PageLayout from "../components/PageLayout";
import { buildUiUrl, projectDisplayValue, requestJson } from "../api";

const initialFilters = {
  project_name: "",
  project_type: "",
  fixed_project: "",
  project_status: "",
  flow_status: "",
};

function buildProjectListStatus(result) {
  const currentCount = (result.projects || []).length;
  const filteredCount = result.filtered_total ?? currentCount;
  const sourceLabel = result.source === "cache" ? "本地缓存" : "远程接口";
  const warning = result.warning ? ` ${result.warning}` : "";
  return `数据来源: ${sourceLabel}。总数 ${result.total || 0}，当前页 ${currentCount}，筛选后 ${filteredCount}。${warning}`;
}

export default function ApprovalPage() {
  const [filters, setFilters] = useState(initialFilters);
  const [statusOptions, setStatusOptions] = useState([]);
  const [projects, setProjects] = useState([]);
  const [statusText, setStatusText] = useState("等待查询。");
  const [pageNum, setPageNum] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [filteredTotal, setFilteredTotal] = useState(0);

  const totalPages = Math.max(1, Math.ceil((total || 0) / Math.max(pageSize, 1)));

  async function loadProjects(nextPage = pageNum) {
    const params = new URLSearchParams({
      page_num: String(nextPage),
      page_size: String(pageSize),
    });
    Object.entries(filters).forEach(([key, value]) => {
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
    Promise.all([requestJson("/api/project-status-options"), requestJson(`/api/projects?page_num=1&page_size=${pageSize}`)])
      .then(([optionsPayload, projectsPayload]) => {
        if (!alive) {
          return;
        }
        setStatusOptions(optionsPayload.items || []);
        setProjects(projectsPayload.projects || []);
        setTotal(Number(projectsPayload.total || 0));
        setFilteredTotal(Number(projectsPayload.filtered_total ?? (projectsPayload.projects || []).length));
        setStatusText(buildProjectListStatus(projectsPayload));
      })
      .catch((error) => {
        if (alive) {
          setStatusText(error.message);
        }
      });
    return () => {
      alive = false;
    };
  }, [pageSize]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function openViewer(projectId) {
    window.open(buildUiUrl(`/project/${encodeURIComponent(projectId)}`), "_blank", "noopener,noreferrer");
  }

  return (
    <PageLayout wide>
      <header className="hero">
        <div>
          <p className="eyebrow">Project List</p>
          <h1>真实项目列表</h1>
          <p className="hero-copy">
            列表页保留之前的浏览入口，只负责筛选、分页和打开项目详情。
            详情页会在新标签页打开，管理配置能力单独放在配置页面处理。
          </p>
        </div>
        <div className="hero-panel">
          <p className="panel-label">Workspace</p>
          <h2>列表与配置分离</h2>
          <p className="hero-copy">
            这轮迭代补充的数据来源标记、缓存回退和项目接口归档继续保留在页面下方，
            顶部区域恢复成之前的样式。
          </p>
        </div>
      </header>

      <main className="grid">
        <section className="card span-full">
          <div className="section-head">
            <div>
              <p className="panel-label">Projects</p>
              <h2>项目列表</h2>
            </div>
            <button className="ghost-button" type="button" onClick={() => loadProjects(pageNum)}>
              刷新列表
            </button>
          </div>

          <div className="project-toolbar-row">
            <input value={filters.project_name} onChange={(event) => updateFilter("project_name", event.target.value)} placeholder="项目名称" />
            <input value={filters.project_type} onChange={(event) => updateFilter("project_type", event.target.value)} placeholder="项目类型" />
            <select value={filters.fixed_project} onChange={(event) => updateFilter("fixed_project", event.target.value)}>
              <option value="">是否固定项目</option>
              <option value="true">是</option>
              <option value="false">否</option>
            </select>
            <select value={filters.project_status} onChange={(event) => updateFilter("project_status", event.target.value)}>
              <option value="">项目状态</option>
              {statusOptions.map((item) => (
                <option key={item.name} value={item.name || ""}>
                  {item.name || ""}
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
            <button className="primary-button" type="button" onClick={() => loadProjects(1)}>
              查询项目
            </button>
          </div>

          <div className="list-toolbar-meta">
            <div className="category-meta">{statusText}</div>
          </div>

          <div className="table-wrap">
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
                {projects.map((project) => (
                  <tr key={project.id}>
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
                        查看项目
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pagination-bar pagination-bar-bottom">
            <button className="ghost-button" type="button" disabled={pageNum <= 1} onClick={() => loadProjects(pageNum - 1)}>
              上一页
            </button>
            <span className="pagination-info">
              第 {pageNum} 页 / 共 {totalPages} 页
              {filteredTotal ? ` / 筛选后 ${filteredTotal}` : ""}
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
