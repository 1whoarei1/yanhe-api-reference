# 发布目录与导入

两款扩展的正式 Release 均提供两份明文 JSON，可分别导入。目录数据不提交源码仓库，不含媒体和个人学习状态。旧版 XLSX 表已停用，不随包分发。

## 新版课程目录

`schema: 1`，`courses[]` 为 `platform: modern` 的课程；字段包括 `id/title/teacher/term/college/code`，可带 tenant，默认 21。课程 ID 与 tenant 一起标识新版课程。快照包含 27,369 门课程。

## 自建旧版课次目录

`format: yanhekt-session-index/v1`，`source.kind: self-collected`，`generatedAt` 与 `partial` 标明时间和是否仍采集中。`courses[]` 含 `id/name/number/term/teachers/sessions`：id 为旧站 course ID，term 可为空，sessions 为该课程明确拥有的 session ID 数组。

本次为 14,435 门课程、132,050 个 session，生成于 2026-10-28T10:10:33Z，仍为部分索引。每门课程的 session 无需连续；同一个 session 不能归属两个 course。不能按编号区间推测归属，不能将 course、session 或 video 的相同数字看作同一对象。

## 客户端导入

- Refine：设置 → 导入课程表，依次选择两个文件。
- Replay：全校课程 → 导入目录，依次选择两个文件；新版可切换在线查询。

先验证整份文件再写入，原始字段仅保留公开目录元数据。单文件上限 32 MiB；拒绝重复课程、跨课程重复 session、非法编号与不兼容格式。IndexedDB 持久化，两种目录分别更新；旧版导入优先于包内测试快照或上游在线索引，浏览器刷新及重新启动后继续使用。导入不会把元数据上传给第三方。

目录可找课不等于录像可播放。播放按真实 session 和 video 链路解析，并由平台验证当前登录、媒体与权限。收集实现、覆盖说明和 SHA-256 见 [采集说明](session-index-server.md)。
