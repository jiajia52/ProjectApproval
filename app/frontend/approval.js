const approvalState = {
  projects: [],
  pageNum: 1,
  pageSize: 20,
  total: 0,
  filteredTotal: 0,
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
    const message = payload?.detail || payload?.message || text || "请求失败。";
    throw new Error(message);
  }
  return payload;
}

function setListStatus(message) {
  document.getElementById("project-list-status").textContent = message;
}

function buildProjectListStatus(result, currentCount, filteredTotal) {
  const sourceLabel = result?.source === "cache" ? "本地缓存" : "远程接口";
  const warning = result?.warning ? ` ${result.warning}` : "";
  return `数据来源：${sourceLabel}。总数 ${result?.total || 0}，当前页 ${currentCount}，筛选后 ${filteredTotal}。${warning}`;
}

function renderPagination() {
  const pageInfo = document.getElementById("project-page-info");
  const prevButton = document.getElementById("project-prev-page");
  const nextButton = document.getElementById("project-next-page");
  const totalPages = Math.max(1, Math.ceil((approvalState.total || 0) / Math.max(approvalState.pageSize, 1)));
  pageInfo.textContent = `第 ${approvalState.pageNum} 页 / 共 ${totalPages} 页`;
  prevButton.disabled = approvalState.pageNum <= 1;
  nextButton.disabled = approvalState.pageNum >= totalPages;
}

function fillProjectStatusOptions(payload) {
  const select = document.getElementById("project-status-filter");
  const currentValue = select.value;
  select.innerHTML = '<option value="">项目状态</option>';
  (payload.items || []).forEach((item) => {
    const option = document.createElement("option");
    option.value = item.name || "";
    option.textContent = item.name || "";
    option.selected = option.value === currentValue;
    select.appendChild(option);
  });
}

function readProjectFilters() {
  return {
    project_name: document.getElementById("project-name-filter").value.trim(),
    project_type: document.getElementById("project-type-filter").value.trim(),
    fixed_project: document.getElementById("project-fixed-filter").value,
    project_status: document.getElementById("project-status-filter").value.trim(),
    flow_status: document.getElementById("project-flow-status-filter").value.trim(),
  };
}

function projectDisplayValue(project, ...keys) {
  for (const key of keys) {
    const value = project?.[key];
    if (value !== null && value !== undefined && String(value).trim() !== "") {
      return String(value);
    }
  }
  return "";
}

function renderProjects(projects) {
  const body = document.getElementById("project-table-body");
  body.innerHTML = "";
  projects.forEach((project) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${projectDisplayValue(project, "projectName", "name", "id")}</td>
      <td>${projectDisplayValue(project, "projectCode", "serialNo") || "-"}</td>
      <td>${projectDisplayValue(project, "domainName", "belongTeamName") || "-"}</td>
      <td>${projectDisplayValue(project, "departmentName", "belongDepartmentName") || "-"}</td>
      <td>${projectDisplayValue(project, "managerName", "projectManagerName", "projectLeaderName") || "-"}</td>
      <td>${projectDisplayValue(project, "projectCategoryName", "projectFeeTypeName", "projectTypeName") || "-"}</td>
      <td>${projectDisplayValue(project, "fixedProjectLabel") || "-"}</td>
      <td>${projectDisplayValue(project, "projectStatusName", "projectStatus") || "-"}</td>
      <td>${projectDisplayValue(project, "flowStatusDisplay", "flowStatusName", "flowStatus") || "-"}</td>
      <td>
        <button class="table-button" data-project-id="${project.id}" data-action="view" type="button">查看项目</button>
      </td>
    `;
    body.appendChild(tr);
  });
}

async function loadProjects() {
  const filters = readProjectFilters();
  const pageSize = Number(document.getElementById("project-page-size").value || 20);
  approvalState.pageSize = pageSize;
  const params = new URLSearchParams({ page_num: String(approvalState.pageNum), page_size: String(pageSize) });
  Object.entries(filters).forEach(([key, value]) => {
    if (value) {
      params.set(key, value);
    }
  });
  const result = await requestJson(`/api/projects?${params.toString()}`);
  approvalState.projects = result.projects || [];
  approvalState.total = Number(result.total || 0);
  approvalState.filteredTotal = Number(result.filtered_total ?? approvalState.projects.length);
  renderProjects(approvalState.projects);
  renderPagination();
  setListStatus(buildProjectListStatus(result, approvalState.projects.length, approvalState.filteredTotal));
}

function openProjectViewer(projectId) {
  const viewerUrl = `/ui/project-viewer.html?projectId=${encodeURIComponent(projectId)}`;
  window.open(viewerUrl, "_blank", "noopener,noreferrer");
}

async function boot() {
  const projectStatusOptions = await requestJson("/api/project-status-options");
  fillProjectStatusOptions(projectStatusOptions);
  renderPagination();
  await loadProjects();
}

document.getElementById("search-projects-button").addEventListener("click", async () => {
  try {
    approvalState.pageNum = 1;
    await loadProjects();
  } catch (error) {
    setListStatus(error.message);
  }
});

document.getElementById("refresh-projects-button").addEventListener("click", async () => {
  try {
    await loadProjects();
  } catch (error) {
    setListStatus(error.message);
  }
});

document.getElementById("project-prev-page").addEventListener("click", async () => {
  if (approvalState.pageNum <= 1) {
    return;
  }
  try {
    approvalState.pageNum -= 1;
    await loadProjects();
  } catch (error) {
    setListStatus(error.message);
  }
});

document.getElementById("project-next-page").addEventListener("click", async () => {
  try {
    approvalState.pageNum += 1;
    await loadProjects();
  } catch (error) {
    approvalState.pageNum = Math.max(1, approvalState.pageNum - 1);
    setListStatus(error.message);
  }
});

document.getElementById("project-table-body").addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) {
    return;
  }
  if (target.dataset.action !== "view") {
    return;
  }
  openProjectViewer(target.dataset.projectId);
});

boot().catch((error) => {
  setListStatus(error.message);
});
