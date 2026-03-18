import { useEffect, useState } from "react";
import { requestJson } from "../api";
import PageLayout from "../components/PageLayout";

function buildSkillSummary(items, activeSkillId) {
  const activeItem = items.find((item) => item.skill_id === activeSkillId);
  return {
    total: items.length,
    activeName: activeItem?.skill_name || "-",
    modifiedAt: activeItem?.modified_at || "-",
  };
}

function SkillsContent() {
  const [skillFiles, setSkillFiles] = useState([]);
  const [activeSkillId, setActiveSkillId] = useState("");
  const [editorText, setEditorText] = useState("");
  const [activeMeta, setActiveMeta] = useState(null);
  const [statusText, setStatusText] = useState("等待加载 Skill 文件。");
  const [saving, setSaving] = useState(false);

  async function openSkillFile(skillId, currentItems = skillFiles) {
    const payload = await requestJson(`/api/skill-files/${encodeURIComponent(skillId)}`);
    setActiveSkillId(skillId);
    setEditorText(payload.content || "");
    const matched = currentItems.find((item) => item.skill_id === skillId) || null;
    setActiveMeta(
      matched
        ? {
            ...matched,
            relative_path: payload.relative_path || matched.relative_path,
          }
        : payload,
    );
    setStatusText(`已载入 ${matched?.skill_name || skillId}。`);
  }

  async function loadSkillList(preferredSkillId = "") {
    const payload = await requestJson("/api/skill-files");
    const items = payload.items || [];
    setSkillFiles(items);
    const nextSkillId = preferredSkillId || activeSkillId || items[0]?.skill_id || "";
    if (nextSkillId) {
      await openSkillFile(nextSkillId, items);
      return;
    }
    setActiveSkillId("");
    setActiveMeta(null);
    setEditorText("");
    setStatusText("当前没有可编辑的 Skill 文件。");
  }

  useEffect(() => {
    loadSkillList().catch((error) => setStatusText(error.message || "加载 Skill 文件失败。"));
  }, []);

  async function saveSkillFile() {
    if (!activeSkillId) {
      return;
    }
    setSaving(true);
    try {
      await requestJson(`/api/skill-files/${encodeURIComponent(activeSkillId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: editorText }),
      });
      await loadSkillList(activeSkillId);
      setStatusText("Skill 文件已保存。");
    } catch (error) {
      setStatusText(error.message || "Skill 文件保存失败。");
    } finally {
      setSaving(false);
    }
  }

  const summary = buildSkillSummary(skillFiles, activeSkillId);

  return (
    <>
      <header className="hero">
        <div>
          <p className="eyebrow">Skill Editor</p>
          <h1>Skill 文件管理</h1>
          <p className="hero-copy">
            这里直接展示 `skills/` 下各个 `SKILL.md` 文件，点击后即可查看并修改原始内容。
          </p>
        </div>
        <div className="hero-panel">
          <p className="panel-label">Overview</p>
          <h2>当前编辑状态</h2>
          <p className="hero-copy">
            共 {summary.total} 个 Skill 文件，当前选中：{summary.activeName}。
          </p>
        </div>
      </header>

      <main className="grid">
        <section className="card">
          <div className="section-head">
            <div>
              <p className="panel-label">Files</p>
              <h2>Skill 文件列表</h2>
            </div>
            <button
              className="ghost-button"
              type="button"
              onClick={async () => {
                try {
                  await loadSkillList(activeSkillId);
                  setStatusText("Skill 文件列表已刷新。");
                } catch (error) {
                  setStatusText(error.message || "刷新 Skill 列表失败。");
                }
              }}
            >
              刷新列表
            </button>
          </div>
          <div className="output-list">
            {skillFiles.map((item) => (
              <button
                key={item.skill_id}
                type="button"
                className={`output-item skill-file-item ${activeSkillId === item.skill_id ? "active" : ""}`}
                onClick={() => openSkillFile(item.skill_id)}
              >
                <strong>{item.skill_name}</strong>
                <p>{item.review_point || "-"}</p>
                <p>{item.modified_at}</p>
                <code>{item.relative_path}</code>
              </button>
            ))}
          </div>
        </section>

        <section className="card span-2">
          <div className="section-head">
            <div>
              <p className="panel-label">Editor</p>
              <h2>SKILL.md 编辑器</h2>
            </div>
            <div className="button-row">
              <button className="ghost-button" type="button" onClick={() => activeSkillId && openSkillFile(activeSkillId)}>
                重新载入
              </button>
              <button className="primary-button" type="button" onClick={saveSkillFile} disabled={!activeSkillId || saving}>
                {saving ? "保存中..." : "保存文件"}
              </button>
            </div>
          </div>
          {activeMeta ? (
            <>
              <div className="source-list">
                <div className="source-item">
                  <strong>文件路径</strong>
                  <code>{activeMeta.relative_path}</code>
                </div>
                <div className="source-item">
                  <strong>最后修改</strong>
                  <code>{activeMeta.modified_at || summary.modifiedAt}</code>
                </div>
              </div>
              <label className="textarea-field">
                <textarea spellCheck="false" value={editorText} onChange={(event) => setEditorText(event.target.value)} />
              </label>
            </>
          ) : (
            <div className="result-box">请选择一个 Skill 文件。</div>
          )}
        </section>

        <section className="card span-full">
          <div className="section-head">
            <div>
              <p className="panel-label">Status</p>
              <h2>操作结果</h2>
            </div>
          </div>
          <div className="result-box">{statusText}</div>
        </section>
      </main>
    </>
  );
}

export default function SkillsPage() {
  return (
    <PageLayout>
      <SkillsContent />
    </PageLayout>
  );
}
