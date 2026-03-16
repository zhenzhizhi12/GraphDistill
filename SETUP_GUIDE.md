# GraphDistill 完整操作指南

## 📋 前置准备

### 1. 环境变量设置（Windows PowerShell）

设置 SiliconFlow API Key（用于轨道3的LLM调用）：

```powershell
# 临时设置（当前会话有效）
$env:SILICONFLOW_API_KEY = "你的API密钥"

# 或永久设置（需要管理员权限）
[System.Environment]::SetEnvironmentVariable('SILICONFLOW_API_KEY', '你的API密钥', 'User')
```

验证设置：
```powershell
echo $env:SILICONFLOW_API_KEY
```

---

## 🚀 完整操作流程

### 步骤 1：启动 WSL AST 微服务（轨道2专用）

**在 WSL 终端中执行：**

```bash
# 1. 进入项目目录
cd /mnt/c/Users/zqw/Desktop/GraphDistill

# 2. 激活虚拟环境（如果还没激活）
source .venv_cjd/bin/activate

# 3. 确保依赖已安装（如果还没安装）
pip install pydantic

# 4. 启动 AST 微服务
python scripts/cjd_ast_service.py --host 0.0.0.0 --port 8001
```

**预期输出：**
```
2026-03-13 09:10:55,271 [INFO] cjd_ast_service - Cangjie Tree-sitter language initialized successfully.
2026-03-13 09:10:55,274 [INFO] cjd_ast_service - CJD AST service listening on 0.0.0.0:8001
```

**保持这个终端窗口打开！** 微服务需要一直运行。

---

### 步骤 2：配置图谱输出路径（可选）

**在 `main.py` 中修改：**

```python
# 第 63 行
GRAPH_JSON_PATH = Path("test_graph.json")  # 从0开始建图
# 或
GRAPH_JSON_PATH = Path("graph.json")  # 使用默认路径
```

**说明：**
- 如果文件不存在，会自动创建新的图谱
- 如果文件存在，会加载已有图谱并增量合并

---

### 步骤 3：运行主流水线（Windows PowerShell）

**在 Windows PowerShell 中执行：**

```powershell
# 进入项目目录
cd C:\Users\zqw\Desktop\GraphDistill

# 设置 API Key（如果还没设置）
$env:SILICONFLOW_API_KEY = "你的API密钥"

# 调试模式运行（每个数据源只处理前5个文件）
python main.py --debug 0

# 或全量运行
python main.py --debug 1
```

**预期输出：**
```
[INFO] Debug 模式开启：每个数据源仅处理前 5 个文档。
[INFO] Preset xxx: found N source files (.md/.cj/.cj.d) (limit_per_source=5)
[INFO] Distilling file: ...
[INFO] Track counts: track1(index/overview)= X, track2(.cj/.cj.d)= Y, track3(other .md)= Z
[INFO] Graph stats: ...
```

---

## 🧪 低成本测试方案（推荐先跑这个）

如果不想调用 LLM API，可以使用测试脚本：

```powershell
# Windows PowerShell
cd C:\Users\zqw\Desktop\GraphDistill
python scripts/test_three_tracks.py --skip-llm
```

**这个脚本会：**
- ✅ 只处理少量预设文件（2个 overview + 2个 .cj.d）
- ✅ 跳过轨道3（LLM调用），零成本
- ✅ 输出详细的轨道统计和样本实体/关系
- ✅ 保存结果到 `test_three_tracks_output.json`

---

## 📊 三轨道说明

### 轨道 1：目录/索引页解析（正则提取）
- **输入**：文件名包含 `overview` 或 `index` 的 `.md` 文件
- **输出**：`Concept` 实体、`File` 实体、`DOCUMENTED_AT` 关系
- **成本**：免费（本地正则解析）

### 轨道 2：Cangjie 声明文件解析（AST提取）
- **输入**：`.cj.d` 或 `.cj` 文件
- **输出**：`Class`、`Interface`、`Function` 实体，`INHERITS`、`IMPLEMENTS`、`RETURNS`、`ACCEPTS_PARAM` 关系
- **成本**：免费（优先调用 WSL AST 服务，失败则降级到本地启发式解析）

### 轨道 3：普通 Markdown 文档（LLM蒸馏）
- **输入**：其他 `.md` 文件
- **输出**：LLM 提取的实体和关系
- **成本**：需要有效的 `SILICONFLOW_API_KEY`

---

## 🔍 验证图谱结果

运行完成后，检查生成的 JSON 文件：

```powershell
# 查看图谱统计
python -c "from graph_builder import GraphBuilder; from pathlib import Path; b = GraphBuilder.load_json('test_graph.json'); print(b.stats_report())"
```

或使用搜索接口：

```powershell
python search_main.py
```

---

## ⚠️ 常见问题

### 1. WSL 微服务启动失败

**问题**：`ModuleNotFoundError: No module named 'pydantic'`

**解决**：
```bash
# 在 WSL 中
source .venv_cjd/bin/activate
pip install pydantic
```

### 2. API Key 无效（401错误）

**问题**：`openai.AuthenticationError: Error code: 401 - Invalid token`

**解决**：
- 检查 API Key 是否正确设置：`echo $env:SILICONFLOW_API_KEY`
- 使用 `--skip-llm` 跳过轨道3，只测试轨道1和轨道2

### 3. 图谱文件已存在，想重新开始

**解决**：
- 删除现有的 JSON 文件：`del test_graph.json`
- 或修改 `GRAPH_JSON_PATH` 指向新文件

---

## 📝 文件说明

- `main.py`：主流水线入口
- `scripts/cjd_ast_service.py`：WSL AST 微服务（轨道2）
- `scripts/test_three_tracks.py`：三轨道集成测试脚本
- `index_parser.py`：轨道1实现（目录解析）
- `cjd_parser.py`：轨道2实现（AST解析）
- `extractor.py`：轨道3实现（LLM蒸馏）
- `entity_id_normalizer.py`：统一的 entity_id 归一化
- `graph_builder.py`：图谱构建和合并逻辑
- `search_engine.py`：向量+图谱双模式查询

---

## 🎯 快速开始（最小化测试）

```powershell
# 1. Windows PowerShell：设置 API Key（可选）
$env:SILICONFLOW_API_KEY = "你的API密钥"

# 2. WSL：启动 AST 服务（后台运行）
wsl bash -c "cd /mnt/c/Users/zqw/Desktop/GraphDistill && source .venv_cjd/bin/activate && python scripts/cjd_ast_service.py --host 0.0.0.0 --port 8001" &

# 3. Windows PowerShell：运行测试脚本（跳过LLM）
python scripts/test_three_tracks.py --skip-llm
```
