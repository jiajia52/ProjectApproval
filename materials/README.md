# 材料目录说明

该目录用于承载“项目全流程”后续补充材料，按业务阶段拆分，避免继续把立项、任务单、验收资料混放在 `docs/` 和 `data/` 中。

当前目录已经作为阶段材料主目录使用，立项资料已迁入 `materials/initiation/`。

## 目录约定

```text
materials/
  initiation/
    README.md
    interfaces/
    pages/
    rules/
    samples/
    assets/
  task_order/
    README.md
    interfaces/
    pages/
    rules/
    samples/
    assets/
  acceptance/
    README.md
    interfaces/
    pages/
    rules/
    samples/
    assets/
```

## 子目录用途

- `interfaces/`: 接口说明、接口样例、字段映射
- `pages/`: 页面原型、字段清单、交互说明
- `rules/`: 规则矩阵、评审点、状态流转说明
- `samples/`: 样例报文、导入数据、脱敏单据
- `assets/`: 截图、附件、示意图

## 当前建议

- 立项材料统一放在 `materials/initiation/`
- 后续新增“任务单”和“验收”材料时，直接放到本目录下对应阶段
- `docs/` 只保留项目级说明和整体方案，避免再次混放业务材料
