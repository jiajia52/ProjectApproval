import { Link } from "react-router-dom";
import PageLayout from "../components/PageLayout";
import { normalizeScene } from "../api";

const sceneCopy = {
  initiation: {
    eyebrow: "Initiation Workspace",
    title: "项目立项首页",
    description: "首页只保留场景入口和说明，不再直接铺开展示项目列表。需要查看列表、复核结果或技能配置时，从上方菜单进入对应页面。",
    statusTitle: "当前场景",
    statusText: "立项场景默认聚焦项目申报与审批准备。",
  },
  acceptance: {
    eyebrow: "Acceptance Workspace",
    title: "项目验收首页",
    description: "验收首页不直接展示项目列表。先进入菜单，再按需打开验收项目列表、复核结果或技能配置页面。",
    statusTitle: "当前场景",
    statusText: "验收场景聚焦验收范围、验收明细和交付佐证。",
  },
  task_order: {
    eyebrow: "Task Order Workspace",
    title: "任务单首页",
    description: "任务单板块与立项、验收平级，独立承载任务单列表、任务流和详情查看，不再挂在立项内部。",
    statusTitle: "当前场景",
    statusText: "任务单场景聚焦任务拆解、人员配置、费用评估和技术要求。",
  },
};

export default function SceneHomePage({ scene = "initiation" }) {
  const activeScene = normalizeScene(scene);
  const copy = sceneCopy[activeScene];
  const scenePath = activeScene === "task_order" ? "/task-order" : `/${activeScene}`;

  return (
    <PageLayout scene={activeScene} section="home">
      <header className="hero">
        <div>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1>{copy.title}</h1>
          <p className="hero-copy">{copy.description}</p>
        </div>
        <div className="hero-panel">
          <p className="panel-label">Status</p>
          <h2>{copy.statusTitle}</h2>
          <p className="hero-copy">{copy.statusText}</p>
        </div>
      </header>

      <main className="grid">
        <section className="card span-2">
          <div className="section-head">
            <div>
              <p className="panel-label">Navigation</p>
              <h2>从菜单进入功能页</h2>
            </div>
          </div>
          <p className="category-meta">
            顶部只保留场景切换和菜单按钮。项目列表、建议复核、Skill 调整已经收进菜单，不再常驻平铺。
          </p>
        </section>

        <section className="card">
          <div className="section-head">
            <div>
              <p className="panel-label">Quick Link</p>
              <h2>直接进入项目列表</h2>
            </div>
          </div>
          <Link className="primary-button home-action-link" to={`${scenePath}/projects`}>
            打开项目列表
          </Link>
        </section>
      </main>
    </PageLayout>
  );
}
