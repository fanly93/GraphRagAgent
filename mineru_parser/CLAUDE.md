# MinerU Parser — Claude Code 工作指南

## 虚拟环境（强制要求）

**在此目录下执行任何 Python 命令之前，必须先激活虚拟环境。**

```bash
# 激活虚拟环境
source .venv/bin/activate

# 验证已激活（应显示 .venv 路径）
which python   # → .../mineru_parser/.venv/bin/python
```

### 虚拟环境信息

| 项目 | 值 |
|---|---|
| 路径 | `mineru_parser/.venv/` |
| Python 版本 | 3.13.12 |
| 解释器 | `.venv/bin/python` |
| 激活脚本 | `.venv/bin/activate` |

### 执行规则

- **禁止** 使用系统 `python3` 或 `python` 直接执行本目录下的脚本
- **必须** 使用 `.venv/bin/python` 或先 `source .venv/bin/activate` 后再执行
- **安装依赖** 必须使用 `.venv/bin/pip install`，不得污染系统环境
- 如果虚拟环境不存在，先执行初始化（见下方）

### 虚拟环境不存在时的初始化

```bash
cd /Users/tanglin/VibeCoding/GraphRagAgent/mineru_parser
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 启动 MinerU 解析服务

### 标准启动流程

```bash
# 1. 进入模块目录
cd /Users/tanglin/VibeCoding/GraphRagAgent/mineru_parser

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 将待解析文件放入 input/ 目录，然后运行
python run_parser.py

# 解析完成后，结果保存在 output/{文件名}/ 目录下
```

### 常用命令

```bash
# 预览文件路由（不实际调用 API）
python run_parser.py --dry-run

# 解析 + 输出规范验证
python run_parser.py --verify

# 解析指定文件
python run_parser.py input/document.pdf input/data.xlsx
```

---

## 目录结构

```
mineru_parser/
├── .venv/              # 虚拟环境（不提交到 git）
├── input/              # 待解析文件放这里
├── output/             # 解析结果输出到这里
├── .env                # API Token 配置（不提交到 git）
├── run_parser.py       # 主入口脚本
├── config.py           # 环境配置加载
├── client.py           # MinerU API 客户端
├── pipeline.py         # Pipeline 编排逻辑
├── models.py           # 数据模型
└── requirements.txt    # 依赖列表
```

---

## 环境配置

`.env` 文件必须包含：

```
MINERU_API_TOKEN=eyJ...   # 从 https://mineru.net/apiManage/openToken 获取
```

Token 缺失时精准解析 API 会返回 A0202 / A0211 错误。

---

## 依赖管理

```bash
# 查看当前安装的包
.venv/bin/pip list

# 新增依赖后更新 requirements.txt
.venv/bin/pip freeze > requirements.txt

# 从 requirements.txt 重新安装
.venv/bin/pip install -r requirements.txt
```

---

## 注意事项

- `input/` 和 `output/` 目录内容不提交 git（已在 .gitignore 中）
- `.env` 文件包含 API Token，不提交 git
- Excel 文件使用 Agent 轻量 API，**仅输出 `full.md`**，无 content_list.json
- 图片文件（.png/.jpg 等）自动开启 OCR（`is_ocr: true`）
