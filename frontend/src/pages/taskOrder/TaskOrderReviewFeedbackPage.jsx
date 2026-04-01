import { useEffect, useMemo, useRef, useState } from "react";
import PageLayout from "../../components/PageLayout";
import { buildUiUrl, normalizeScene, projectDisplayValue, requestJson } from "../../api";

const EXCLUDED_STATUS = new Set(["待立项", "立项中"]);
const STORAGE_KEY = "review-feedback-page-v3";
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
const initialTaskOrderFilters = {
  task_order_no: "",
  task_order_name: "",
  supplier: "",
  project_name: "",
  domain: "",
  task_order_status: "",
};

function optionLabel(option) {
  return option?.label || option?.name || option?.value || "";
}

function optionValue(option) {
  return option?.label || option?.name || option?.value || "";
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

function buildReviewStorageKey(projectId, category, scene) {
  return `${scene || "initiation"}::${category || "default"}::${projectId}`;
}

function loadStoredReviewEntries() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function loadStoredReviews(category, scene) {
  const rawEntries = loadStoredReviewEntries();
  const nextValue = {};
  Object.entries(rawEntries).forEach(([key, value]) => {
    if (!value || typeof value !== "object") {
      return;
    }
    const parts = key.split("::");
    const storedScene = parts.length >= 3 ? parts[0] : "initiation";
    const storedCategory = parts.length >= 3 ? parts[1] : parts[0];
    const projectId = parts.length >= 3 ? parts.slice(2).join("::") : parts.slice(1).join("::") || key;
    const recordCategory = value.category || storedCategory || "";
    const recordScene = value.scene || storedScene || "initiation";
    if (recordCategory !== category || normalizeScene(recordScene) !== normalizeScene(scene)) {
      return;
    }
    nextValue[projectId] = value;
  });
  return nextValue;
}

function persistStoredReviews(category, scene, reviewMap) {
  const rawEntries = loadStoredReviewEntries();
  Object.keys(rawEntries).forEach((key) => {
    if (key.startsWith(`${scene || "initiation"}::${category || "default"}::`)) {
      delete rawEntries[key];
    }
  });
  Object.entries(reviewMap).forEach(([projectId, record]) => {
    rawEntries[buildReviewStorageKey(projectId, category, scene)] = {
      ...record,
      category,
      scene,
    };
  });
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rawEntries));
}

function getReviewTimestamp(record) {
  const value = record?.updatedAt || record?.savedAt || "";
  const timestamp = value ? new Date(value).getTime() : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function getApprovalTimestamp(record) {
  const value = record?.approvalGeneratedAt || record?.generatedAt || "";
  const timestamp = value ? new Date(value).getTime() : 0;
  return Number.isFinite(timestamp) ? timestamp : 0;
}

function pickNewerReviewRecord(primary, fallback) {
  if (!primary?.decision && !primary?.summary && !primary?.error) {
    return fallback || {};
  }
  if (!fallback?.decision && !fallback?.summary && !fallback?.error) {
    return primary || {};
  }
  return getApprovalTimestamp(primary) >= getApprovalTimestamp(fallback) ? primary : fallback;
}

function mergeReviewMaps(localMap, remoteMap) {
  const nextValue = { ...remoteMap };
  const approvalFields = [
    "decision",
    "summary",
    "risks",
    "missingInformation",
    "positiveEvidence",
    "projectCommentary",
    "baseline",
    "segments",
    "runDir",
    "approvalGeneratedAt",
  ];
  Object.entries(localMap || {}).forEach(([projectId, record]) => {
    const remoteRecord = nextValue[projectId];
    if (!remoteRecord) {
      nextValue[projectId] = record;
      return;
    }
    const mergedRecord = { ...remoteRecord, ...record };
    const keepLocalApproval = getApprovalTimestamp(record) >= getApprovalTimestamp(remoteRecord);
    if (!keepLocalApproval) {
      approvalFields.forEach((field) => {
        mergedRecord[field] = remoteRecord[field];
      });
    }
    if (!record?.reviewOk) {
      mergedRecord.reviewOk = remoteRecord.reviewOk || mergedRecord.reviewOk;
    }
    if (!record?.reviewReason) {
      mergedRecord.reviewReason = remoteRecord.reviewReason || mergedRecord.reviewReason;
    }
    if (getReviewTimestamp(record) < getReviewTimestamp(remoteRecord)) {
      mergedRecord.persistError = remoteRecord.persistError || "";
    }
    nextValue[projectId] = mergedRecord;
  });
  return nextValue;
}

function isPassDecision(decision) {
  return String(decision || "").trim() === "通过";
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

function resolveApprovalTimestamp(record) {
  return formatApprovalTimestamp(record?.approvalGeneratedAt || record?.generatedAt || record?.savedAt || record?.updatedAt || "");
}

function buildPositiveEvidence(record) {
  const evidence = [];
  const statistics = record?.baseline?.statistics || {};
  const positiveEvidence = record?.positiveEvidence || [];
  if (statistics.total_rules) {
    evidence.push(`共通过 ${statistics.passed_rules || 0}/${statistics.total_rules} 条审批规则`);
  }
  positiveEvidence.forEach((item) => {
    if (item) {
      evidence.push(item);
    }
  });
  return Array.from(new Set(evidence)).slice(0, 3);
}

function buildAttentionItems(record) {
  if (isPassDecision(record?.decision)) {
    return [];
  }
  return Array.from(new Set([...(record?.risks || []), ...(record?.missingInformation || [])])).slice(0, 3);
}

function ReviewAdviceCard({ record, isTaskOrderScene = false }) {
  if (!record?.decision && !record?.summary && !record?.error) {
    return <div className="review-advice-empty">未生成建议</div>;
  }

  const fallbackText = buildAdviceText(record);
  const approvalTimestampText = resolveApprovalTimestamp(record);

  if (record?.error) {
    return (
      <div className="review-advice-box review-advice-box-error" title={fallbackText}>
        <div className="review-advice-head">
          <span className="review-decision-pill is-reject">生成失败</span>
        </div>
        {approvalTimestampText ? <div className="review-advice-meta">审批时间：{approvalTimestampText}</div> : null}
        <p className="review-advice-summary">{record.error}</p>
      </div>
    );
  }

  const pass = isPassDecision(record?.decision);
  const toneClass = pass ? "is-pass" : record?.decision === "驳回" ? "is-reject" : "is-warning";
  const items = pass ? buildPositiveEvidence(record) : buildAttentionItems(record);
  const sectionTitle = pass ? "证据" : "关注事项";
  const projectCommentary = pass ? String(record?.projectCommentary || "").trim() : "";

  return (
    <div className={`review-advice-box ${pass ? "is-pass" : ""}`} title={fallbackText}>
      <div className="review-advice-head">
        <span className={`review-decision-pill ${toneClass}`}>{record.decision || "-"}</span>
      </div>
      {approvalTimestampText ? <div className="review-advice-meta">上次审批时间：{approvalTimestampText}</div> : null}
      <p className="review-advice-summary">{record.summary || "-"}</p>
      {projectCommentary ? (
        <div className="review-advice-section">
          <strong>{isTaskOrderScene ? "任务评价" : "项目评价"}</strong>
          <p className="review-advice-commentary">{projectCommentary}</p>
        </div>
      ) : null}
      {items.length ? (
        <div className="review-advice-section">
          <strong>{sectionTitle}</strong>
          <ul className="review-advice-list">
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {record.runDir ? <code>{record.runDir}</code> : null}
    </div>
  );
}

function buildAdviceText(record) {
  if (!record?.decision && !record?.summary) {
    return "未生成建议";
  }
  const risks = (record.risks || []).slice(0, 3);
  return [
    `结论: ${record.decision || "-"}`,
    `摘要: ${record.summary || "-"}`,
    ...(record.projectCommentary && isPassDecision(record.decision) ? [`项目评价: ${record.projectCommentary}`] : []),
    ...(risks.length ? ["风险:", ...risks.map((item) => `- ${item}`)] : []),
  ].join("\n");
}

function buildProjectStatus(project) {
  return projectDisplayValue(project, "projectStatusName", "projectStatus") || "-";
}

function buildFlowStatus(project) {
  return projectDisplayValue(project, "flowStatusDisplay", "flowStatusName", "flowStatus") || "-";
}

function shouldKeepProject(project) {
  return !EXCLUDED_STATUS.has(buildProjectStatus(project)) && !EXCLUDED_STATUS.has(buildFlowStatus(project));
}

function buildProjectsQuery(scene, pageNum, pageSize, filters = {}) {
  const params = new URLSearchParams({
    page_num: String(pageNum),
    page_size: String(pageSize),
    scene,
  });
  Object.entries(filters).forEach(([key, value]) => {
    const text = String(value ?? "").trim();
    if (text) {
      params.set(key, text);
    }
  });
  return params.toString();
}

async function fetchProjectPage(scene, pageNum, pageSize, filters = {}) {
  const query = buildProjectsQuery(scene, pageNum, pageSize, filters);
  return requestJson(`/api/projects?${query}`);
}

function buildStatusText(payload, scene = "initiation") {
  const currentCount = (payload.projects || []).length;
  const filteredCount = Number(payload.filtered_total ?? currentCount);
  const totalCount = Number(payload.total || 0);
  const sourceLabel = payload.source === "cache" ? "本地缓存" : "远程接口";
  const warningText = payload.warning ? ` ${payload.warning}` : "";
  const extra = payload.page_source || payload.total_source
    ? ` 当前页来源: ${payload.page_source || sourceLabel}，总数来源: ${payload.total_source || sourceLabel}。`
    : "";
  const itemLabel = normalizeScene(scene) === "task_order" ? "任务单" : "项目";
  return `数据来源: ${sourceLabel}。总数 ${totalCount}，当前页 ${currentCount} 个${itemLabel}，筛选后 ${filteredCount}。${extra}${warningText}`;
}

function buildTaskOrderStatus(taskOrder) {
  return projectDisplayValue(taskOrder, "taskOrderStatusName", "taskOrderStatus", "statusName", "taskStatusName", "taskStatus") || "-";
}

export default function TaskOrderReviewFeedbackPage() {
  const activeScene = normalizeScene("task_order");
  const isTaskOrderScene = activeScene === "task_order";
  const [rules, setRules] = useState(null);
  const [category, setCategory] = useState("");
  const [projects, setProjects] = useState([]);
  const [statusText, setStatusText] = useState("正在加载项目...");
  const [reviewMap, setReviewMap] = useState({});
  const [loadingMap, setLoadingMap] = useState({});
  const [refreshing, setRefreshing] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [pageNum, setPageNum] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [filterOptions, setFilterOptions] = useState({
    domain: [],
    task_order_status: [],
    supplier: [],
  });
  const [taskOrderFilters, setTaskOrderFilters] = useState(initialTaskOrderFilters);
  const [appliedTaskOrderFilters, setAppliedTaskOrderFilters] = useState(initialTaskOrderFilters);
  const saveTimersRef = useRef({});

  const visibleProjects = useMemo(() => (isTaskOrderScene ? projects : projects.filter(shouldKeepProject)), [isTaskOrderScene, projects]);
  const totalPages = Math.max(
    1,
    Math.ceil((isTaskOrderScene ? total : visibleProjects.length) / Math.max(pageSize, 1)),
  );
  const currentPageProjects = useMemo(() => {
    if (isTaskOrderScene) {
      return visibleProjects;
    }
    const start = (pageNum - 1) * pageSize;
    return visibleProjects.slice(start, start + pageSize);
  }, [isTaskOrderScene, pageNum, pageSize, visibleProjects]);

  useEffect(() => {
    if (pageNum > totalPages) {
      setPageNum(totalPages);
    }
  }, [pageNum, totalPages]);

  useEffect(() => {
    let alive = true;
    Promise.all([
      requestJson(`/api/rules?scene=${encodeURIComponent(activeScene)}`),
      requestJson(`/api/project-filter-options?scene=${encodeURIComponent(activeScene)}`),
    ])
      .then(([rulesPayload, optionsPayload]) => {
        if (!alive) {
          return;
        }
        setRules(rulesPayload);
        setCategory(rulesPayload.categories?.[0]?.name || "");
        setFilterOptions({
          domain: optionsPayload?.items?.domain || [],
          task_order_status: optionsPayload?.items?.task_order_status || [],
          supplier: optionsPayload?.items?.supplier || [],
        });
      })
      .catch((error) => {
        if (alive) {
          setStatusText(error.message);
        }
      });
    return () => {
      alive = false;
    };
  }, [activeScene]);

  useEffect(() => {
    let alive = true;
    const filters = isTaskOrderScene ? appliedTaskOrderFilters : {};
    fetchProjectPage(activeScene, pageNum, pageSize, filters)
      .then((payload) => {
        if (!alive) {
          return;
        }
        setProjects(payload.projects || []);
        setTotal(Number(payload.total || 0));
        setStatusText(buildStatusText(payload, activeScene));
      })
      .catch((error) => {
        if (alive) {
          setStatusText(error.message || "加载列表失败");
        }
      });
    return () => {
      alive = false;
    };
  }, [activeScene, appliedTaskOrderFilters, isTaskOrderScene, pageNum, pageSize]);

  useEffect(() => {
    if (!category) {
      return;
    }
    const localReviews = loadStoredReviews(category, activeScene);
    setReviewMap(localReviews);

    let alive = true;
    requestJson(`/api/review-feedback?category=${encodeURIComponent(category)}&scene=${encodeURIComponent(activeScene)}`)
      .then((payload) => {
        if (!alive) {
          return;
        }
        const merged = mergeReviewMaps(localReviews, payload.items || {});
        setReviewMap(merged);
        persistStoredReviews(category, activeScene, merged);
      })
      .catch(() => {});

    return () => {
      alive = false;
    };
  }, [activeScene, category]);

  useEffect(() => () => {
    Object.values(saveTimersRef.current).forEach((timerId) => window.clearTimeout(timerId));
  }, []);

  function schedulePersistReview(project, record) {
    if (!project?.id || !category) {
      return;
    }

    if (saveTimersRef.current[project.id]) {
      window.clearTimeout(saveTimersRef.current[project.id]);
    }

    saveTimersRef.current[project.id] = window.setTimeout(async () => {
      try {
        const { persistError, savedAt, projectId, projectName, category: _recordCategory, ...feedbackPayload } = record;
        const savedRecord = await requestJson("/api/review-feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            projectId: project.id,
            projectName: projectDisplayValue(project, "projectName", "name", "id"),
            category,
            scene: activeScene,
            feedback: feedbackPayload,
          }),
        });
        setReviewMap((current) => {
          const nextValue = {
            ...current,
            [project.id]: {
              ...(current[project.id] || {}),
              ...savedRecord,
              persistError: "",
            },
          };
          persistStoredReviews(category, activeScene, nextValue);
          return nextValue;
        });
      } catch (error) {
        setReviewMap((current) => {
          const nextValue = {
            ...current,
            [project.id]: {
              ...(current[project.id] || {}),
              persistError: error.message || "落盘失败",
            },
          };
          persistStoredReviews(category, activeScene, nextValue);
          return nextValue;
        });
      } finally {
        delete saveTimersRef.current[project.id];
      }
    }, 500);
  }

  function updateReview(project, patch) {
    const projectId = project.id;
    setReviewMap((current) => {
      const nextRecord = {
        ...(current[projectId] || {}),
        ...patch,
        category,
        updatedAt: patch.updatedAt || new Date().toISOString(),
      };
      const nextValue = {
        ...current,
        [projectId]: nextRecord,
      };
      persistStoredReviews(category, activeScene, nextValue);
      schedulePersistReview(project, nextRecord);
      return nextValue;
    });
  }

  function updateTaskOrderFilter(key, value) {
    setTaskOrderFilters((current) => ({ ...current, [key]: value }));
  }

  function applyTaskOrderFilters() {
    setAppliedTaskOrderFilters({ ...taskOrderFilters });
    setPageNum(1);
  }

  function resetTaskOrderFilters() {
    setTaskOrderFilters(initialTaskOrderFilters);
    setAppliedTaskOrderFilters(initialTaskOrderFilters);
    setPageNum(1);
  }

  async function refreshProjects() {
    try {
      setRefreshing(true);
      const filters = isTaskOrderScene ? appliedTaskOrderFilters : {};
      const payload = await fetchProjectPage(activeScene, pageNum, pageSize, filters);
      setProjects(payload.projects || []);
      setTotal(Number(payload.total || 0));
      setStatusText(buildStatusText(payload, activeScene));
    } catch (error) {
      setStatusText(error.message);
    } finally {
      setRefreshing(false);
    }
  }

  async function generateAdvice(project) {
    const projectId = project.id;
    const resolvedProjectId = projectDisplayValue(
      project,
      "projectId",
      "projectBudgetId",
      "projectEstablishmentId",
      "projectInfoId",
    );
    const taskOrderId = projectDisplayValue(project, "id", "taskId", "taskOrderId");
    try {
      setLoadingMap((current) => ({ ...current, [projectId]: true }));
        const result = await requestJson("/api/approve/remote-project", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            projectId: resolvedProjectId || projectId,
            taskOrderId: taskOrderId || projectId,
            category,
            scene: activeScene,
          }),
        });
      updateReview(project, {
        decision: result.decision || "",
        summary: result.summary || "",
        risks: result.risks || [],
        missingInformation: result.missing_information || [],
        positiveEvidence: result.positive_evidence || [],
        projectCommentary: result.project_commentary || "",
        baseline: result.baseline || null,
        segments: result.segments || [],
        category,
        runDir: result.run_dir || "",
        approvalGeneratedAt: result.generated_at || new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        error: "",
      });
    } catch (error) {
      updateReview(project, {
        error: error.message,
        updatedAt: new Date().toISOString(),
      });
    } finally {
      setLoadingMap((current) => ({ ...current, [projectId]: false }));
    }
  }

  async function generateCurrentPageAdvice() {
    try {
      setBatchBusy(true);
      for (const project of currentPageProjects) {
        // Sequential execution avoids hammering the approval gateway.
        // eslint-disable-next-line no-await-in-loop
        await generateAdvice(project);
      }
      setStatusText(`当前页 ${currentPageProjects.length} 个${isTaskOrderScene ? "任务单" : "项目"}的建议已更新`);
    } catch (error) {
      setStatusText(error.message);
    } finally {
      setBatchBusy(false);
    }
  }

  function renderTaskOrderFilters() {
    const domainOptions = uniqueOptions(projects, "domainName", "belongTeamName", "belongDomainName", "domain");
    const supplierOptions = filterOptions.supplier?.length
      ? filterOptions.supplier
      : uniqueOptions(projects, "supplierName", "supplier", "vendorName").map((item) => ({ label: item, value: item, name: item }));
    const statusOptions = filterOptions.task_order_status?.length
      ? filterOptions.task_order_status
      : uniqueOptions(projects, "taskStatusName", "taskOrderStatus", "taskOrderStatusName", "statusName", "taskStatus")
        .map((item) => ({ label: item, value: item, name: item }));
    return (
      <div className="task-order-filter-hero">
        <div className="task-order-filter-grid">
          <label className="task-order-filter-field">
            <span>任务单编号</span>
            <input
              value={taskOrderFilters.task_order_no}
              onChange={(event) => updateTaskOrderFilter("task_order_no", event.target.value)}
              placeholder="请输入"
            />
          </label>
          <label className="task-order-filter-field">
            <span>任务单名称</span>
            <input
              value={taskOrderFilters.task_order_name}
              onChange={(event) => updateTaskOrderFilter("task_order_name", event.target.value)}
              placeholder="请输入"
            />
          </label>
          <label className="task-order-filter-field">
            <span>供应商</span>
            <select value={taskOrderFilters.supplier} onChange={(event) => updateTaskOrderFilter("supplier", event.target.value)}>
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
              value={taskOrderFilters.project_name}
              onChange={(event) => updateTaskOrderFilter("project_name", event.target.value)}
              placeholder="请输入"
            />
          </label>
          <label className="task-order-filter-field">
            <span>归属领域</span>
            <select value={taskOrderFilters.domain} onChange={(event) => updateTaskOrderFilter("domain", event.target.value)}>
              <option value="">请选择</option>
              {domainOptions.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </label>
          <label className="task-order-filter-field">
            <span>任务单状态</span>
            <select value={taskOrderFilters.task_order_status} onChange={(event) => updateTaskOrderFilter("task_order_status", event.target.value)}>
              <option value="">请选择</option>
              {statusOptions.map((item, index) => (
                <option key={`${optionValue(item)}-${index}`} value={optionValue(item)}>
                  {optionLabel(item)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="task-order-filter-actions">
          <button className="ghost-button" type="button" onClick={resetTaskOrderFilters}>重置</button>
          <button className="primary-button" type="button" onClick={applyTaskOrderFilters}>查询</button>
        </div>
      </div>
    );
  }

  return (
    <PageLayout wide scene={activeScene} section="review-feedback">
      <header className="hero">
        <div>
          <p className="eyebrow">Review Feedback</p>
          <h1>{isTaskOrderScene ? "任务单建议复核" : "项目建议复核"}</h1>
          <p className="hero-copy">
            {isTaskOrderScene
              ? "这里展示任务单分页清单，支持逐条生成建议，以及按当前页批量生成大模型审批建议。"
              : "这里只展示不处于“待立项”或“立项中”的项目，支持分页查看、逐条生成建议，以及按当前页批量生成大模型审批建议。"}
          </p>
        </div>
        <div className="hero-panel">
          <p className="panel-label">Current Scope</p>
          <h2>{isTaskOrderScene ? "任务单复核工作台" : "复核分页工作台"}</h2>
          <p className="hero-copy">
            {isTaskOrderScene
              ? "任务单场景会优先使用已经落盘的任务单正文与复核记录，不再和立项共用目录，便于后续回溯和规则迭代。"
              : "大模型审批会优先使用已经落盘的项目正文，不再每次重新拉取远程接口。人工评价与建议复核结果会同步落盘，便于后续回溯和程序改进。"}
          </p>
        </div>
      </header>

      <main className="grid">
        <section className="card span-full">
          <div className="section-head">
            <div>
              <p className="panel-label">Filters</p>
              <h2>{isTaskOrderScene ? "任务单范围与本页生成" : "项目范围与本页生成"}</h2>
            </div>
            <div className="button-row">
              <button className="ghost-button" type="button" onClick={refreshProjects} disabled={refreshing}>
                {refreshing ? "刷新中..." : isTaskOrderScene ? "刷新任务单" : "刷新项目"}
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={generateCurrentPageAdvice}
                disabled={batchBusy || !currentPageProjects.length || !category}
              >
                {batchBusy ? "本页生成中..." : isTaskOrderScene ? "本页全部生成任务单建议" : "本页全部生成建议"}
              </button>
            </div>
          </div>

          {isTaskOrderScene ? renderTaskOrderFilters() : null}

          <div className="project-toolbar-row review-toolbar-row">
            <div className="meta-item">
              <strong>审批品类</strong>
              <select style={{ marginTop: 8 }} value={category} onChange={(event) => setCategory(event.target.value)}>
                {(rules?.categories || []).map((item) => (
                  <option key={item.name} value={item.name}>
                    {item.name} / {item.group}
                  </option>
                ))}
              </select>
            </div>
            <div className="meta-item">
              <strong>分页大小</strong>
              <select
                style={{ marginTop: 8 }}
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value || 20));
                  setPageNum(1);
                }}
              >
                {PAGE_SIZE_OPTIONS.map((item) => (
                  <option key={item} value={item}>
                    {item} 条/页
                  </option>
                ))}
              </select>
            </div>
            <div className="meta-item review-toolbar-note">
              <strong>筛选规则</strong>
              <div className="category-meta" style={{ marginTop: 8, textAlign: "left" }}>
                {isTaskOrderScene ? "筛选项与任务单列表一致，点击“查询”后生效。" : "自动排除项目状态或流程状态为“待立项”“立项中”的项目。"}
              </div>
            </div>
            <div className="meta-item review-toolbar-note">
              <strong>当前状态</strong>
              <div className="category-meta" style={{ marginTop: 8, textAlign: "left" }}>
                {statusText}
              </div>
            </div>
          </div>
        </section>

        <section className="card span-full">
          <div className="section-head">
            <div>
              <p className="panel-label">Review List</p>
              <h2>{isTaskOrderScene ? "任务单复核列表" : "项目复核列表"}</h2>
            </div>
            <div className="pagination-bar">
              <button className="ghost-button" type="button" onClick={() => setPageNum((current) => Math.max(1, current - 1))} disabled={pageNum <= 1}>
                上一页
              </button>
              <span className="pagination-info">
                第 {pageNum} / {totalPages} 页，本页 {currentPageProjects.length} 条
              </span>
              <button
                className="ghost-button"
                type="button"
                onClick={() => setPageNum((current) => Math.min(totalPages, current + 1))}
                disabled={pageNum >= totalPages}
              >
                下一页
              </button>
            </div>
          </div>

          <div className="table-wrap">
            <table className="compact-table review-feedback-table">
              <thead>
                <tr>
                  <th>{isTaskOrderScene ? "任务单简要信息" : "项目简要信息"}</th>
                  <th>大模型审批建议</th>
                  <th>建议是否OK</th>
                  <th>不OK原因/改进建议</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {currentPageProjects.map((project) => {
                  const reviewKey = project.id;
                  const resolvedProjectId = projectDisplayValue(
                    project,
                    "projectId",
                    "projectBudgetId",
                    "projectEstablishmentId",
                    "projectInfoId",
                  );
                  const taskOrderId = projectDisplayValue(project, "id", "taskId", "taskOrderId");
                  const review = pickNewerReviewRecord(reviewMap[reviewKey] || {}, reviewMap[resolvedProjectId] || {});
                  const loading = Boolean(loadingMap[reviewKey]);
                  return (
                    <tr key={reviewKey}>
                      <td>
                        <div className="review-project-info">
                          <strong>
                            {isTaskOrderScene
                              ? projectDisplayValue(project, "taskOrderName", "taskName", "name", "id")
                              : projectDisplayValue(project, "projectName", "name", "id")}
                          </strong>
                          {isTaskOrderScene ? (
                            <>
                              <div>任务单编号: {projectDisplayValue(project, "taskOrderNo", "taskNo", "taskCode") || "-"}</div>
                              <div>所属项目: {projectDisplayValue(project, "projectName", "projectInfoName") || "-"}</div>
                              <div>供应商: {projectDisplayValue(project, "supplierName", "supplier", "vendorName") || "-"}</div>
                              <div>归属领域: {projectDisplayValue(project, "domainName", "belongDomainName", "domain") || "-"}</div>
                              <div>任务单状态: {buildTaskOrderStatus(project)}</div>
                            </>
                          ) : (
                            <>
                              <div>项目编码: {projectDisplayValue(project, "projectCode", "serialNo") || "-"}</div>
                              <div>项目经理: {projectDisplayValue(project, "managerName", "projectManagerName", "projectLeaderName") || "-"}</div>
                              <div>项目类型: {projectDisplayValue(project, "projectCategoryName", "projectFeeTypeName", "projectTypeName") || "-"}</div>
                              <div>项目状态: {buildProjectStatus(project)}</div>
                              <div>流程状态: {buildFlowStatus(project)}</div>
                            </>
                          )}
                        </div>
                      </td>
                      <td>
                        <ReviewAdviceCard record={review} isTaskOrderScene={isTaskOrderScene} />
                      </td>
                      <td>
                        <select
                          className="review-select"
                          value={review.reviewOk || ""}
                          onChange={(event) => updateReview(project, { reviewOk: event.target.value })}
                        >
                          <option value="">未评价</option>
                          <option value="ok">OK</option>
                          <option value="not_ok">不OK</option>
                        </select>
                      </td>
                      <td>
                        {review.approvalGeneratedAt || review.savedAt || review.updatedAt ? (
                          <div className="review-history-meta">
                            <strong>上次复议记录</strong>
                            <div>审批时间：{resolveApprovalTimestamp(review) || "-"}</div>
                            <div>改进建议更新时间：{formatApprovalTimestamp(review.savedAt || review.updatedAt) || "-"}</div>
                          </div>
                        ) : null}
                        <textarea
                          className="review-reason-input"
                          placeholder={isTaskOrderScene ? "填写任务单建议不OK的原因，或希望模型如何调整任务单建议" : "填写为什么不OK，或希望模型如何调整建议"}
                          value={review.reviewReason || ""}
                          onChange={(event) => updateReview(project, { reviewReason: event.target.value })}
                        />
                        {review.persistError ? <div className="review-persist-status is-error">落盘失败: {review.persistError}</div> : null}
                        {!review.persistError && review.savedAt ? (
                          <div className="review-persist-status">已落盘: {review.savedAt}</div>
                        ) : null}
                      </td>
                      <td>
                        <div className="button-row review-row-actions">
                          <button className="ghost-button" type="button" onClick={() => generateAdvice(project)} disabled={loading || !category}>
                            {loading ? "生成中..." : isTaskOrderScene ? "生成任务单建议" : "生成建议"}
                          </button>
                          <button
                            className="table-button"
                            type="button"
                            onClick={() =>
                              window.open(
                                buildUiUrl(`/project/${encodeURIComponent(resolvedProjectId || taskOrderId || reviewKey)}`, {
                                  scene: activeScene,
                                  category,
                                  taskOrderId,
                                }),
                                "_blank",
                                "noopener,noreferrer",
                              )
                            }
                          >
                            {isTaskOrderScene ? "查看任务单" : "查看项目"}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!currentPageProjects.length ? (
                  <tr>
                    <td colSpan="5">
                      <div className="viewer-empty">{isTaskOrderScene ? "没有符合条件的任务单。" : "没有符合条件的项目。"}</div>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </PageLayout>
  );
}
