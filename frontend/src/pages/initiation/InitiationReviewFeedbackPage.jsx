import { useEffect, useMemo, useRef, useState } from "react";
import PageLayout from "../../components/PageLayout";
import { buildUiUrl, projectDisplayValue, requestJson } from "../../api";

const EXCLUDED_STATUS = new Set(["待立项", "立项中"]);
const STORAGE_KEY = "review-feedback-page-v3";
const FETCH_PAGE_SIZE = 100;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

function buildReviewStorageKey(projectId, category) {
  return `${category || "default"}::${projectId}`;
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

function loadStoredReviews(category) {
  const rawEntries = loadStoredReviewEntries();
  const nextValue = {};
  Object.entries(rawEntries).forEach(([key, value]) => {
    if (!value || typeof value !== "object") {
      return;
    }
    const [storedCategory, ...rest] = key.split("::");
    const projectId = rest.join("::") || key;
    const recordCategory = value.category || storedCategory || "";
    if (recordCategory !== category) {
      return;
    }
    nextValue[projectId] = value;
  });
  return nextValue;
}

function persistStoredReviews(category, reviewMap) {
  const rawEntries = loadStoredReviewEntries();
  Object.keys(rawEntries).forEach((key) => {
    if (key.startsWith(`${category || "default"}::`)) {
      delete rawEntries[key];
    }
  });
  Object.entries(reviewMap).forEach(([projectId, record]) => {
    rawEntries[buildReviewStorageKey(projectId, category)] = {
      ...record,
      category,
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

async function fetchAllProjects() {
  const allProjects = [];
  let pageNum = 1;
  let total = 0;
  let source = "remote";
  let warning = "";

  while (true) {
    const result = await requestJson(`/api/projects?page_num=${pageNum}&page_size=${FETCH_PAGE_SIZE}`);
    const pageProjects = result.projects || [];
    allProjects.push(...pageProjects);
    total = Number(result.total || allProjects.length);
    source = result.source || source;
    warning = result.warning || warning;
    if (!pageProjects.length || allProjects.length >= total) {
      break;
    }
    pageNum += 1;
  }

  return { allProjects, total, source, warning };
}

function buildStatusText(payload, filteredCount, pageNum, pageSize, pageCount) {
  const sourceLabel = payload.source === "cache" ? "缓存" : "远程";
  const warningText = payload.warning ? `，${payload.warning}` : "";
  return `已加载 ${payload.allProjects.length} 个项目，过滤后 ${filteredCount} 个，当前第 ${pageNum} / ${pageCount} 页，每页 ${pageSize} 条，数据来源 ${sourceLabel}${warningText}`;
}

export default function InitiationReviewFeedbackPage() {
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
  const [projectSource, setProjectSource] = useState("remote");
  const [projectWarning, setProjectWarning] = useState("");
  const saveTimersRef = useRef({});

  const visibleProjects = useMemo(() => projects.filter(shouldKeepProject), [projects]);
  const totalPages = Math.max(1, Math.ceil(visibleProjects.length / Math.max(pageSize, 1)));
  const currentPageProjects = useMemo(() => {
    const start = (pageNum - 1) * pageSize;
    return visibleProjects.slice(start, start + pageSize);
  }, [pageNum, pageSize, visibleProjects]);

  useEffect(() => {
    if (pageNum > totalPages) {
      setPageNum(totalPages);
    }
  }, [pageNum, totalPages]);

  useEffect(() => {
    let alive = true;
    Promise.all([requestJson("/api/rules"), fetchAllProjects()])
      .then(([rulesPayload, projectsPayload]) => {
        if (!alive) {
          return;
        }
        const filteredCount = projectsPayload.allProjects.filter(shouldKeepProject).length;
        setRules(rulesPayload);
        setCategory(rulesPayload.categories?.[0]?.name || "");
        setProjects(projectsPayload.allProjects);
        setProjectSource(projectsPayload.source || "remote");
        setProjectWarning(projectsPayload.warning || "");
        setStatusText(buildStatusText(projectsPayload, filteredCount, 1, pageSize, Math.max(1, Math.ceil(filteredCount / pageSize))));
      })
      .catch((error) => {
        if (alive) {
          setStatusText(error.message);
        }
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    setStatusText(
      buildStatusText(
        { allProjects: projects, source: projectSource, warning: projectWarning },
        visibleProjects.length,
        pageNum,
        pageSize,
        totalPages,
      ),
    );
  }, [pageNum, pageSize, projectSource, projectWarning, projects, totalPages, visibleProjects.length]);

  useEffect(() => {
    if (!category) {
      return;
    }
    const localReviews = loadStoredReviews(category);
    setReviewMap(localReviews);

    let alive = true;
    requestJson(`/api/review-feedback?category=${encodeURIComponent(category)}`)
      .then((payload) => {
        if (!alive) {
          return;
        }
        const merged = mergeReviewMaps(localReviews, payload.items || {});
        setReviewMap(merged);
        persistStoredReviews(category, merged);
      })
      .catch(() => {});

    return () => {
      alive = false;
    };
  }, [category]);

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
          persistStoredReviews(category, nextValue);
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
          persistStoredReviews(category, nextValue);
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
      persistStoredReviews(category, nextValue);
      schedulePersistReview(project, nextRecord);
      return nextValue;
    });
  }

  async function refreshProjects() {
    try {
      setRefreshing(true);
      const payload = await fetchAllProjects();
      const filteredCount = payload.allProjects.filter(shouldKeepProject).length;
      setProjects(payload.allProjects);
      setProjectSource(payload.source || "remote");
      setProjectWarning(payload.warning || "");
      setPageNum(1);
      setStatusText(buildStatusText(payload, filteredCount, 1, pageSize, Math.max(1, Math.ceil(filteredCount / pageSize))));
    } catch (error) {
      setStatusText(error.message);
    } finally {
      setRefreshing(false);
    }
  }

  async function generateAdvice(project) {
    const projectId = project.id;
    try {
      setLoadingMap((current) => ({ ...current, [projectId]: true }));
        const result = await requestJson("/api/approve/remote-project", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ projectId, category }),
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
      setStatusText(`当前页 ${currentPageProjects.length} 个项目的建议已更新`);
    } catch (error) {
      setStatusText(error.message);
    } finally {
      setBatchBusy(false);
    }
  }

  return (
    <PageLayout wide scene="initiation" section="review-feedback">
      <header className="hero">
        <div>
          <p className="eyebrow">Review Feedback</p>
          <h1>项目建议复核</h1>
          <p className="hero-copy">
            这里只展示不处于“待立项”或“立项中”的项目，支持分页查看、逐条生成建议，以及按当前页批量生成大模型审批建议。
          </p>
        </div>
        <div className="hero-panel">
          <p className="panel-label">Current Scope</p>
          <h2>复核分页工作台</h2>
          <p className="hero-copy">
            大模型审批会优先使用已经落盘的项目正文，不再每次重新拉取远程接口。人工评价与建议复核结果会同步落盘，便于后续回溯和程序改进。
          </p>
        </div>
      </header>

      <main className="grid">
        <section className="card span-full">
          <div className="section-head">
            <div>
              <p className="panel-label">Filters</p>
              <h2>项目范围与本页生成</h2>
            </div>
            <div className="button-row">
              <button className="ghost-button" type="button" onClick={refreshProjects} disabled={refreshing}>
                {refreshing ? "刷新中..." : "刷新项目"}
              </button>
              <button
                className="primary-button"
                type="button"
                onClick={generateCurrentPageAdvice}
                disabled={batchBusy || !currentPageProjects.length || !category}
              >
                {batchBusy ? "本页生成中..." : "本页全部生成建议"}
              </button>
            </div>
          </div>

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
                自动排除项目状态或流程状态为“待立项”“立项中”的项目。
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

          <div className="table-wrap">
            <table className="compact-table review-feedback-table">
              <thead>
                <tr>
                  <th>项目简要信息</th>
                  <th>大模型审批建议</th>
                  <th>建议是否OK</th>
                  <th>不OK原因/改进建议</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {currentPageProjects.map((project) => {
                  const projectId = project.id;
                  const review = reviewMap[projectId] || {};
                  const loading = Boolean(loadingMap[projectId]);
                  return (
                    <tr key={projectId}>
                      <td>
                        <div className="review-project-info">
                          <strong>{projectDisplayValue(project, "projectName", "name", "id")}</strong>
                          <div>项目编码: {projectDisplayValue(project, "projectCode", "serialNo") || "-"}</div>
                          <div>项目经理: {projectDisplayValue(project, "managerName", "projectManagerName", "projectLeaderName") || "-"}</div>
                          <div>项目类型: {projectDisplayValue(project, "projectCategoryName", "projectFeeTypeName", "projectTypeName") || "-"}</div>
                          <div>项目状态: {buildProjectStatus(project)}</div>
                          <div>流程状态: {buildFlowStatus(project)}</div>
                        </div>
                      </td>
                      <td>
                        <ReviewAdviceCard record={review} />
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
                          placeholder="填写为什么不OK，或希望模型如何调整建议"
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
                            {loading ? "生成中..." : "生成建议"}
                          </button>
                          <button
                            className="table-button"
                            type="button"
                            onClick={() => window.open(buildUiUrl(`/project/${encodeURIComponent(projectId)}`), "_blank", "noopener,noreferrer")}
                          >
                            查看项目
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {!currentPageProjects.length ? (
                  <tr>
                    <td colSpan="5">
                      <div className="viewer-empty">没有符合条件的项目。</div>
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
