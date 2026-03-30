import { useEffect, useMemo, useRef, useState } from "react";
import PageLayout from "../../components/PageLayout";
import { buildUiUrl, normalizeScene, projectDisplayValue, requestJson } from "../../api";

const STORAGE_KEY = "acceptance-review-feedback-page-v4";
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

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

function mergeReviewMaps(localMap, remoteMap) {
  const nextValue = { ...remoteMap };
  Object.entries(localMap || {}).forEach(([projectId, record]) => {
    const remoteRecord = nextValue[projectId];
    if (!remoteRecord || getReviewTimestamp(record) >= getReviewTimestamp(remoteRecord)) {
      nextValue[projectId] = record;
    }
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

function ReviewAdviceCard({ record }) {
  if (!record?.decision && !record?.summary && !record?.error) {
    return <div className="review-advice-empty">尚未生成建议</div>;
  }

  if (record?.error) {
    return (
      <div className="review-advice-box review-advice-box-error">
        <div className="review-advice-head">
          <span className="review-decision-pill is-reject">生成失败</span>
        </div>
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
    <div className={`review-advice-box ${pass ? "is-pass" : ""}`}>
      <div className="review-advice-head">
        <span className={`review-decision-pill ${toneClass}`}>{record.decision || "-"}</span>
      </div>
      <p className="review-advice-summary">{record.summary || "-"}</p>
      {projectCommentary ? (
        <div className="review-advice-section">
          <strong>项目评价</strong>
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

function ApprovalRuleDetailPanel({ record, open, onToggle }) {
  const detailItems = normalizeApprovalDetailItems(record);
  if (!record?.decision || !detailItems.length) {
    return null;
  }

  return (
    <div className="viewer-approval-actions" style={{ marginTop: 12 }}>
      <button className="ghost-button" type="button" onClick={onToggle}>
        {open ? "收起规则明细" : "查看规则明细"}
      </button>
      {open ? (
        <div className="viewer-approval-detail-panel" style={{ width: "100%" }}>
          <div className="viewer-approval-detail-head">
            <h3>审批规则明细</h3>
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
    </div>
  );
}

function buildProjectStatus(project) {
  return projectDisplayValue(project, "projectStatusName", "projectStatus") || "-";
}

function buildFlowStatus(project) {
  return projectDisplayValue(project, "flowStatusDisplay", "flowStatusName", "flowStatus") || "-";
}

function buildAcceptanceDomain(project) {
  return (
    projectDisplayValue(
      project,
      "domainName",
      "businessDomainName",
      "businessCategoryName",
      "projectClassifyParentName",
    ) || "-"
  );
}

function isLowSignalAcceptanceLabel(value) {
  const text = String(value || "").trim();
  if (!text) {
    return true;
  }
  return /^[A-Z&/-]{2,8}$/.test(text);
}

function buildAcceptanceProjectTags(project) {
  const tags = [];
  const pushTag = (value) => {
    const text = String(value || "").trim();
    if (!text || text === "-" || tags.includes(text)) {
      return;
    }
    tags.push(text);
  };
  pushTag(projectDisplayValue(project, "projectCode", "serialNo"));
  const categoryText = projectDisplayValue(project, "projectClassifyParentName", "businessCategoryName", "projectCategoryName");
  const subcategoryText = projectDisplayValue(project, "projectClassifyName", "businessSubcategoryName", "projectTypeName");
  if (!isLowSignalAcceptanceLabel(categoryText)) {
    pushTag(categoryText);
  } else {
    pushTag(buildAcceptanceDomain(project));
  }
  if (!isLowSignalAcceptanceLabel(subcategoryText)) {
    pushTag(subcategoryText);
  }
  pushTag(projectDisplayValue(project, "projectLevelName", "projectLevel"));
  return tags;
}

function resolveAcceptanceProjectCategory(project) {
  return (
    projectDisplayValue(project, "businessSubcategoryName", "projectClassifyName", "projectTypeName", "category") || ""
  );
}

function getProjectReviewRecord(reviewStore, project, fallbackCategory = "") {
  const projectId = project?.id;
  if (!projectId) {
    return {};
  }
  const projectCategory = resolveAcceptanceProjectCategory(project) || fallbackCategory || "";
  const directRecord = reviewStore?.[projectCategory]?.[projectId];
  if (directRecord) {
    return directRecord;
  }
  let latestRecord = {};
  let latestTimestamp = 0;
  Object.values(reviewStore || {}).forEach((categoryItems) => {
    const candidate = categoryItems?.[projectId];
    if (!candidate) {
      return;
    }
    const timestamp = getReviewTimestamp(candidate);
    if (timestamp >= latestTimestamp) {
      latestTimestamp = timestamp;
      latestRecord = candidate;
    }
  });
  return latestRecord;
}

function buildCategoryReviewStore(categories, scene) {
  const nextValue = {};
  categories.forEach((item) => {
    const category = String(item || "").trim();
    if (!category) {
      return;
    }
    nextValue[category] = loadStoredReviews(category, scene);
  });
  return nextValue;
}

async function fetchAcceptanceReviewProjects(scene) {
  const result = await requestJson(`/api/review-projects?scene=${encodeURIComponent(scene)}`);
  const projects = result.projects || [];
  return {
    allProjects: projects,
    total: Number(result.total || projects.length),
    source: result.source || "remote",
    warning: result.warning || "",
  };
}

function countGeneratedReviews(reviewMap) {
  return Object.values(reviewMap || {}).filter((item) => item?.decision || item?.summary || item?.error).length;
}

function countPassReviews(reviewMap) {
  return Object.values(reviewMap || {}).filter((item) => isPassDecision(item?.decision)).length;
}

function countPendingManualReviews(reviewMap) {
  return Object.values(reviewMap || {}).filter((item) => {
    if (!item?.decision && !item?.summary && !item?.error) {
      return false;
    }
    return !item?.reviewOk;
  }).length;
}

function buildStatusText(payload, pageNum, pageSize, pageCount) {
  const sourceLabel = payload.source === "cache" ? "缓存" : "远程接口";
  const warningText = payload.warning ? ` ${payload.warning}` : "";
  return `项目 ${payload.allProjects.length} 条，当前第 ${pageNum} / ${pageCount} 页，每页 ${pageSize} 条，数据来源 ${sourceLabel}。${warningText}`;
}

export default function AcceptanceReviewFeedbackPage() {
  const activeScene = normalizeScene("acceptance");
  const [rules, setRules] = useState(null);
  const [category, setCategory] = useState("");
  const [projects, setProjects] = useState([]);
  const [statusText, setStatusText] = useState("正在加载项目...");
  const [reviewStore, setReviewStore] = useState({});
  const [loadingMap, setLoadingMap] = useState({});
  const [refreshing, setRefreshing] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [pageNum, setPageNum] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [projectSource, setProjectSource] = useState("remote");
  const [projectWarning, setProjectWarning] = useState("");
  const [detailOpenMap, setDetailOpenMap] = useState({});
  const saveTimersRef = useRef({});

  const filteredProjects = useMemo(() => {
    if (!category) {
      return projects;
    }
    return projects.filter((project) => resolveAcceptanceProjectCategory(project) === category);
  }, [category, projects]);
  const projectReviewRecords = useMemo(
    () => filteredProjects.map((project) => getProjectReviewRecord(reviewStore, project, category)),
    [category, filteredProjects, reviewStore],
  );
  const generatedReviewCount = useMemo(() => countGeneratedReviews(projectReviewRecords), [projectReviewRecords]);
  const passReviewCount = useMemo(() => countPassReviews(projectReviewRecords), [projectReviewRecords]);
  const pendingManualReviewCount = useMemo(() => countPendingManualReviews(projectReviewRecords), [projectReviewRecords]);
  const totalPages = Math.max(1, Math.ceil(filteredProjects.length / Math.max(pageSize, 1)));
  const currentPageProjects = useMemo(() => {
    const start = (pageNum - 1) * pageSize;
    return filteredProjects.slice(start, start + pageSize);
  }, [filteredProjects, pageNum, pageSize]);

  useEffect(() => {
    if (pageNum > totalPages) {
      setPageNum(totalPages);
    }
  }, [pageNum, totalPages]);

  useEffect(() => {
    let alive = true;
    Promise.all([requestJson(`/api/rules?scene=${encodeURIComponent(activeScene)}`), fetchAcceptanceReviewProjects(activeScene)])
      .then(([rulesPayload, projectsPayload]) => {
        if (!alive) {
          return;
        }
        setRules(rulesPayload);
        setProjects(projectsPayload.allProjects);
        setProjectSource(projectsPayload.source || "remote");
        setProjectWarning(projectsPayload.warning || "");
        setStatusText(buildStatusText(projectsPayload, 1, pageSize, Math.max(1, Math.ceil(projectsPayload.allProjects.length / pageSize))));
      })
      .catch((error) => {
        if (alive) {
          setStatusText(error.message || "加载项目失败");
        }
      });
    return () => {
      alive = false;
    };
  }, [activeScene, pageSize]);

  useEffect(() => {
    setStatusText(
      buildStatusText(
        { allProjects: filteredProjects, source: projectSource, warning: projectWarning },
        pageNum,
        pageSize,
        totalPages,
      ),
    );
  }, [filteredProjects, pageNum, pageSize, projectSource, projectWarning, totalPages]);

  useEffect(() => {
    const reviewCategories = Array.from(new Set(projects.map((project) => resolveAcceptanceProjectCategory(project)).filter(Boolean)));
    if (!reviewCategories.length) {
      setReviewStore({});
      return;
    }
    let alive = true;
    const localStore = buildCategoryReviewStore(reviewCategories, activeScene);
    setReviewStore(localStore);

    Promise.all(
      reviewCategories.map(async (item) => {
        const payload = await requestJson(`/api/review-feedback?category=${encodeURIComponent(item)}&scene=${encodeURIComponent(activeScene)}`);
        const merged = mergeReviewMaps(localStore[item] || {}, payload.items || {});
        return [item, merged];
      }),
    )
      .then((entries) => {
        if (!alive) {
          return;
        }
        const nextStore = {};
        entries.forEach(([item, merged]) => {
          nextStore[item] = merged;
          persistStoredReviews(item, activeScene, merged);
        });
        setReviewStore(nextStore);
      })
      .catch(() => {});

    return () => {
      alive = false;
    };
  }, [activeScene, projects]);

  useEffect(() => () => {
    Object.values(saveTimersRef.current).forEach((timerId) => window.clearTimeout(timerId));
  }, []);

  function schedulePersistReview(project, projectCategory, record) {
    if (!project?.id || !projectCategory) {
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
            category: projectCategory,
            scene: activeScene,
            feedback: feedbackPayload,
          }),
        });
        setReviewStore((current) => {
          const categoryItems = {
            ...(current[projectCategory] || {}),
            [project.id]: {
              ...((current[projectCategory] || {})[project.id] || {}),
              ...savedRecord,
              category: projectCategory,
              persistError: "",
            },
          };
          const nextValue = {
            ...current,
            [projectCategory]: categoryItems,
          };
          persistStoredReviews(projectCategory, activeScene, categoryItems);
          return nextValue;
        });
      } catch (error) {
        setReviewStore((current) => {
          const categoryItems = {
            ...(current[projectCategory] || {}),
            [project.id]: {
              ...((current[projectCategory] || {})[project.id] || {}),
              persistError: error.message || "落盘失败",
            },
          };
          const nextValue = {
            ...current,
            [projectCategory]: categoryItems,
          };
          persistStoredReviews(projectCategory, activeScene, categoryItems);
          return nextValue;
        });
      } finally {
        delete saveTimersRef.current[project.id];
      }
    }, 500);
  }

  function updateReview(project, patch) {
    const projectId = project.id;
    const projectCategory = resolveAcceptanceProjectCategory(project) || category || "";
    if (!projectCategory) {
      return;
    }
    setReviewStore((current) => {
      const categoryItems = current[projectCategory] || {};
      const nextRecord = {
        ...(categoryItems[projectId] || {}),
        ...patch,
        category: patch.category || projectCategory,
        updatedAt: patch.updatedAt || new Date().toISOString(),
      };
      const nextValue = {
        ...current,
        [projectCategory]: {
          ...categoryItems,
          [projectId]: nextRecord,
        },
      };
      persistStoredReviews(projectCategory, activeScene, nextValue[projectCategory]);
      schedulePersistReview(project, projectCategory, nextRecord);
      return nextValue;
    });
  }

  async function refreshProjects() {
    try {
      setRefreshing(true);
      const payload = await fetchAcceptanceReviewProjects(activeScene);
      setProjects(payload.allProjects);
      setProjectSource(payload.source || "remote");
      setProjectWarning(payload.warning || "");
      setPageNum(1);
      setStatusText(buildStatusText(payload, 1, pageSize, Math.max(1, Math.ceil(payload.allProjects.length / pageSize))));
    } catch (error) {
      setStatusText(error.message || "刷新项目失败");
    } finally {
      setRefreshing(false);
    }
  }

  async function generateAdvice(project) {
    const projectId = project.id;
    const projectCategory = resolveAcceptanceProjectCategory(project) || category || "";
    try {
      setLoadingMap((current) => ({ ...current, [projectId]: true }));
      const result = await requestJson("/api/approve/remote-project", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ projectId, category: projectCategory, scene: activeScene, refreshDocument: true }),
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
        category: result.resolved_category || projectCategory,
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
      setStatusText(`当前页 ${currentPageProjects.length} 个项目的建议已更新`);
    } catch (error) {
      setStatusText(error.message || "生成建议失败");
    } finally {
      setBatchBusy(false);
    }
  }

  return (
    <PageLayout wide scene={activeScene} section="review-feedback">
      <header className="card acceptance-review-hero">
        <div className="acceptance-review-hero-copy">
          <p className="eyebrow">Acceptance Review</p>
          <h1>验收复核工作台</h1>
          <p className="hero-copy">项目列表改为专用验收复核接口，只读取 `projectAccept` 中项目状态为 4、9 的项目，并围绕验收复核重新组织展示内容。</p>
        </div>
        <div className="acceptance-review-hero-stats">
          <div className="acceptance-review-hero-stat">
            <span>数据来源</span>
            <strong>{projectSource === "cache" ? "缓存" : "远程接口"}</strong>
          </div>
          <div className="acceptance-review-hero-stat">
            <span>验收状态</span>
            <strong>4 / 9</strong>
          </div>
          <div className="acceptance-review-hero-stat">
            <span>当前品类</span>
            <strong>{category || "-"}</strong>
          </div>
        </div>
      </header>

      <main className="grid">
        <section className="card span-full acceptance-review-dashboard">
          <div className="acceptance-review-metrics">
            <article className="acceptance-review-metric-card">
              <span>项目总数</span>
              <strong>{projects.length}</strong>
            </article>
            <article className="acceptance-review-metric-card">
              <span>已生成建议</span>
              <strong>{generatedReviewCount}</strong>
            </article>
            <article className="acceptance-review-metric-card">
              <span>建议通过</span>
              <strong>{passReviewCount}</strong>
            </article>
            <article className="acceptance-review-metric-card">
              <span>待人工确认</span>
              <strong>{pendingManualReviewCount}</strong>
            </article>
          </div>
          <div className="acceptance-review-toolbar">
            <div className="acceptance-review-toolbar-fields">
              <label className="meta-item">
                <strong>业务子类</strong>
                <select style={{ marginTop: 8 }} value={category} onChange={(event) => setCategory(event.target.value)}>
                  <option value="">全部</option>
                  {(rules?.categories || []).map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name} / {item.group}
                    </option>
                  ))}
                </select>
              </label>
              <label className="meta-item">
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
              </label>
              <div className="meta-item review-toolbar-note">
                <strong>筛选规则</strong>
                <div className="category-meta" style={{ marginTop: 8, textAlign: "left" }}>
                  仅显示验收中、已完成的验收项目，接口来源与验收项目列表保持同源。
                </div>
              </div>
              <div className="meta-item review-toolbar-note">
                <strong>当前状态</strong>
                <div className="category-meta" style={{ marginTop: 8, textAlign: "left" }}>
                  {statusText}
                </div>
              </div>
            </div>
            <div className="button-row">
              <button className="ghost-button" type="button" onClick={refreshProjects} disabled={refreshing}>
                {refreshing ? "刷新中..." : "刷新项目"}
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={generateCurrentPageAdvice}
                disabled={batchBusy || !currentPageProjects.length}
              >
                {batchBusy ? "生成中..." : "生成本页建议"}
              </button>
            </div>
          </div>
        </section>

        <section className="card span-full acceptance-review-list-card">
          <div className="section-head">
            <div>
              <p className="panel-label">Acceptance Review Projects</p>
              <h2>项目复核列表</h2>
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

          <div className="acceptance-review-project-list">
            {currentPageProjects.map((project) => {
              const projectId = project.id;
              const projectCategory = resolveAcceptanceProjectCategory(project) || category || "";
              const review = getProjectReviewRecord(reviewStore, project, category);
              const loading = Boolean(loadingMap[projectId]);
              return (
                <article key={projectId} className="acceptance-review-project-card">
                  <div className="acceptance-review-project-head">
                    <div>
                      <p className="panel-label">项目复核</p>
                      <h3>{projectDisplayValue(project, "projectName", "name", "id")}</h3>
                      <div className="acceptance-review-project-tags">
                        {buildAcceptanceProjectTags(project).map((item) => (
                          <span key={item}>{item}</span>
                        ))}
                      </div>
                    </div>
                    <div className="button-row">
                      <button className="ghost-button" type="button" onClick={() => generateAdvice(project)} disabled={loading || !projectCategory}>
                        {loading ? "生成中..." : "生成建议"}
                      </button>
                      <button
                        className="table-button"
                        type="button"
                        onClick={() =>
                          window.open(
                            buildUiUrl(`/project/${encodeURIComponent(projectId)}`, { scene: activeScene, category: projectCategory }),
                            "_blank",
                            "noopener,noreferrer",
                          )
                        }
                      >
                        查看项目
                      </button>
                    </div>
                  </div>

                  <div className="acceptance-review-project-grid">
                    <section className="acceptance-review-project-summary">
                      <div className="acceptance-review-info-grid">
                        <div><span>项目经理</span><strong>{projectDisplayValue(project, "managerName", "projectManagerName", "projectLeaderName") || "-"}</strong></div>
                        <div><span>归属领域</span><strong>{buildAcceptanceDomain(project)}</strong></div>
                        <div><span>申请项目预算</span><strong>{projectDisplayValue(project, "applyTotalBudget", "applyBudget", "requestBudget", "projectBudget", "proBudget") || "-"}</strong></div>
                        <div><span>申请年度预算</span><strong>{projectDisplayValue(project, "applyYearBudget", "projectYearBudget", "proBudgetYear", "yearBudget") || "-"}</strong></div>
                        <div><span>累计验收金额(含税)</span><strong>{projectDisplayValue(project, "acceptanceAmountTax", "acceptMoneyTax", "acceptanceTaxIncludedAmount", "totalAcceptAmountTax") || "-"}</strong></div>
                        <div><span>累计验收金额(不含税)</span><strong>{projectDisplayValue(project, "acceptanceAmount", "acceptMoneyNoTax", "acceptanceWithoutTaxAmount", "totalAcceptAmount") || "-"}</strong></div>
                        <div><span>预算执行率</span><strong>{projectDisplayValue(project, "budgetExecutionRate", "executeRate", "progressRate", "budgetRate") || "-"}</strong></div>
                        <div><span>流程状态</span><strong>{buildFlowStatus(project)}</strong></div>
                      </div>
                    </section>

                    <section className="acceptance-review-project-advice">
                      <div className="acceptance-review-panel-title">模型审批建议</div>
                      <ReviewAdviceCard record={review} />
                      <ApprovalRuleDetailPanel
                        record={review}
                        open={Boolean(detailOpenMap[projectId])}
                        onToggle={() => setDetailOpenMap((current) => ({ ...current, [projectId]: !current[projectId] }))}
                      />
                    </section>

                    <section className="acceptance-review-project-manual">
                      <div className="acceptance-review-panel-title">人工复核</div>
                      <select
                        className="review-select"
                        value={review.reviewOk || ""}
                        onChange={(event) => updateReview(project, { reviewOk: event.target.value })}
                      >
                        <option value="">未评价</option>
                        <option value="ok">OK</option>
                        <option value="not_ok">不OK</option>
                      </select>
                      {review.approvalGeneratedAt || review.savedAt || review.updatedAt ? (
                        <div className="review-history-meta">
                          <strong>最近复核记录</strong>
                          <div>审批时间: {resolveApprovalTimestamp(review) || "-"}</div>
                          <div>更新时间: {formatApprovalTimestamp(review.savedAt || review.updatedAt) || "-"}</div>
                        </div>
                      ) : null}
                      <textarea
                        className="review-reason-input"
                        placeholder="填写不 OK 的原因，或说明你希望模型如何调整验收建议"
                        value={review.reviewReason || ""}
                        onChange={(event) => updateReview(project, { reviewReason: event.target.value })}
                      />
                      {review.persistError ? <div className="review-persist-status is-error">落盘失败: {review.persistError}</div> : null}
                      {!review.persistError && review.savedAt ? <div className="review-persist-status">已落盘: {review.savedAt}</div> : null}
                    </section>
                  </div>
                </article>
              );
            })}
            {!currentPageProjects.length ? <div className="viewer-empty">没有符合条件的验收项目。</div> : null}
          </div>
        </section>
      </main>
    </PageLayout>
  );
}
