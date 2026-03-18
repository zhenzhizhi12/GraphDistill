# GraphDistill 项目结构说明

> 更新时间：2026年3月18日

## 📁 目录树

```
GraphDistill/
├── core/                              # 核心模块包（相对导入）
│   ├── __init__.py
│   ├── graph_builder.py              # 图构建与管理
│   ├── search_engine.py              # 搜索引擎
│   ├── cjd_parser.py                 # Cangjie AST解析（三轨道轨道2）
│   ├── extractor.py                  # 信息提取与LLM蒸馏（三轨道轨道3）
│   ├── index_parser.py               # 索引/概览解析（三轨道轨道1）
│   ├── pydantic_schema.py            # 数据模型定义
│   └── entity_id_normalizer.py       # 实体标准化
│
├── data/                              # 知识图谱数据文件
│   ├── test_core_extraction_unified_std_api.json      # 基础图数据
│   └── test_graph_with_vectors.json                   # 向量索引图数据
│
├── tests/                             # 测试与评估脚本
│   ├── test_core_extraction.py                # 三轨道测试
│   ├── test_search_report.py                  # 搜索引擎评测
│   ├── compare_old_search_report.py           # 旧方案对比（已完成）
│   ├── TEST_REPORT.md                         # 测试报告
│   └── OLD_SEARCH_COMPARE_REPORT.md           # 对比报告
│
├── services/                          # 外部服务支持
│   └── scripts/
│       ├── cjd_ast_service.py                 # 🔑 WSL AST微服务（建图时需要）
│       ├── test_three_tracks.py               # 三轨道低成本测试
│       ├── test_cjd_parser.py                 # AST解析测试
│       ├── debug_cjd_ast.py                   # AST调试工具
│       └── install_cangjie_treesitter_python_binding.cmd
│
├── temp_repos/                        # 🔑 本地文档库（search_engine回退依赖）
│   ├── Cangjie_Guide/
│   ├── Cangjie_StdLib/
│   ├── Cangjie_StdX/
│   ├── Cangjie_Tools/
│   ├── CangjieTreeSitter/
│   ├── HarmonyOS_Cangjie/
│   └── interface_sdk_cangjie/
│
├── main.py                            # 主建图流程入口
├── query.py                           # 查询接口（便捷API）
├── serve.py                           # 可视化服务器
├── build_vector_index.py              # FAISS向量索引构建工具
├── visualizer.html                    # 前端可视化页面
│
├── requirements.txt                   # Python依赖列表
├── SETUP_GUIDE.md                     # 项目设置指南
├── PROJECT_STRUCTURE.md               # 本文件
│
├── .venv_cjd/                         # Python虚拟环境
├── .git/                              # Git版本控制
├── .vscode/                           # VSCode配置
├── .idea/                             # IDE配置
├── .gitignore                         # Git忽略规则
│
└── __pycache__/                       # Python缓存（自动生成，可删除）
```

## 📦 核心功能说明

### 一、三轨道知识图谱提取流程

**入口：`main.py` → `distill_docs()`**

| 轨道 | 文件类型 | 处理方式 | 核心模块 |
|-----|---------|--------|---------|
| **轨道1** | `.md`（index/overview） | 目录页解析 | `core.index_parser` |
| **轨道2** | `.cj` / `.cj.d` | AST解析（本地/微服务/兜底） | `core.cjd_parser` |
| **轨道3** | `.md`（其他） | LLM蒸馏提取 | `core.extractor` |

### 二、搜索引擎回退机制

**入口：`query.py` → `ask()` / `core.search_engine.SearchEngine`**

**回退链：**
```
图上下文 → DOCUMENTED_AT关系 → temp_repos本地文档 → 加载补充内容 → LLM重试
```

**关键依赖：**
- ✅ `temp_repos/` 必须保留（存储本地文档副本）
- ✅ `search_engine.py` 的 `_resolve_doc_paths()` 通过 `sources` 推断路径
- ✅ `_load_supplementary_content()` 加载文档原文进行LLM增强

### 三、AST微服务（Windows→WSL）

**启动命令：**
```bash
# WSL终端中执行
cd /mnt/c/Users/zqw/Desktop/GraphDistill
source .venv_cjd/bin/activate
python services/scripts/cjd_ast_service.py --host 0.0.0.0 --port 8001
```

**使用流程：**
1. Windows下 `core.cjd_parser.parse_cjd_ast()` 调用
2. 尝试本地 Tree-sitter（若cangjie_lang非空）
3. 回退到远程 HTTP 调用 WSL 微服务（http://127.0.0.1:8001/parse_cjd）
4. 最后兜底正则表达式解析

---

## 🔧 导入路径约定

### 根目录脚本
```python
from core.graph_builder import GraphBuilder
from core.search_engine import SearchEngine
from core.cjd_parser import parse_cjd_ast
```

### tests/ 子目录脚本
```python
# 在文件开头添加
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.graph_builder import GraphBuilder
from core.search_engine import SearchEngine
```

### services/scripts/ 脚本
```python
import sys
from pathlib import Path
_ROOT = Path(__file__).resolve().parents[2]  # 上溯两层到项目根
sys.path.insert(0, str(_ROOT))

from core.cjd_parser import parse_cjd_ast
```

### core/ 内部模块
```python
# core/ 中的模块使用相对导入
from .graph_builder import GraphBuilder
from .pydantic_schema import DocumentGraph
from .entity_id_normalizer import normalize_entity_id
```

---

## 📝 常见操作

### 1. 启动完整建图
```bash
python main.py --model Pro/zai-org/GLM-4.7
```

### 2. 启动查询接口
```bash
python query.py
```

### 3. 构建向量索引
```bash
python build_vector_index.py \
  --input data/test_core_extraction_unified_std_api.json \
  --output data/test_graph_with_vectors.json
```

### 4. 运行搜索评测
```bash
python tests/test_search_report.py
```

### 5. 启动可视化服务
```bash
python serve.py
```
然后访问 http://localhost:8000/visualizer.html

---

## ⚠️ 重要说明

### 必须保留的文件/目录
- ✅ `temp_repos/` - search_engine 文档回退依赖
- ✅ `services/scripts/cjd_ast_service.py` - 建图时的 AST 微服务
- ✅ `.venv_cjd/` - Python 虚拟环境
- ✅ `data/` - 知识图谱数据

### 已删除的文件
- ❌ `old-search-l1/` - 旧搜索方案（对比已完成）
- ❌ `scripts/` - 脚本已移至 `services/scripts/`
- ❌ `scripts.zip` - 旧版本归档
- ❌ `log.txt`, `test_run.log` 等日志文件

### 测试脚本用途
| 脚本 | 用途 | 运行命令 |
|-----|-----|---------|
| `test_core_extraction.py` | 验证三轨道提取 | `python tests/test_core_extraction.py` |
| `test_search_report.py` | 评测搜索质量 | `python tests/test_search_report.py` |
| `compare_old_search_report.py` | 对比新旧方案（已完成） | ⚠️ 需要 old-search-l1（已删除） |

---

## 🚀 下一步

1. **验证导入无误**：`python -c "from core.graph_builder import GraphBuilder; print('✓')"`
2. **运行建图流程**：`python main.py --limit-per-source 5`
3. **启动查询接口**：`python query.py`
4. **查看可视化**：`python serve.py`

