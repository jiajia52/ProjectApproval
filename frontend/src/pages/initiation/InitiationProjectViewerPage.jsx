import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import PageLayout from "../../components/PageLayout";
import { requestJson } from "../../api";

import {
  EXCEL_VALUE_ONLY_SUBCATEGORIES,
  normalizeList,
  formatValue,
  definitionPairs,
  formatCurrency,
  firstMeaningful,
  normalizeScopeRows,
  normalizeSoftwareScopeRows,
  buildProjectValueEntriesById,
  buildBudgetSummary,
  buildProjectBadges,
  resolveExcelLayout,
  filterSectionsByData,
  resolveRuleCategoryFromSummary,
  renderOverviewItems,
  ImageGallery,
  ProjectContentBlocks,
  OkrBoard,
  SystemScopeBoard,
  SystemProjectScopeBoard,
  approvalToneClass,
  normalizeApprovalDetailItems,
  formatApprovalTimestamp,
  ApprovalInfoCard,
  ScopeTable,
  SoftwareScopeTable,
  ProjectSolutionBlocks,
  ProjectValueCards,
  TamModelBoard,
  MilestoneTable,
  parseNumeric,
  HistoryInvestmentPanel,
  buildCostChangeMetric,
  PatchedHistoryInvestmentPanel,
  BudgetBoard,
  normalizeArchitectureReviewGroups,
  filterArchitectureReviewPayload,
  ArchitectureReviewDetailDialog,
  ArchitectureReviewPanel,
  OrganizationBoard,
  formatApprovalResult,
} from "./projectViewerShared";

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

  function renderCostChange() {
    const costChange = documentPayload?.cost_change || {};
    const costChangeMetric = buildCostChangeMetric(documentPayload);
    const trendValue = parseNumeric(costChangeMetric?.secondThirdTrend);
    const trendText = Number.isFinite(trendValue) ? `${trendValue.toFixed(2)}%` : "";
    if (activeTab === "history") {
      return (
        <>
          <div id="viewer-content-panel">
            <p className="category-meta">历史投入分析</p>
            <PatchedHistoryInvestmentPanel documentPayload={documentPayload} />
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
          <p className="category-meta">费用变化点</p>
          <article className="viewer-form-card cost-change-card">
            <div className="viewer-form-section-title">基本信息</div>
            <div className="viewer-value-grid viewer-value-grid-4">
              <label className="viewer-value-field">
                <span>维度</span>
                <div className="viewer-value-box">{formatValue(costChangeMetric?.dimension || "-")}</div>
              </label>
              <label className="viewer-value-field">
                <span>{costChangeMetric?.firstLabel || "2024年目标"}</span>
                <div className="viewer-value-box">{formatCurrency(firstMeaningful(costChangeMetric?.firstValue, 0))}</div>
              </label>
              <label className="viewer-value-field">
                <span>{costChangeMetric?.secondLabel || "2025年目标"}</span>
                <div className="viewer-value-box">{formatCurrency(firstMeaningful(costChangeMetric?.secondValue, 0))}</div>
              </label>
              <label className="viewer-value-field">
                <span>
                  {costChangeMetric?.thirdLabel || "2026年目标"}
                  {trendText ? <em className="cost-change-trend">↘ {trendText}</em> : null}
                </span>
                <div className="viewer-value-box">{formatCurrency(firstMeaningful(costChangeMetric?.thirdValue, 0))}</div>
              </label>
            </div>
            <label className="viewer-value-field">
              <span>费用变化说明</span>
              <div className="viewer-value-box viewer-value-box-large">
                {costChangeMetric?.content || costChange.reason || "暂无说明"}
              </div>
            </label>
          </article>
        </div>
        <div id="viewer-side-panel">
          {definitionPairs([
            { label: "固定项目", value: costChange.fixed_project ? "是" : "否" },
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
    <PageLayout wide scene="initiation" section="projects">
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
