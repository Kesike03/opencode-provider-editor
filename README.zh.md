# OpenCode 配置编辑助手

[English](README.md) | 中文

本地运行的 Python 桌面程序，用来编辑 OpenCode `provider` 格式的中转站配置。使用 Python 标准库和 Tkinter，无第三方依赖，不启动 Web 服务。编辑与体检在本机完成；只有点击“从 URL 拉取模型列表”才会访问填写的中转站地址。

## 启动

安装 Python 3.10 或更新版本。在本目录运行：

```powershell
py app.py
```

macOS / Linux 可运行 `python3 app.py`。部分 Linux 发行版需要安装系统包 `python3-tk`。Windows 的 Python 安装程序需包含 Tcl/Tk。

## 语言

界面支持中文和英文，可在右上角随时切换，切换时会保留输入文本、当前页签、筛选条件、选中分组/模型和导出结果。默认语言按 `OPENCODE_EDITOR_LANG`、`LC_ALL` / `LC_MESSAGES` / `LANG`、系统 locale 的顺序判断，无法识别时使用中文。也可强制指定：

```powershell
$env:OPENCODE_EDITOR_LANG='en'; py app.py
```

```bash
OPENCODE_EDITOR_LANG=en python3 app.py
```

## 使用

1. 在“导入”页粘贴完整的 `opencode.json` / `opencode.jsonc` 文本，点击“识别配置”。也可先填入示例。即使原文是 `{}`，也可在编辑页创建第一个分组。
2. 在“快速编辑”页左侧选择 provider（一个 provider 对应一个中转站分组）。列表显示 ID、名称和模型数量；右侧“分组设置”显示完整 baseURL 与脱敏 key 来源。选择模型后右侧切换到“模型能力与限制”，两种详情可用页签切换。
3. 点击“+ 添加分组”选择基于原生 provider 或添加自定义 provider。自定义模式填写 ID、名称及 URL；API key 可留空，通过可增删的请求头输入认证。模型 ID 行也可增删；可点“从 URL 拉取模型列表”填充 ID，再自行筛选。分组与模型列表都有删除按钮，删除前会确认。
4. 选择分组字段，或用搜索框按模型 ID / 名称查找模型并选择右侧的能力字段。字段左侧的 `?` 悬浮显示当前语言的简介；双击字段或点击“编辑选中字段”按钮。布尔值使用勾选框；headers、interleaved、variants 支持 JSONC 输入。支持逐次撤销。
5. 查看“体检”页，核对缺失的能力元数据、格式、上下文限制和启用/禁用列表。
6. 点击“生成导出文本”，再“一键复制”，自行粘贴回配置文件。编辑后旧输出自动失效，避免复制过时内容。

字段没有声明和 `false` 是两种状态。弹窗中的“移除字段”会删除该配置项，让 OpenCode 自行决定默认值或继承行为。空字符串会作为空字符串写入，不等于移除。输入页保留最初粘贴的文本，不会随表格修改；重新导入以输入页为准。

## 支持的字段

| 层级 | 表格字段 | 配置位置 |
| --- | --- | --- |
| provider | name | `provider.<id>.name` |
| provider | baseURL、headers | `provider.<id>.options.baseURL / headers` |
| model | name、reasoning、tool_call、attachment、interleaved、variants | `provider.<id>.models.<model-id>.*` |
| model | limit.context、limit.output | `provider.<id>.models.<model-id>.limit.*` |

已有配置中的 ID 可以包含点号、斜线和中文，程序按真实键路径处理。新增 provider ID 限定为小写字母、下划线、数字及连字符；新增模型 ID 可以包含斜线，不能包含 `#`。其他配置项（npm、options、modalities、插件、权限等）保留原样。修改已有 ID 可在输入文本中完成后重新导入。

### 创建分组与拉取模型

- “基于原生 provider”填写内置 provider ID，例如 `openai`；只写所填的覆盖项，不指定 npm。已存在的 ID 无法重复添加，直接选择现有分组编辑即可。
- “添加自定义 provider”要求显示名、基础 URL，自动设置 `npm: "@ai-sdk/openai-compatible"`；对应 OpenAI 兼容接口，其他协议需在导出前手动调整适配器配置。
- 模型列表按钮请求 `GET <baseURL>/models`，携带 `Authorization: Bearer <API 密钥>`（若填了密钥）及所填请求头；同名 Authorization 请求头覆盖 Bearer。支持返回 `{"data":[{"id":"模型ID"}]}` 的接口。拉取结果去重后追加到模型 ID 行，不会移除手填内容，也不会写入能力元数据。
- 请求在后台执行，超时 12 秒，响应上限 4 MB；失败时不改动表单。URL 不接受内嵌账号、查询参数或片段；`{env:...}` 类型密钥引用不能用于实时拉取。请求会把填写的密钥/请求头发送到所填 URL，请先核对地址。
- 删除分组或模型只删除该定义，不自动修改默认模型、代理配置或其他位置的引用；可用撤销恢复。

## 思考模式与中转站权限

`reasoning: true` 是能力声明，不能让原本不支持思考的模型获得思考能力。是否返回思考内容，还取决于 SDK 适配器、请求参数、中转站分组权限及模型。

例如服务端使用 `reasoning_content` 字段时，可按实际协议填写：

```json
{
  "reasoning": true,
  "interleaved": {"field": "reasoning_content"},
  "limit": {"context": 128000, "output": 8192}
}
```

上述上限只是示例。`variants` 不提供万能预设：如 `reasoningEffort`、`thinking` 等参数取决于适配器和模型，需查对应文档。离线体检不会验证模型是否存在、实际权限或响应字段，不消耗 API 额度。

字段依据 [OpenCode 配置 schema](https://opencode.ai/config.json) 中的 `ProviderConfig` 核对。较新的 schema 还提供结构不同的 `providers` 配置，本工具会明确拒绝该格式，避免误写；本版面向用户现有的 `provider` 配置。不同 OpenCode 版本对 interleaved 字符串等形式的支持可能不同，`{"field":"reasoning_content"}` 是常用的对象写法。体检覆盖本工具编辑的字段，不是整个 OpenCode schema 的完整验证器。

## 密钥与 auth.json

- `options.apiKey` 内联密钥在概览中仅显示前 4 个字符和总长度；长度不超过 4 的短密钥完全遮盖。
- `{env:NAME}` / `{file:path}` 显示为引用，不读取或展开引用内容。
- 点击“加载 auth.json”手动选择认证文件，按 provider ID 匹配 API key；OAuth 单独标记。常见路径为 `~/.local/share/opencode/auth.json`，实际位置可能受 `XDG_DATA_HOME` 影响。
- 未加载认证文件时显示“未确认”，不会假定它一定存在。内联配置优先展示；实际运行时认证解析以 OpenCode 为准。
- 加载的认证数据只用于展示，不会并入输出。可随时清除内存中的认证数据。
- 输入和输出保留原配置中的完整密钥，headers 编辑器也会展示原值，方便修改。程序不写配置文件、不记录日志、不自动保存。新建分组的密钥会写入输出中的 `options.apiKey`，需要避免将输出分享给无关人员。

## JSONC 保留策略

解析时记录每个值的位置；编辑已有字段时只替换其值，新增字段追加到所属对象末尾，删除字段只删除对应键值和必要的逗号。未编辑区域、键顺序、注释、未知字段保持原样。没有任何编辑时导出与输入完全一致。

对象（headers、variants 等）按键递归合并修改，尽量保留内部注释。整个值类型改变、数组整体替换或字段删除时，被替换/删除值内部的注释无法保留。新增字段的局部空白可能与原排版略有不同。支持 BOM、两种注释、尾逗号、CRLF；拒绝重复键和非法 JSON 值，并报告行列位置。

## 验证

```powershell
py -m unittest discover -s tests -v
```

测试覆盖解析、注释保留、分组和模型增删、密钥脱敏、离线体检、模拟的模型列表响应，以及中英文目录键、占位符和英文错误消息。可用 `py tests/gui_smoke.py` 执行桌面交互及语言切换检查，`py tests/layout_smoke.py` 检查中英文界面在 1180×770、900×650、780×550 窗口和窄弹窗下的控件可见性（都需要图形桌面）。测试中的网络请求均使用模拟响应，不访问真实中转站。

## 许可证

本项目基于 [GNU Affero General Public License v3.0](LICENSE)（AGPL-3.0）开源。
