# 旧版延河课堂

网页入口为 `https://www.yanhekt.cn`，JSON 接口基础地址为 `https://cbiz.yanhekt.cn`。见 [接口清单](../catalog/endpoints.json) 的 `legacy.*` 和 [OpenAPI](../openapi/legacy.json)。yanhekit 当前的新版客户端不覆盖这些旧站接口。

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

## 直播

`GET /v1/live?id=<liveId>&with_session=true&with_course=true` 消费 `data.id/course_id/session_id/status/schedule_started_at/schedule_ended_at`，以及：

| 字段 | 画面 |
| --- | --- |
| `target` | 主画面 / 教室 |
| `target_vga` | 屏幕 |
| `target_room` | 学生 / 其它教室机位 |

参考实现把 `status=1` 解释为直播，`2` 解释为待开始，`3` 解释为结束；还用学校时区下的安排时间窗口修正 `2` 的显示状态。这是客户端状态推断，不是新增服务端状态码。不能把它当作媒体流已经发布的保证。

只使用实际返回的 HLS / FLV 地址。旧站的直播列表、旧直播页面与新版直播房间不是同一个接口体系。当前旧站直播已有合成媒体测试，尚未完成真实直播场景验收，见 [验证范围](verification.md)。

## 播放凭据与字幕

`GET /v1/auth/video/token?id=<当前用户 badge>` 返回 `data.token/expired_at/now`。参考实现缺省传 `0`，不能把这里的 `id` 理解为 course 或 video ID。短期凭据在内存使用，根据有效期重新获取；不要把完整签名视频地址写入长期目录。

`GET /v1/video/subtitle/list?video_id=<videoId>` 返回字幕列表，消费 `language` 和 `url/src`。选取中文项或第一项后读取其文件。参考解析器支持常见 VTT / SRT，不保证其它字幕格式，也不把没有字幕判为没有录播。
