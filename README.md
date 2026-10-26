<p align="center">
  <img src="logo.png" width="144" alt="VCPedia 查询插件 Logo">
</p>

<h1 align="center">VCPedia 查询插件</h1>

<p align="center">
  给 AstrBot LLM 使用的 VCPedia 虚拟歌手百科查询插件
</p>

<p align="center">
  <a href="https://github.com/ristSn/astrbot_plugin_vcpedia">GitHub</a> ·
  <a href="https://vcpedia.cn/">VCPedia</a> ·
  <a href="https://cloud.astrbot.app/publish">AstrBot 插件发布页</a>
</p>

---

这是一个参考 `astrbot_plugin_minecraft_wiki` 架构编写的 [AstrBot](https://astrbot.app/) 插件，用统一工具入口让 LLM 查询 [VCPedia](https://vcpedia.cn/) 的页面、歌曲、P主、声库、专辑与歌词。

VCPedia 是中文虚拟歌手领域的大型百科，收录 VOCALOID、Synthesizer V、ACE Studio、X Studio 等声库角色，以及中文原创曲、P主、专辑、演唱会等条目。本插件把这些内容整理成 LLM 易用的结构化工具。

## 功能概览

- 统一工具入口：`ask_vcpedia`
- 页面搜索、摘要、章节、整页正文
- 结构化信息框解析：
  - 歌曲：演唱、UP主、投稿时间、播放量、B站/网易云/YouTube 链接
  - P主：艺名、生日、出身、活跃年份、歌曲风格、社交链接
  - 虚拟歌手：本名、别名、声源、身高、生日、所属团体
  - 专辑：出品、发行日期、专辑类型、收录曲目
- 歌曲 STAFF 表解析（作词、作曲、编曲、调教、曲绘、PV 等）
- 歌词提取（保留换行，清理颜色/注音/黑幕等模板）
- 成就识别（殿堂曲、传说曲、神话曲等题头）
- 多版本歌曲支持（如 `tabs/core` 中的原版与重制版）
- 专辑 `Tracklist` 曲目解析
- 消歧义页面与候选页面提示
- 页面缓存，减少重复请求

## 安装

### 从 AstrBot 插件市场安装

插件上架后，在 AstrBot WebUI 的插件市场中搜索「VCPedia 查询」并安装。

### 从 GitHub 安装

在 AstrBot WebUI 的插件管理中使用「从仓库安装」，填写：

```text
https://github.com/ristSn/astrbot_plugin_vcpedia
```

也可以手动克隆到 AstrBot 的插件目录：

```bash
cd AstrBot-Data/instances/<实例ID>/core/data/plugins
git clone https://github.com/ristSn/astrbot_plugin_vcpedia.git
```

安装依赖：

```bash
pip install -r astrbot_plugin_vcpedia/requirements.txt
```

然后在 AstrBot WebUI 的插件管理中重载插件，或重启 AstrBot。

## 推荐调用方式

LLM 默认只需要调用 `ask_vcpedia`：

```text
查一下权御天下的歌词
ilem 的生日和代表作
洛天依是谁
殿堂III 收录了哪些歌
海市蜃楼 初音未来 这首歌的播放量
```

## mode 说明

| mode | 用途 |
| --- | --- |
| `auto` | 根据问题自动判断意图（默认） |
| `summary` | 页面摘要 |
| `search` | 只返回搜索候选，适合先确认页面名 |
| `info` | 通用页面信息（信息框 + 摘要 + 章节） |
| `song` | 歌曲信息（信息框、STAFF、成就、歌词节选） |
| `lyrics` | 完整歌词 |
| `producer` | P主/创作者信息 |
| `voicebank` | 虚拟歌手/声库信息 |
| `album` | 专辑信息与收录曲目 |
| `section` | 指定章节，配合 `section` 参数 |
| `full_page` | 整页正文，适合让模型深度阅读 |

`question` 支持显式标题前缀：

```text
title:海市蜃楼(初音未来)
页面:权御天下
```

## 其他工具

除了统一入口，插件还注册了这些细分工具，便于模型在明确场景下直接调用：

- `search_vcpedia_page`
- `get_vcpedia_summary`
- `get_vcpedia_page_info`
- `get_vcpedia_song_info`
- `get_vcpedia_lyrics`
- `get_vcpedia_section`

## 返回结构

统一入口返回 JSON 字符串：

```json
{
  "intent": "song",
  "tool_used": "get_song_info",
  "result": {
    "title": "海市蜃楼(初音未来)",
    "type": "song",
    "url": "https://vcpedia.cn/海市蜃楼(初音未来)",
    "fields": {
      "演唱": "初音未来",
      "歌曲名称": "海市蜃楼",
      "UP主": "纯白",
      "bb_id": "av16809354",
      "投稿时间": "2017年12月1日"
    },
    "staff": [
      { "role": "作编曲/混音", "name": "纯白" },
      { "role": "作词", "name": "雨狸" }
    ],
    "achievements": ["VOCALOID中文神话曲"]
  }
}
```

常见错误：

- `error: page not found`：没有找到页面，可换关键词或先用 `search`
- `error: lyrics not found`：页面没有歌词章节
- `error: section not found`：章节名不匹配，返回值里会附 `available_sections`
- `error: request failed` / `timeout`：网络或 VCPedia 服务异常

## 配置项

| 配置 | 说明 | 默认值 |
| --- | --- | --- |
| `base_url` | VCPedia API 地址 | `https://vcpedia.cn/api.php` |
| `timeout_seconds` | 请求超时 | `12` |
| `cache_ttl_seconds` | 页面缓存秒数 | `86400` |
| `max_return_chars` | 常规返回上限 | `3800` |
| `max_full_page_chars` | 整页返回上限 | `16000` |
| `max_lyrics_chars` | 歌词返回上限 | `6000` |
| `default_search_limit` | 搜索候选数 | `5` |
| `user_agent` | 请求 UA | `astrbot-plugin-vcpedia/1.0` |

## 实现说明

- 只使用 MediaWiki Action API，不抓取 HTML 页面。
- 页面正文通过 `action=query&prop=revisions` 获取原始 wikitext，再在本地做模板展开与清洗。
- 歌曲页的 `VOCALOID_Songbox`、P主页的 `Producer`、声库页的 `人物信息`、专辑页的 `Album Infobox` 会被解析为字段。
- `tabs/core` 包裹的多版本内容会展开后统一渲染。
- 对常见模板（`color`、`ruby`、`黑幕`、`Cquote`、`Age`、`Astrology` 等）做了语义化处理。
- 页面按标题缓存，默认 24 小时。

## 已知限制

- VCPedia 模板生态非常复杂，极少数页面可能仍有模板残片或丢失由 Lua 模块动态生成的内容。
- `full_page` 超长页面会按 `max_full_page_chars` 截断，并返回 `is_truncated`。
- 同名歌曲可能对应多个页面（如 `海市蜃楼(初音未来)` 与 `海市蜃楼(Dimist)`），结果会通过 `candidates` 提示候选。
- 歌词版权归原作者所有；插件只用于查询与介绍，回答时建议只引用与问题相关的短句，并附上 VCPedia 页面链接。

## 发布到 AstrBot 插件市场

1. 修改 `metadata.yaml` 中的 `version`（遵循语义化版本）。
2. 提交并推送到 GitHub 仓库。
3. 打开 [AstrBot 插件发布页](https://cloud.astrbot.app/publish)，登录 AstrBot Cloud。
4. 填写仓库地址 `https://github.com/ristSn/astrbot_plugin_vcpedia`，提交审核。
5. 审核通过后，用户即可在插件市场搜索并安装。

> 插件市场要求仓库根目录包含 `metadata.yaml`，压缩包不超过 16MB。本仓库只包含插件运行所需文件，不包含 `.git`、`__pycache__` 等开发产物。

## 许可证

本项目使用 [MIT License](LICENSE)。

## 数据来源

- VCPedia：<https://vcpedia.cn/>
- API：<https://vcpedia.cn/api.php>

本插件与 VCPedia 官方无隶属关系，仅调用其公开 MediaWiki API。
