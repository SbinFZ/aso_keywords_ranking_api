# App Store Keyword Ranking & Analysis Service

> A professional toolset for App Store (ASO) keyword research, popularity analysis, and ranking monitoring.

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Framework-green.svg)
![License](https://img.shields.io/badge/license-MIT-red.svg)

**Keywords:** `aso`, `app-store`, `keyword-research`, `app-ranking`, `itunes-api`, `fastapi`

---

这是一个用于 App Store 关键词挖掘、热度分析和排名监控的工具集。它基于 Apple 官方接口，能够帮助 ASO (App Store Optimization) 团队快速评估关键词价值，监控自家应用在特定关键词下的排名表现。

## 核心功能

1.  **关键词热度 (Popularity):** 查询关键词的流行度分数 (0-100)。
    *   *独家特性:* 当官方 API 未返回热度时，自动根据搜索联想词 (Hints) 的排名进行智能估算，确保数据覆盖率。
2.  **排名监控 (Ranking):** 查询指定 App 在特定关键词下的实时排名 (Rank) 及搜索结果总数 (Results Count)。
3.  **竞品分析:** 识别特定关键词下的 Top 1 应用，了解流量主要去向。
4.  **搜索联想 (Hints):** 获取用户在搜索框输入时的下拉推荐词。
5.  **热搜趋势 (Trends):** 获取当前 App Store 的热门搜索榜单。

## 快速上手

### 1. 环境准备

确保你的电脑已安装 Python 3.8 或更高版本。

```bash
# 克隆项目到本地
git clone <your-repo-url>
cd aso_keywords_ranking_api

# 创建虚拟环境 (推荐)
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 运行分析脚本 (推荐)

项目内置了两个强大的分析脚本，位于 `scripts/` 目录下。

#### A. 竞品关键词挖掘与排名分析

此脚本会分析一组高价值的竞品关键词 (如 "math solver", "ai tutor" 等)，并检查 **Sovi AI** (或其他指定 App) 在这些词下的排名。

```bash
# 运行分析脚本
PYTHONPATH=. python3 scripts/analyze_competitor_keywords.py
```

**输出结果:**
脚本运行完成后，会在项目根目录生成 Markdown (`.md`) 和 JSON (`.json`) 格式的报告。

**报告示例:**
| Keyword | Rank (Sovi) | Results | Priority | Score | Top App | Source |
|---|---|---|---|---|---|---|
| math solver | **#53** | 184 | 100 | 100.00 | Photomath | MZSearchHints |
| picture math | - | 179 | 100 | 100.00 | Photomath | MZSearchHints |

*   **Rank:** Sovi AI 的当前排名 ("-" 表示未进入前 200 名)。
*   **Results:** 竞价程度参考，结果数越多竞争越激烈。
*   **Priority/Score:** 关键词热度 (100 为最高)。
*   **Top App:** 该关键词下的第一名应用。

#### B. 修改目标 App

如果你需要分析其他 App，只需打开脚本文件 (如 `scripts/analyze_competitor_keywords.py`)，修改顶部的 `TARGET_APP_ID` 即可：

```python
# 修改为你想要监控的 App ID
TARGET_APP_ID = "你的AppID" 
```

### 3. 启动 API 服务 (开发人员用)

如果你需要将此功能集成到内部后台或 Dashboard，可以启动 REST API 服务。

```bash
uvicorn app.main:app --reload --port 8000
```

*   **API 文档:** `http://127.0.0.1:8000/docs`
*   **热度查询:** `GET /v1/keywords/popularity?keyword=tiktok&country=US`
*   **联想词:** `GET /v1/keywords/hints?keyword=chat`

## 常见问题

*   **Q: 为什么 Priority 有时候是 0？**
    *   A: Apple 并不对所有词都返回官方热度。如果脚本显示 Priority 为 0 且 Score 为 0，说明该词在联想词中也未出现，可能搜索量极低。
*   **Q: Score 和 Priority 有什么区别？**
    *   A: `Priority` 是原始值。`Score` 是归一化后的 0-100 分数。如果官方未返回 Priority，我们会根据联想词排名给出一个估算的 `Score` (如 100, 90, 80...)。
*   **Q: 如何切换国家？**
    *   A: 脚本默认查询 **US** 市场。如需查询其他国家，请在代码调用 `fetch_keyword_popularity` 或 `fetch_search_rank` 时传入 `country="CN"` (或 JP, UK 等)。

## 目录结构

*   `app/`: 核心代码逻辑
    *   `mzsearchhints.py`: 处理 Apple 联想与热度接口
    *   `itunes_search.py`: 处理排名查询接口
    *   `storefronts.py`: 国家/地区 ID 映射
*   `scripts/`: 业务分析脚本
    *   `analyze_competitor_keywords.py`: 竞品词分析
    *   `analyze_sovi_keywords.py`: 品牌词分析
*   `tests/`: 自动化测试用例

## 声明

本项目仅供内部数据分析与学习使用，请勿用于非授权的商业用途。
