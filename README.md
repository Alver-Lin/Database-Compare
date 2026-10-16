# 数据库对比工具（database-comparison）

跨库表结构与数据内容对比工具。支持源库 / 目标库异构连接，通过可视化向导完成库表选择、字段映射与行级内容比对，并生成可下载的 PDF 报告。

## 功能概览

- **任务管理**：创建、编辑、复制、删除对比任务；历史数据源可一键回填
- **四步向导**
  1. 选择源库 / 目标库（及 Schema）
  2. 对比数据表（表名、数量、表级关联）
  3. 对比表结构（字段连线映射）
  4. 对比字段内容（精确 / 模糊匹配）
- **高级匹配**
  - 多源字段聚合（`+` 拼接）到同一目标列
  - 值别名映射（如 `3` ↔ `PUBLISHED`）
  - 按字符位提取后比对
  - 源表 Join、搜索筛选条件
  - 模糊内容对比（忽略 JSON 数组 / 逗号分隔等格式差异）
- **报告**：在线查看对比结果，支持下载 PDF
- **本地持久化**：任务与连接配置保存在 `backend/data/app.db`

## 支持的数据源

| 类型 | 说明 |
|------|------|
| MySQL / MariaDB | 原生协议 |
| PostgreSQL | 原生协议 |
| SQLite | 本地文件路径 |
| Oracle | `oracledb` 驱动 |
| OceanBase | MySQL / Oracle 租户（含 JDBC） |
| 达梦 (DM) | JDBC |

> 达梦、OceanBase（部分场景）依赖本机 Java 与 `backend/drivers` 下的 JDBC 驱动。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3、Vite、Ant Design Vue、Vue Router、Axios |
| 后端 | FastAPI、Uvicorn、SQLAlchemy、Pydantic |
| 任务库 | SQLite（`backend/data/app.db`） |
| 报告 | ReportLab（PDF） |

## 目录结构

```
database_comparison/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # 应用入口
│   │   ├── connectors.py    # 各数据库连接与取数
│   │   ├── routers/         # tasks / compare API
│   │   └── ...
│   ├── drivers/             # JDBC Bridge 与驱动（jar/class）
│   ├── requirements.txt
│   └── data/                # 运行时生成，勿提交敏感数据
├── frontend/                # Vue 前端
│   ├── src/
│   └── package.json
├── start-backend.bat        # Windows 启动后端
├── start-frontend.bat       # Windows 启动前端
├── pack.ps1                 # 打便携发布包
└── README.md
```

## 环境要求

- **Python** 3.10+（推荐 3.12）
- **Node.js** 18+（前端开发 / 构建）
- **Java 17+**（使用达梦或 OceanBase JDBC 时需要；`JAVA_HOME` 或 `PATH` 中可找到 `java`）
- Windows / Linux / macOS 均可开发；仓库内自带 `.bat` / `pack.ps1` 面向 Windows

## 快速开始（开发）

### 1. 克隆仓库

```bash
git clone <你的 GitLab 仓库地址>
cd database_comparison
```

### 2. 后端

```bash
# 建议使用虚拟环境
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
# source .venv/bin/activate

pip install -r backend/requirements.txt

cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

或在 Windows 上直接双击 / 运行 `start-backend.bat`。

- API 文档：<http://127.0.0.1:8001/docs>
- 健康检查：`GET /api/health`

### 3. 前端

另开终端：

```bash
cd frontend
npm install
npm run dev
```

或运行 `start-frontend.bat`。

- 开发地址：<http://127.0.0.1:5174/>
- `/api` 已代理到 `http://127.0.0.1:8001`

浏览器打开前端地址即可使用。

## 使用流程

1. 在「数据对比任务」页创建任务，分别配置并测试 **源库**、**目标库** 连接  
2. 进入向导：选择库表 → 表关联 → 字段连线 → 字段内容对比  
3. 按需开启模糊对比、值别名、提取规则或筛选条件  
4. 完成后查看报告，可下载 PDF；任务进度会保存在本地数据库  

## 便携发布包（可选）

在 Windows 上执行：

```powershell
.\pack.ps1
```

脚本会：

1. 构建前端到 `web/`
2. 打包内嵌 Python runtime、JRE 与后端代码
3. 输出到 `release/数据库对比工具/`，并在桌面生成 zip

对方机器解压后双击 `启动.bat`，访问 <http://127.0.0.1:8765/> 即可，无需单独安装 Node / 项目虚拟环境。

局域网访问时，将 `127.0.0.1` 换成主机 IP，端口 `8765`。

## 主要 API

| 前缀 | 说明 |
|------|------|
| `/api/health` | 健康检查 |
| `/api/tasks` | 任务 CRUD、连接测试、数据源历史、PDF 下载 |
| `/api/compare` | 库表列举、字段映射、行匹配、未匹配行查询等 |

完整接口见运行中的 Swagger：`/docs`。

## 配置与数据安全

- 任务与连接信息（含密码）保存在 **`backend/data/app.db`**
- 该目录已在 `.gitignore` 中忽略；**请勿将 `app.db` 提交到 GitLab 或发给无关人员**
- 对外展示任务配置时，接口会将密码脱敏为 `******`

## 常见问题

**达梦 / OceanBase 连接失败**  
确认已安装 JRE/JDK，且 `backend/drivers` 中具备对应 JDBC 驱动与 Bridge 编译产物（`.jar` / `.class`）。

**OceanBase Oracle 租户**  
在「默认数据库」栏填写服务名 / 租户名；租户模式可选「自动识别 / MySQL / Oracle」。

**前端调不通后端**  
确认后端在 `8001` 端口运行，且前端通过 Vite 代理访问 `/api`（不要把前端请求直接打到错误端口）。

**对比结果异常为空**  
检查字段是否已连线、是否勾选了对比字段，以及搜索/筛选条件是否过严。

## 许可证

内部项目，按团队 / 组织约定使用与分发。
