<div align="center">

<img src="assets/logo-ver2.png" alt="KnowMeTutor" width="140" style="border-radius: 15px;">

# KnowMeTutor：智能体原生的个性化辅导

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-000000?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=flat-square)](LICENSE)
[核心亮点](#key-features) · [快速开始](#get-started) · [探索 KnowMeTutor](#explore-knowmetutor) · [TutorBot](#tutorbot)

</div>

<a id="key-features"></a>
## ✨ 核心亮点

- **统一聊天工作区** — 五种模式，同一条对话线。聊天、深度解题、测验生成、深度研究与数学动画共享上下文：从闲聊到多智能体解题、出题、再深入调研，消息不丢。
- **个人 TutorBot** — 不是聊天机器人，而是自主导师。每个 TutorBot 拥有独立工作区、记忆、人格与技能；可提醒、可学新能力、随你成长。由 [nanobot](https://github.com/HKUDS/nanobot) 驱动。
- **引导式学习** — 把资料变成结构化、可视化的学习路径：多步计划、每步交互页面、步步可讨论。
- **知识中枢** — 上传 PDF、Markdown、纯文本构建 RAG 知识库；用彩色笔记本跨会话整理洞见。文档主动参与每次对话。
- **持久记忆** — 持续勾勒你的学习画像：学过什么、如何学习、目标何在。全功能与 TutorBot 共享，越用越准。

---

<a id="get-started"></a>
## 🚀 快速开始

### 方案 A — 引导式安装（推荐）

一条交互脚本完成依赖安装、环境配置、连通性检测与启动，无需手改 `.env`。

```bash
git clone https://github.com/HKUDS/KnowMeTutor.git
cd KnowMeTutor

# 创建 Python 环境
conda create -n deeptutor python=3.11 && conda activate deeptutor
# 或：python -m venv .venv && source .venv/bin/activate

# 启动引导
python scripts/start_tour.py
```

向导会引导完成 **Web 模式**（推荐）配置：选择依赖配置、安装 pip + npm、拉起临时服务并在浏览器打开设置页；四步引导配置 LLM、嵌入与搜索并现场测通；完成后自动按配置重启。

完成后访问 [http://localhost:3782](http://localhost:3782)。

<a id="option-b-manual"></a>
### 方案 B — 本地手动安装

若希望完全自控，可自行安装与配置。

**1. 安装依赖**

```bash
git clone https://github.com/HKUDS/KnowMeTutor.git
cd KnowMeTutor

conda create -n deeptutor python=3.11 && conda activate deeptutor
pip install -e ".[server]"

# 前端
cd web && npm install && cd ..
```

**2. 配置环境**

```bash
cp .env.example .env
```

编辑 `.env`，至少填写必填项：

```dotenv
# LLM（必填）
LLM_BINDING=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-xxx
LLM_HOST=https://api.openai.com/v1

# 嵌入（知识库必填）
EMBEDDING_BINDING=openai
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_API_KEY=sk-xxx
EMBEDDING_HOST=https://api.openai.com/v1
EMBEDDING_DIMENSION=3072
```

<details>
<summary><b>支持的 LLM 提供商</b></summary>

| 提供商 | Binding | 默认 Base URL |
|:--|:--|:--|
| AiHubMix | `aihubmix` | `https://aihubmix.com/v1` |
| Anthropic | `anthropic` | `https://api.anthropic.com/v1` |
| Azure OpenAI | `azure_openai` | — |
| BytePlus | `byteplus` | `https://ark.ap-southeast.bytepluses.com/api/v3` |
| BytePlus Coding Plan | `byteplus_coding_plan` | `https://ark.ap-southeast.bytepluses.com/api/coding/v3` |
| Custom (OpenAI-compat) | `custom` | — |
| DashScope (Qwen) | `dashscope` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek | `deepseek` | `https://api.deepseek.com` |
| Gemini | `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| GitHub Copilot | `github_copilot` | `https://api.githubcopilot.com` |
| Groq | `groq` | `https://api.groq.com/openai/v1` |
| MiniMax | `minimax` | `https://api.minimax.io/v1` |
| Mistral | `mistral` | `https://api.mistral.ai/v1` |
| Moonshot (Kimi) | `moonshot` | `https://api.moonshot.ai/v1` |
| Ollama | `ollama` | `http://localhost:11434/v1` |
| OpenAI | `openai` | `https://api.openai.com/v1` |
| OpenAI Codex | `openai_codex` | `https://chatgpt.com/backend-api` |
| OpenRouter | `openrouter` | `https://openrouter.ai/api/v1` |
| OpenVINO Model Server | `ovms` | `http://localhost:8000/v3` |
| Qianfan (Ernie) | `qianfan` | `https://qianfan.baidubce.com/v2` |
| SiliconFlow | `siliconflow` | `https://api.siliconflow.cn/v1` |
| Step Fun | `stepfun` | `https://api.stepfun.com/v1` |
| vLLM | `vllm` | `http://localhost:8000/v1` |
| VolcEngine | `volcengine` | `https://ark.cn-beijing.volces.com/api/v3` |
| VolcEngine Coding Plan | `volcengine_coding_plan` | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| Xiaomi MIMO | `xiaomi_mimo` | `https://api.xiaomimimo.com/v1` |
| Zhipu AI (GLM) | `zhipu` | `https://open.bigmodel.cn/api/paas/v4` |

</details>

<details>
<summary><b>支持的嵌入（Embedding）提供商</b></summary>

嵌入使用与 LLM 相同的提供商列表。常见选择：

| 提供商 | Binding | 模型示例 |
|:--|:--|:--|
| OpenAI | `openai` | `text-embedding-3-large` |
| DashScope | `dashscope` | `text-embedding-v3` |
| Ollama | `ollama` | `nomic-embed-text` |
| SiliconFlow | `siliconflow` | `BAAI/bge-m3` |
| vLLM | `vllm` | 任意嵌入模型 |
| 任意 OpenAI 兼容 | `custom` | — |

</details>

<details>
<summary><b>支持的联网搜索提供商</b></summary>

| 提供商 | 环境变量键 | 说明 |
|:--|:--|:--|
| Brave | `BRAVE_API_KEY` | 推荐，有免费额度 |
| Tavily | `TAVILY_API_KEY` | |
| Jina | `JINA_API_KEY` | |
| SearXNG | — | 自托管，无需 API Key |
| DuckDuckGo | — | 无需 API Key |
| Perplexity | `PERPLEXITY_API_KEY` | 需要 API Key |

</details>

**3. 启动服务**

```bash
# 后端（FastAPI）
python -m deeptutor.api.run_server

# 前端（Next.js）— 另开终端
cd web && npm run dev -- -p 3782
```

| 服务 | 默认端口 |
|:---:|:---:|
| 后端 | `8001` |
| 前端 | `3782` |

浏览器打开 [http://localhost:3782](http://localhost:3782)。

### 方案 C — Docker 部署

Docker 将前后端打包为单容器，本机无需 Python/Node。任选其一：

**1. 配置环境变量**（两种方式均需）

```bash
git clone https://github.com/HKUDS/KnowMeTutor.git
cd KnowMeTutor
cp .env.example .env
```

编辑 `.env`，填写必填项（与[方案 B](#option-b-manual)相同）。

**2a. 拉取官方镜像（推荐）**

镜像发布于 [GitHub Container Registry](https://github.com/HKUDS/KnowMeTutor/pkgs/container/deeptutor)，支持 `linux/amd64` 与 `linux/arm64`。

```bash
docker compose -f docker-compose.ghcr.yml up -d
```

固定版本可编辑 `docker-compose.ghcr.yml` 中的镜像标签：

```yaml
image: ghcr.io/hkuds/deeptutor:1.0.0  # 或 :latest
```

**2b. 源码构建**

```bash
docker compose up -d
```

本地根据 `Dockerfile` 构建并启动。

**3. 验证与管理**

容器健康后打开 [http://localhost:3782](http://localhost:3782)。

```bash
docker compose logs -f   # 查看日志
docker compose down      # 停止并移除容器
```

<details>
<summary><b>云端 / 远程部署</b></summary>

远程部署时，浏览器需知晓后端公网地址。在 `.env` 中增加：

```dotenv
NEXT_PUBLIC_API_BASE_EXTERNAL=https://your-server.com:8001
```

前端启动脚本会在运行时应用，无需重新构建。

</details>

<details>
<summary><b>开发模式（热重载）</b></summary>

叠加 dev 覆盖以挂载源码并热重载：

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

`deeptutor/`、`scripts/`、`web/` 的修改会即时生效。

</details>

<details>
<summary><b>自定义端口</b></summary>

在 `.env` 中覆盖：

```dotenv
BACKEND_PORT=9001
FRONTEND_PORT=4000
```

然后重启：

```bash
docker compose up -d     # 或 docker compose -f docker-compose.ghcr.yml up -d
```

</details>

<details>
<summary><b>数据持久化</b></summary>

用户数据与知识库通过卷映射到本地：

| 容器内路径 | 宿主机路径 | 内容 |
|:---|:---|:---|
| `/app/data/user` | `./data/user` | 设置、记忆、工作区、会话、日志 |
| `/app/data/knowledge_bases` | `./data/knowledge_bases` | 上传文档与向量索引 |

`docker compose down` 后目录仍保留，下次 `up` 会复用。

</details>

<details>
<summary><b>环境变量参考</b></summary>

| 变量 | 必填 | 说明 |
|:---|:---:|:---|
| `LLM_BINDING` | **是** | LLM 提供商（`openai`、`anthropic` 等） |
| `LLM_MODEL` | **是** | 模型名（如 `gpt-4o`） |
| `LLM_API_KEY` | **是** | API 密钥 |
| `LLM_HOST` | **是** | API 地址 |
| `EMBEDDING_BINDING` | **是** | 嵌入提供商 |
| `EMBEDDING_MODEL` | **是** | 嵌入模型名 |
| `EMBEDDING_API_KEY` | **是** | 嵌入 API 密钥 |
| `EMBEDDING_HOST` | **是** | 嵌入端点 |
| `EMBEDDING_DIMENSION` | **是** | 向量维度 |
| `SEARCH_PROVIDER` | 否 | 搜索提供商（`tavily`、`jina`、`serper`、`perplexity` 等） |
| `SEARCH_API_KEY` | 否 | 搜索 API 密钥 |
| `BACKEND_PORT` | 否 | 后端端口（默认 `8001`） |
| `FRONTEND_PORT` | 否 | 前端端口（默认 `3782`） |
| `NEXT_PUBLIC_API_BASE_EXTERNAL` | 否 | 云端部署时后端公网 URL |
| `DISABLE_SSL_VERIFY` | 否 | 关闭 SSL 校验（默认 `false`） |

</details>

---

<a id="explore-knowmetutor"></a>
## 📖 探索 KnowMeTutor

<div align="center">
<img src="assets/figs/deeptutor-architecture.png" alt="KnowMeTutor 架构" width="800">
</div>

### 💬 聊天 — 统一智能工作区

<div align="center">
<img src="assets/figs/dt-chat.png" alt="聊天工作区" width="800">
</div>

五种模式共处同一工作区，由统一上下文管理串联：历史、知识库与引用跨模式保留，同一主题下可随时切换。

| 模式 | 作用 |
|:---|:---|
| **聊天** | 工具增强对话：RAG、联网搜索、代码执行、深度推理、头脑风暴、论文检索，按需组合。 |
| **深度解题** | 多智能体解题：规划、检索、求解与验证，步步可溯源引用。 |
| **测验生成** | 基于知识库出题，内置校验。 |
| **深度研究** | 主题拆解、并行调研 RAG、网络与论文，输出带引用报告。 |
| **数学动画** | 基于 Manim 将数学概念可视化为动画与分镜。 |

工具与工作流解耦：每种模式下你可自选启用哪些工具、用几个、或完全不用；流程负责推理节奏，工具由你编排。

> 从快速聊天起步，难题切到深度解题，自测用测验，再开深度研究深挖，同一条对话线贯穿始终。

### 🎓 引导式学习 — 可视化、分步掌握

<div align="center">
<img src="assets/figs/dt-guide.png" alt="引导式学习" width="800">
</div>

将个人材料变成结构化、多步学习路径：给出主题，可选关联笔记本记录，KnowMeTutor 将：

1. **设计学习计划** — 从材料中提炼 3 到 5 个递进知识点。
2. **生成交互页面** — 每点对应富视觉 HTML 页面，含讲解、图示与示例。
3. **上下文问答** — 每步旁路聊天，深入探讨。
4. **学习小结** — 结束后汇总所学。

会话可暂停、恢复或回看任一步。

### 📚 知识管理 — 学习基础设施

<div align="center">
<img src="assets/figs/dt-knowledge.png" alt="知识管理" width="800">
</div>

在此构建与管理驱动全局的文档集合。

- **知识库** — 上传 PDF、TXT、Markdown，形成可检索、RAG 就绪的集合；可增量追加。
- **笔记本** — 跨会话整理学习记录；聊天、引导学习、深度研究的洞见可按色分类保存。

知识库不是冷存储，它主动参与每次对话、研究与学习路径。

### 🧠 记忆 — 与你一同成长

<div align="center">
<img src="assets/figs/dt-memory.png" alt="记忆" width="800">
</div>

KnowMeTutor 从两个互补维度持续理解你：

- **摘要** — 学习进度流水账：学过什么、探索过哪些主题、理解如何演进。
- **学习画像** — 学习者身份：偏好、水平、目标与沟通风格，随交互自动精炼。

记忆在全功能与 TutorBot 间共享；用得越多，越贴合你。

---

<a id="tutorbot"></a>
### 🦞 TutorBot — 持久、自主的 AI 导师

<div align="center">
<img src="assets/figs/tutorbot-architecture.png" alt="TutorBot 架构" width="800">
</div>

TutorBot 不是聊天机器人，它是基于 [nanobot](https://github.com/HKUDS/nanobot) 的持久、可多实例智能体。每个实例独立循环、工作区、记忆与人格；你可同时运行多个角色，各自演进。

<div align="center">
<img src="assets/figs/tb.png" alt="TutorBot" width="800">
</div>

- **Soul 模板** — 通过可编辑 Soul 文件定义人格、语气与教学理念；可选内置原型或完全自定义。
- **独立工作区** — 每实例独立目录：记忆、会话、技能与配置隔离，仍可访问 KnowMeTutor 共享知识层。
- **主动心跳** — 不止被动回复：心跳系统支持定期学习提醒、复习与计划任务。
- **完整工具** — RAG、代码执行、联网、论文检索、深度推理、头脑风暴。
- **技能扩展** — 在工作区添加技能文件即可教会新能力。
- **多通道** — 可接 Telegram、Discord、Slack、飞书、企业微信、钉钉、邮件等。
- **团队与子智能体** — 后台子任务或多智能体协作，应对长程复杂任务。

```bash
deeptutor bot create math-tutor --persona "Socratic math teacher who uses probing questions"
deeptutor bot create writing-coach --persona "Patient, detail-oriented writing mentor"
deeptutor bot list                  # 查看所有导师实例
```

<div align="center">
采用 [Apache License 2.0](LICENSE) 许可。
</div>
