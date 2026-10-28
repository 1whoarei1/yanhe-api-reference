# 旧版延河课堂

网页入口为 `https://www.yanhekt.cn`，JSON 接口基础地址为 `https://cbiz.yanhekt.cn`。见 [接口清单](../catalog/endpoints.json) 的 `legacy.*` 和 [OpenAPI](../openapi/legacy.json)。yanhekit 当前的新版客户端不覆盖这些旧站接口。

## 以 session 定位回放

`course_id` 表示课程 / 教学班，`session_id` 表示具体课次，`video_id` 表示该课次内的视频片段；它们是独立编号。同一数字出现在不同路径中不能视为同一个对象。

旧版回放的目标是 session。收到 `/session/{sessionId}` 或 `/ReadSession/{sessionId}` 后，使用该 `session_id` 调用 `/v1/course/session`，从响应中解析实际所属的 `course_id`；随后以返回的课程编号查询课次列表，并按目标 session 及 video 选择录像。不要把路径数字直接填入 `/v1/course?id=…`。

2026-10-27 对用户指定示例的定点公开元数据核对结果：

| 网页入口 | 实际身份 | 所属课程 |
| --- | --- | --- |
| [course/71990](https://www.yanhekt.cn/course/71990) | course `71990` | （英）材料电化学理论与应用 |
| [session/71990](https://www.yanhekt.cn/session/71990) | session `71990` | course `9397`，离散数学Ⅱ |
| [session/281490](https://www.yanhekt.cn/session/281490) | session `281490` | course `30226`，机器学习实践 |

这次使用旧站公开客户端请求头，未附带用户 Bearer；上述固定请求返回 HTTP 200、`code=0`。它只验证身份和归属，不证明全部接口允许匿名读取，也不证明媒体可播放。正式播放器仍使用本人已登录的会话。

客户端保存或分享回放目标时应保留 `session_id`，不能仅保存解析后的父课程编号。一个 session 内有多个 video 时，再保留 `video_id`；参考播放器的 `legacy_session` / `legacy_video` 是扩展自己的页面参数，不是新的平台 API 参数。

## 认证与请求头

参考客户端从本人已登录旧站的 `localStorage.auth.token` 取得旧站 Bearer，再调用 `/v1/user` 校验 `data.id`，另读取 `badge`。这不是新版 `_token`；参考解析器接受 32 位十六进制字符串，这一形状是客户端观察值。

旧站请求头对照：

| 头 | 参考实现的值 |
| --- | --- |
| `Authorization` | `Bearer <旧站当前 token>` |
| `Xdomain-Client` | `web_user` |
| `Xclient-Version` | `v1` |
| `Xclient-Timestamp` | 当前 Unix 秒的字符串 |
| `Xclient-Signature` | `MD5(CLIENT_KEY + "_v1_undefined")` |
| `Referer` / `Origin` | 参考浏览器实现对相应旧站域设置 `https://www.yanhekt.cn/` / `https://www.yanhekt.cn` |

`CLIENT_KEY = 1138b69dfef641d9d7ba49137d2d4875` 是参考旧网页协议中的公开客户端常量，不是用户 token。API 请求签名中的 `_undefined` 是参考实现的实际行为，不能因为它看起来异常，就未经验证改成时间戳。媒体请求使用另一种签名，见 [媒体与字幕](media.md)。

JSON 通常为 `{ "code": 0, "data": ... }`，非零业务码与 HTTP 错误分别处理。来源：[LegacyYanheApi](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/src/watch/legacy-api.js)、[legacy-core](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/src/watch/legacy-core.js)。

## 本人课程与课程详情

`GET /v2/course/private/list?page=1&page_size=100&user_relationship_type=1` 读取 `data.data`、`data.last_page` 和 `data.total`。课程常用 `id/name_zh/professors/school_year/semester`。这条路径是“我的课程”，不是新版的全站搜索。

`GET /v1/course?id=<courseId>&with_professor_badges=true` 读取课程名称、教师及学期。随后 `GET /v2/course/session/list?course_id=<courseId>` 获取课次和视频。

合成响应片段：

```json
{
  "code": 0,
  "data": [{
    "id": 400001,
    "started_at": "2026-09-23 08:00:00",
    "title": "示例课次",
    "videos": [{
      "id": 500001,
      "duration": 5400,
      "vga": "https://cvideo.yanhekt.cn/example/screen.m3u8",
      "main": "https://cvideo.yanhekt.cn/example/classroom.m3u8"
    }]
  }]
}
```

一个 session 可包含多个 video。`vga` 对应屏幕，`main` 或 `room` 对应教室。参考客户端用 `sessionId:videoId` 形成内部复合标识；这不是一个可以直接传给平台的数字 `session_id`。

课次元数据存在，不代表当前会话可以读取相应媒体。旧站其它课程的回放访问范围尚未由本次整理验证，不应把列表响应当作媒体授权。

## 旧页面链接的解析

| 网页地址 | 后续解析 |
| --- | --- |
| `/course/{courseId}` | 已有课程编号，查询课程和 session 列表 |
| `/session/{sessionId}`、`/ReadSession/{sessionId}` | `/v1/course/session?session_id=…&with_video=true` |
| `/live/{liveId}` | `/v1/live?id=…&with_session=true&with_course=true` |

从接口返回的 `course_id`、`course.id`、`session.course_id` 确认归属；返回多个不同课程编号时应报告结构冲突。直播和 session 页面只靠路径数字不能决定所属课程。

`with_video=true` 不保证响应内直接带有可播放的 `videos` 数组。此次 session 元数据响应含 `id/course_id/title/course/video_ids`；实际视频片段仍按课次列表中的 `videos[]` 读取，字幕使用其中 video 的编号。空列表、元数据可读、媒体授权、媒体响应和视频解码分别判断。

## 目录数据与后续接入

旧版课程表已暂停使用和分发，它是课程级目录，没有独立 session 表或 `session_id` 字段，不能把它的 course 编号换成同号 session 链接。旧版 session 目录正在另行准备，尚未接入播放器或本接口项目；这里没有新增或声称存在全站 session 搜索接口。

后续接入时至少核对目标 `session_id` 与接口返回的 `course_id`，多个视频片段继续按各自 `video_id` 区分。接入文件格式待实际数据确定，不从旧课程表猜测映射。

## 直播课程列表与跨站对应

旧站课程页调用 `GET /v2/live/list?source_id=<旧站 course_id>&page=1&page_size=100`，读取 `data.data`。这里的筛选键是 `source_id`；`course_id` 会被忽略，不能据其响应把全站直播误当作某门课的直播。结果还应核对 `row.course.id` 或 `row.source_id`，直播详情再核对实际课程归属。

2026-10-28 对照旧站当前前端与公开元数据核验：`source_id=73687` 返回该课程的直播预告；使用 `course_id=73687` 得到的是全站列表。该课程和新版 `102154` 在已有目录中均为「计算机新技术专题」、黄河燕、2026–2027 第一学期。这是课程级对应，不能据此推导两站课次编号相等。

播放器保存的是独立的课程关联：`{modern: "102154", legacy: "73687"}`。每次切换重新读取两站课次，按学校时区的上课时间定位；多个同时段候选时要求具体直播链接。旧站 `live_id/session_id/course_id`、新版 `sub_id/course_id` 保持各自语义，不互换同号 ID。关联仅保存在浏览器本地，不含登录凭据或视频地址。

画面布局与声音选择分开：三画面采用左侧主画面、右侧上下两路。声音可以来自未展示的第三路，始终只输出一个来源。完整 HLS 构建支持分离音轨；签到模式的画面跳帧使用独立于声音的时钟。

## 直播

`GET /v1/live?id=<liveId>&with_session=true&with_course=true` 消费 `data.id/course_id/session_id/status/schedule_started_at/schedule_ended_at`，以及：

| 字段 | 画面 |
| --- | --- |
| `target` | 主画面 / 教室 |
| `target_vga` | 屏幕 |
| `target_room` | 学生 / 其它教室机位 |

参考实现优先按 `status=1` 显示直播、`3` 显示结束；明确仍在直播的状态不被课表结束时间覆盖，以支持延时下课。`2` 为待开始，并用学校时区下的安排时间窗口修正其显示状态。这是客户端状态推断，不是新增服务端状态码。不能把它当作媒体流已经发布的保证。

只使用实际返回的 HLS / FLV 地址。旧站的直播列表、旧直播页面与新版直播房间不是同一个接口体系。当前旧站直播已有合成媒体测试，尚未完成真实直播场景验收，见 [验证范围](verification.md)。

## 播放凭据与字幕

`GET /v1/auth/video/token?id=<当前用户 badge>` 返回 `data.token/expired_at/now`。参考实现缺省传 `0`，不能把这里的 `id` 理解为 course 或 video ID。短期凭据在内存使用，根据有效期重新获取；不要把完整签名视频地址写入长期目录。`clive*.yanhekt.cn` 的旧站直播沿用直播接口返回的地址，参考实现不另加新版签名，也不要求先申请录播 token；只有 `cvideo/coss` 等录播域名继续使用旧站短期播放凭据。

`GET /v1/video/subtitle/list?video_id=<videoId>` 返回字幕列表，消费 `language` 和 `url/src`。选取中文项或第一项后读取其文件。参考解析器支持常见 VTT / SRT，不保证其它字幕格式，也不把没有字幕判为没有录播。

## session 索引与视频元数据

旧版课程搜索与课次发现已接入 [公开在线索引](autoslides.md)。原旧版课程表继续停用。session ID 仍为播放目标，课程 ID 用于查找父课程及索引课次。选择索引课次后读取 `/v1/course/session` 的 `video_ids`，验证所属课程与片段，再通过 `GET /v1/video?id=` 获取所选视频的 `main/vga/room/audio/duration`。该视频对象的 `course_id/session_id` 可能为 0，不作为归属依据。接口失败或空 `video_ids` 分别提示，不将“未收录”解释为“没有回放”。
