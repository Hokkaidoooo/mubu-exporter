# Mubu Exporter

把幕布大纲整理为可迁移的 Markdown：保留文件夹、富文本、任务状态、表格、公式和文档间引用，支持将图片下载到本地。

Python 3.10+ · Windows / Linux · MIT

## 先看示例

无需账号、令牌或网络即可转换仓库内手写的合成示例：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
mubu-export inspect --cache examples/cache
mubu-export export --cache examples/cache --out exports/demo --images skip
```

Linux/macOS 激活环境使用 `source .venv/bin/activate`。打开 `exports/demo/index.md` 查看导出目录。输出目录必须是新目录；再次运行时换一个目录名。

示例输入在 [examples/cache](examples/cache)，[导出预览](examples/preview/index.md) 展示实际转换结果。它们仅含虚构内容。

## 能保留什么

| 内容 | Markdown 表达 |
| --- | --- |
| 文件夹与同名文档 | 按 ID 分配稳定、唯一的路径，规避 Windows 保留名和大小写冲突 |
| 大纲 | 自适应章节标题，或完整嵌套列表 |
| 粗体、斜体、删除线、行内代码 | 对应 Markdown 标记；代码保留反引号与空格 |
| 高亮、挖空 | `==高亮==`、`{{挖空}}`，显示效果取决于阅读器 |
| 下划线、颜色 | 少量 HTML；可用 `--no-color` 移除颜色 |
| 公式 | `$LaTeX$`，需要阅读器支持数学公式 |
| 任务与备注 | `- [ ]` / `- [x]`、块引用 |
| 普通表格 | GFM 表格，保留单元格中的转义文字与换行 |
| 文档引用 | 已导出文档使用相对链接与节点锚点；外部文档保留幕布链接 |
| 图片 | 保留远程地址、下载本地、或明确跳过 |

合并单元格、嵌套表格和已知不完整数据会显式报错，避免生成看似成功却丢内容的文件。大纲布局不会复刻幕布的交互界面。

## 备份自己的幕布

`fetch` 使用幕布网页端接口；这是非官方工具，接口可能变化。只用于你有权限访问的内容。

1. 在浏览器登录幕布，打开开发者工具的 Network 面板。
2. 选取发往 `api2.mubu.com` 的文档请求，找到请求头 `Jwt-Token`。
3. 运行隐藏输入命令并粘贴该值。令牌只在本次进程内使用，不会保存到文件。

```powershell
mubu-export fetch --cache cache/backup-001 --prompt-token
mubu-export inspect --cache cache/backup-001
mubu-export export --cache cache/backup-001 --out exports/backup-001 --images local
```

如接口需要 `data-unique-id`，可通过环境变量 `MUBU_UNIQUE_ID` 提供。自动化可从环境变量 `MUBU_TOKEN` 读取令牌；不要把令牌写进脚本、命令参数、截图或 Git。

备份会分页读取文档、合并每日笔记，再重新抓取所有文档。不会仅凭旧文件存在就跳过更新。每日笔记接口失败时备份失败；确实无需每日笔记可明确加 `--no-daily`。

下载与导出在同盘临时目录完成，全部通过后才将新目录交付。已有目录不会被覆盖。转换只读取 `tree.json` 中列出的文档，旧缓存中多余的文件不会重新混入导出。

## 常用选项

```powershell
# 只处理本地缓存，完全不请求网络
mubu-export export --cache cache/backup-001 --out exports/text --images skip --no-color

# 使用完整嵌套列表
mubu-export export --cache cache/backup-001 --out exports/bullets --style bullets

# 明确在 front matter 加入源文档 ID 与幕布链接
mubu-export export --cache cache/backup-001 --out exports/with-source --source-metadata
```

默认导出摘要只显示数量，不打印账号、文档名或文档 ID。源文档 ID 和 URL 默认不进入 front matter；正文、文件名、节点锚点、原有链接和图片仍可能包含你自己的内容。导出结果属于私人数据，不应直接提交到公共仓库。

图片请求不会携带幕布令牌，默认只下载 HTTPS 公网地址，拒绝重定向、私网地址、非图片响应、空响应和超过 32 MiB 的文件。来自可信本地网络的图片，可明确加 `--allow-private-images`。图片 URL 仍可能属于外部站点，下载会访问相应服务器。

链接协议和颜色值默认校验；遇到危险内容会失败。`--trusted-input` 可为可信输入放开这两项限制，不建议用于未知来源的缓存。`--no-color` 可以绕过颜色渲染，保留正文。

## 本地缓存契约

```text
cache/backup-001/
  tree.json          # folders 和 documents 列表，文档 ID 为主键
  docs/<id>.json     # {"meta": {...}, "data": {"definition": ..., "directory": [...]}}
  manifest.json      # 新备份的 schema 版本与文档数量
```

`definition` 支持 JSON 对象或 JSON 字符串，必须明确包含 `nodes` 列表；合法空笔记使用 `{"nodes": []}`。ID 只允许字母、数字、下划线与连字符。最多支持 64 层节点和 32 层目录。支持已有相同契约的缓存，不需要将私人缓存放入源码仓库。

导出包含 `index.md`、每篇笔记和 `manifest.json`。清单记录文档数量、图片模式、实际文件路径与 SHA-256，方便核对和迁移。

## 开发与验证

```powershell
python -m pip install ".[dev]"
python -m pytest
python -m ruff check .
python -m build
```

测试只使用合成数据，并包含本机 HTTP 服务的真实请求验证，不需要幕布账号。CI 在 Windows / Linux、Python 3.10 / 3.12 上执行测试、lint、构建和安装后的示例转换。在线幕布接口未纳入公共 CI，接口兼容性不能由离线测试保证。

## 隐私与限制

仓库不包含登录数据、账号信息、真实笔记、私人诊断记录或个人截图。示例和测试均为手写合成内容。请保留令牌与备份的访问权限，并参考 [隐私说明](PRIVACY.md)。

本工具不提供官方接口稳定性承诺，不绕过权限，也不会将笔记发送给 AI 或分析服务。Markdown 阅读器对公式、高亮、挖空和 HTML 的支持程度不同。附件文件、嵌入网页等未列入支持表的对象不保证转换；发布重要资料前应将导出与源内容核对。
