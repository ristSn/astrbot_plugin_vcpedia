# Changelog

## 1.0.0 - 2026-10-26

### Added

- 统一的 `ask_vcpedia` LLM 工具入口，支持 `auto`、`summary`、`search`、`info`、`song`、`lyrics`、`producer`、`voicebank`、`album`、`section`、`full_page` 模式。
- VCPedia 页面搜索、摘要、章节和整页正文查询。
- `VOCALOID_Songbox`、`Producer`、`人物信息`、`Album Infobox` 信息框解析。
- 歌曲 STAFF 表、殿堂曲/传说曲/神话曲题头识别。
- 专辑 `Tracklist` 曲目解析。
- 多版本歌曲 `tabs/core` 展开。
- 歌词提取，支持颜色、注音、黑幕等常见模板清理。
- 消歧义页面和候选页面提示。
- 页面 TTL 缓存与可配置的返回长度限制。
- 插件 Logo、MIT 许可证和 GitHub 发布配置。
