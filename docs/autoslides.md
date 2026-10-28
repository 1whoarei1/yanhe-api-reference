# 旧版课程索引

感谢 **[bit-admin](https://github.com/bit-admin)** 公开 **[Yanhekt-AutoSlides](https://github.com/bit-admin/Yanhekt-AutoSlides)** 的 session 索引与接口研究，使旧版课程检索和课次发现成为可能。本次独立实现 HTTP 客户端，依据其 [固定修订的 API 文档](https://github.com/bit-admin/Yanhekt-AutoSlides/blob/746cd87ccc4da59cb838adc023200531aa379a85/share/docs/api.md) 和 indexer 源码整理协议。

基础地址 `https://share.ruc.edu.kg`，公开只读元数据接口，无 Bearer。服务有校园网 / WAF 访问限制；本环境的 `/api/terms`、`/api/search?q=9397`、`/api/courses/71990/sessions` 返回 HTTP 403 HTML，故下述数据结构依据源码，例子均为合成数据。403 或验证页面是连接错误，不能解释为零课程、零课次或没有回放。

## 检索与课次

| 请求 | 约束与返回 |
| --- | --- |
| `GET /api/terms` | `terms` 为部署已索引的学期；`updatedAt` 为毫秒时间戳或 null。客户端动态读取学期。 |
| `GET /api/search?q=...&term=...` | 查询课程名、教师、课程 ID、课程链接或教务编号。课程名 / 教师必须限定一个已索引学期；课程 ID / 教务编号可以不指定。`q` 2–64 字符，至多 6 个关键词，至少一个词长不小于 2。 |
| `GET /api/courses/{id}/sessions` | `id` 是 course ID；返回 `{course, sessions: [sessionId, ...]}`，升序。未知课程 404，不代表原站没有回放。 |
| `GET /api/courses/{id}/yanhekt` | 对已收录课程读取原站精简元数据，缓存 6 小时。 |
| `GET /api/courses/{id}/yanhekt/sessions?from=0` | 每次最多 30 个课次，使用响应 `next` 继续读取；`next=null` 结束。标题、时间、教室、`recorded` 等可为 null，也可能出现单条 `error: gone/unavailable`。不返回 video ID。缓存 30 分钟，unavailable 不缓存。 |

搜索返回 `query`、`total`、`truncated`、`results`。每门课程包含 `id/name/number/term/teachers/sessionCount/match.fields`。`sessionCount` 是已索引的课次数，不是可播放回放或视频片段数。搜索最多返回 200 门，没有服务端分页；插件仅对这批结果每 40 门本地分页，另显示总匹配数。`truncated=true` 表示排序候选已限制到较新的 5,000 门，与 200 条返回上限不是同一含义。

**搜索不是 session 搜索。** 数字查询对应 course ID，session URL 会被拒绝。`course/71990` 与 `session/71990` 必须分别解析；不能用 session ID 去请求 `/api/courses/{id}/sessions`。已知 session 链接仍走 [旧版接口](legacy.md)，无需先被索引收录。

## 播放接入

Refine 0.9.7 与 Replay 0.4.2 的界面统一使用“旧版”名称。搜索用上述前两个接口；课程页合并原站课次列表与索引的 session ID，重复 session 不重复插入。只在用户选中课次后，通过 `/v1/course/session?session_id=...&with_video=true` 取得所属 course 与 `video_ids`，核对父课程，再读取 `/v1/video?id=...` 的所选片段元数据。其它片段只列出编号，不预取媒体。保留独立的 session / video 身份、切换、恢复、字幕及下载流程。

`/v1/video` 可能返回为 0 的 `course_id/session_id`，不能据此推断关联。归属以 session 元数据的父课程及 `video_ids` 为准；错误父课程、无视频或不属于该课次的 video 均停止解析。播放仍使用原有登录、短期播放凭据及签名链路。

索引仍在建设，可能缺课程、课次、学期，或保留过时条目。读取失败明确报错，已知 session 地址可以独立打开。请求索引不携带延河课堂 Bearer、Cookie 或签名媒体地址，也不把个人记录上传给索引。原旧版 XLSX 表继续停用，不随包分发。

## Release 数据与边界

[独立的 `index` 预发布](https://github.com/bit-admin/Yanhekt-AutoSlides/releases/tag/index) 提供完整数据库和客户端学期分片；它不是普通应用 release。默认客户端分片导出范围从 `2023-2024-1` 开始，不能据此声称覆盖 2020/2021 的 session。在线服务覆盖范围以 `/api/terms` 和实际返回为准。

发布资产采用加密封装，完整数据库与客户端分片使用不同密钥。当前集成使用公开在线 API，不打包这些加密快照或密钥，不要求用户解密。旧 `/v2/api/*` 已退役，返回 410。

业务错误采用 `{error, message, param?}`；包括 `term-required`、`term-not-indexed`、`query-too-short`、`bad-param`、`not-found` 等。502 / 503 表示原站读取失败或部署尚未配置，HTML 验证页也应按不可用处理。
