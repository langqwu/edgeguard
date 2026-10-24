# EdgeGuard · 断网可用的用电风险识别

> 在插座/配电回路侧采集电参量，用轻量模型判断**用电越界**（违规充电、大功率电器），
> **端侧判断、断网可用**；有网时上传样本，由**华为云**复盘并迭代模型后下发。

参加 **第十一届华为 ICT 大赛（2026-2027）中国创新赛 · 赛题1：基于华为云产品打造 AI 创新应用**
初赛材料截止：**2026-11-30**

---

## 📌 先读这三份

| 文档 | 内容 | 谁看 |
| --- | --- | --- |
| **[docs/00-project.md](docs/00-project.md)** | **总纲**：项目定位（竞赛非产品）、架构（端侧判断+云端进化）、核心设计决策、三条警戒线 | **全队必读** |
| [docs/01-competition.md](docs/01-competition.md) | 官方赛题原文、**评审权重（初赛创新 60% + 价值 40%）**、晋级规则、往年作品深度参考线 | 写材料的人 |
| [docs/03-plan.md](docs/03-plan.md) | 五周执行计划、分工、风险登记、**初赛不做清单** | 排期的人 |

其余文档：

| 文档 | 内容 |
| --- | --- |
| [docs/02-solution.md](docs/02-solution.md) | 技术方案：采集规格、特征、两个必做实验（少样本泛化/声电双模）、云端迭代机制、指标台账、演示脚本 |
| [docs/04-research.md](docs/04-research.md) | 调研附录：竞品拆解（云南电网/安科瑞）、我们的位置、政策证据、创新性四层判据、踩过的坑 |
| [docs/08-wiring-and-collection.md](docs/08-wiring-and-collection.md) | **实物操作手册**：PZEM 接线图、CT 安装、TTL 四线接法、上电验证、故障排查、安全红线 |
| [docs/09-option-a-testbox.md](docs/09-option-a-testbox.md) | **方案 A 详解**：现成计量插座/测试盒的三种类型、哪根线插哪个口、验收与排障 |

---

## 🎯 一句话定位

> **电网方案要有电网数据、判断在主站；电气厂商只能测电气参数；摄像头有盲区还侵犯隐私。**
> 我们给拿不到电网数据、又装不起摄像头的场景（宿舍、出租屋、群租房、小商铺），
> 一个**断网也能判断、只采电参量**的方案。

---

## ⚙️ 架构：端侧判断 + 云端进化

```
      端侧（离线可用）                      华为云（有网时）
 ──────────────────────          ───────────────────────────
   推理判断、本地告警        ──上传─→   误报样本 / 未知设备样本
                                          ↓ 批量复盘
   断网时照常工作            ←─下发─    重训 + 模型版本发布
   （继续用现行模型）                    （RDS / Redis / MaaS）
```

**端侧负责"当场判断"，云端负责"持续变聪明"。**

---

## 🚦 当前阶段：只做初赛要的五件事

| # | 交付物 | 状态 |
| --- | --- | --- |
| 1 | 四类负载真实波形（各 ≥20 段） | ⏳ 待硬件 |
| 2 | 三分类模型 + 混淆矩阵/准确率/误报率 | ⏳ 待数据 |
| 3 | 关键代码片段（2–3 段 + 注释） | ⏳ 待模型 |
| 4 | 60 秒断网演示视频 | ⏳ 待模型 |
| 5 | 【模板1】Word 定稿 | ⏳ 待 1–4 |

**初赛不做**：继电器控制、禁用/申诉、云上部署、开发板、前端页面、产品化设计。
（完整清单见 [docs/03-plan.md](docs/03-plan.md)）

---

## 🚀 快速开始

### 环境

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 用合成数据验证流水线（无硬件也能跑）

```bash
python -m src.synth --out data/raw --per-class 6
python -m src.analyze --plot --features
python -m src.train --leave-one-out
```

> ⚠️ 合成数据仅用于流程验证，**不得作为实验指标来源**。

### 真实采集（需接好 PZEM-004T）

**接线步骤见 [docs/08-wiring-and-collection.md](docs/08-wiring-and-collection.md)。**

```bash
python -m tools.list_ports                        # 找到 COMx
python -m tools.pzem_probe --port COM3            # 探测地址（出厂可能是 0xF8 或 0x01）
python -m src.collect --port COM3 --label e_bike_charger --minutes 30 --plot
python -m src.analyze --plot --features
python -m src.train --leave-one-out
```

> 采集程序默认 `--address auto`，会自动探测 `0xF8` / `0x01`，不必手动指定。

---

## 📁 仓库结构

```
.
├── README.md
├── requirements.txt
├── LICENSE
├── docs/
│   ├── 00-project.md        # 总纲（定位与架构）
│   ├── 01-competition.md    # 赛题与评审规则（官方核实）
│   ├── 02-solution.md       # 技术方案
│   ├── 03-plan.md           # 执行计划与设备
│   ├── 04-research.md       # 调研与竞品
│   └── 08-wiring-and-collection.md  # 接线与采集操作手册
├── src/
│   ├── pzem.py              # PZEM-004T Modbus-RTU 驱动（零依赖）
│   ├── collect.py           # 采集：存 CSV + 元数据 + 实时曲线
│   ├── analyze.py           # 清洗、重采样、特征、可视化
│   ├── train.py             # 基线模型、留一验证、混淆矩阵
│   └── synth.py             # 合成数据（仅流程验证）
├── tools/
│   ├── list_ports.py        # 串口枚举
│   ├── pzem_probe.py        # 地址探测（第一次上电先跑这个）
│   └── pdf_extract.py       # PDF 文本提取
├── tests/
│   └── test_pzem_selftest.py  # 无硬件自测（桩串口）
├── sources/                 # 官方赛题原文、手册、标准等证据
└── data/                    # 采集数据（不入库）
```

---

## 🔐 数据与隐私

- 原始用电数据只留本地 `data/`（已 `.gitignore`），**不入库**
- 采集需告知并取得参与者同意，只采比赛所需电参量
- 公开发布的示例数据会脱敏或使用合成数据，并明确标注

## ⚡ 安全须知（220V 实验）

- 接线**必须断电操作**，接完先验电
- CT 互感器**只套火线（L）**，不套零线、不套双线
- 接线端全部放入**带保护门**插座盒
- **不在宿舍做长时间大功率实验**
- 尽量使用实验室场地，由有经验者陪同

## 📄 开源许可

[MIT](LICENSE)

## 👥 团队

- 队伍：待填写 ｜ 学校：待填写 ｜ 指导教师：待填写

---

## 🔍 立项审计（可复用技能）

- **[docs/05-audit.md](docs/05-audit.md)** —— 对本项目的立意审计：方向对头、完整度 6/10、三个致命缺口、下一步唯一动作
- **[skills/project-preflight-audit/SKILL.md](skills/project-preflight-audit/SKILL.md)** —— 通用"项目立意审计"技能，任何项目起步阶段都能用

> 审计结论：**方向对头，但零真实数据是致命缺口**。
> 下一步唯一动作：**本周完成 H1 最小验证（借 3 类负载各采 3–5 段，画图 + 跑一次留一验证）**。
---

## 📊 拿奖概率评估

- **[docs/06-odds.md](docs/06-odds.md)** —— 诚实版概率评估：漏斗结构、六维竞争位、四种情形下的通过率、敏感性分析

> 结论：**认真做到位，过初赛约 35–50%；拿到国家级奖约 30–50%**（进了总决赛必有奖）。
> 拿一等奖约 2–8%，属小概率。
> **最关键的杠杆：真实数据（+15~20 个百分点）与路径 B（+8~12 个百分点），两者都在我们手里。**
---

## ⏳ 等设备期间做什么

- **[docs/07-waiting-tasks.md](docs/07-waiting-tasks.md)** —— 零硬件依赖的并行任务清单

> 三个不靠设备就能补的缺口：**码道留痕（30 分钟）、公开数据集基线（半天）、断网演示脚本（2–3 小时）**。
> 等 PZEM 一到，直接进 W2，不用从零开始。