# 通用约定

## 系统与域名

| 系统 | 网页入口 | 数据接口 / 文件服务 | 登录态 |
| --- | --- | --- | --- |
| 新版延河课堂 | `https://aita.yanhekt.cn/portal/#/`、`/coursedetail`、`/livingroom` | 同域的 `userapi`、`vlabpassportapi`、`courseapi` 等；媒体来自平台返回的域名 | `_token` 所属的新版会话和 Bearer |
| 旧版延河课堂 | `https://www.yanhekt.cn/` | `https://cbiz.yanhekt.cn`；旧媒体常见 `cvideo.yanhekt.cn`、`coss.yanhekt.cn` | 旧站独立 Bearer 及 Xclient 请求头 |
| 新乐学 | `https://zy-eclass.bit.edu.cn/` | 同域 `/api/`、`/internal-api/`；观测到校内上传服务 `https://zy-media.bit.edu.cn` | 浏览器已登录会话；写入时按需带 CSRF 头 |
| 旧乐学 | `https://lexue.bit.edu.cn/` | Moodle AJAX、模块 HTML、`pluginfile.php` | 已登录会话；部分读取 RPC 还需要当前 `sesskey` |

`https://yanhe.bit.edu.cn/` 是另外的学校入口，不能据此把上述系统的请求路径混用。统一身份认证会跳转到其它官方域名；这里不提供密码、验证码或短信认证的重放接口。

## 编号

| 名称 | 意义 | 常见误用 |
| --- | --- | --- |
| 新版 `course_id` | 新版课程 / 教学班 | 不能当作旧站 course、直播或新乐学课程编号 |
| 新版 `sub_id` | 一次课次，可能是直播安排或已生成回放 | 只有课程编号不能直接替代课次编号 |
| `tenant_id` / `tenant_code` | 租户标识，北理工观察值为 `21` | 其它租户应读取当前用户信息，不能全局写死 `21` |
| `zhiyuan_id` | 新版详情中指向新乐学的课程关联值 | 为空或 `0` 不代表同名课程可以自动关联 |
| 旧站 `course_id` | 课程 / 教学班 | `/course/71990` 与 `/session/71990` 是不同对象 |
| 旧站 `session_id` | 回放目标课次 | 先解析它所属的课程，不能用同号 course 替代；保存回放目标要保留 session |
| 旧站 `video_id` | 一个 session 内的视频片段 | 同一 session 可以有多个 video；字幕接口用 video 编号 |
| 旧站 live ID | 直播安排 | `/live/…` 后的编号不是 course ID，也不能因为存在关联 session 就自动改为回放 |
| 新乐学 `activityId` | 资料或作业活动 | `course_id` 与活动编号不是同一个值 |
| 新乐学 `uploadId` / `reference_id` | 文件实体 / 文件引用 | 下载引用、上传文件和提交记录编号不可互换 |
| Moodle module ID | 课程页面 `module-…` 及模块 URL 中的 `id` | 不是课程编号，也不是 `pluginfile.php` 的 context ID |

跨客户端保存标识时使用字符串，避免 JSON 数值精度、前导零和平台同号的问题。参考插件的数字校验通常限制 1–12 位，这是客户端约束，未验证为服务端通用长度上限。

## 请求与响应

新版同一域名有多组网关，不能把所有 `code` 都按 `0` 处理：

- `infosimple`：参考客户端要求 `code=200` 并读取 `params`。
- 本人课程列表：插件要求 `code=1000` 并读取 `params.result`。
- 课程、课次、字幕等：参考客户端接受 `0` 与 `10002`；后者可能代表没有录播，不能直接归为鉴权失败。
- 学期与院系：插件兼容 `1000/0/200`，这是客户端接受范围。
- 资料下载地址接口：判断字段为 `state`，不是 `code`。
- 旧站 `cbiz`：参考客户端要求 `code=0`，结果通常在 `data`。
- 新乐学：通常直接返回 JSON 资源，不套用延河课堂业务码；遇到登录 HTML 不能继续当 JSON 解析。
- Moodle：AJAX 返回数组，单项有 `error` 与 `data`；许多其它入口返回 HTML 或文件。

HTTP 成功、业务码成功和资源已生成是三个条件。不要用 `HTTP 200` 直接推断视频、字幕或作业提交已经完成。

## 认证材料的边界

新版与旧版 Bearer、乐学会话和 Moodle `sesskey` 分开管理。跨域媒体请求是否携带认证信息取决于对应服务；新乐学 MEDIA 上传已经观察到可以按返回 URL 传文件，参考实现不向该域转发新乐学 Cookie 或 CSRF 头。

浏览器页面脚本不能随意设置 `Cookie`、`Origin` 或 `Referer`。Python `requests`、浏览器扩展后台、内容脚本和普通网页的 CORS、重定向及请求头能力不同，协议移植不能只复制一个 `fetch`。OpenAPI 中的 Cookie 头用于描述已有会话，不代表浏览器控制台可以手写该头。

日志只记录方法、域名、路径、状态及字段名；删除 Cookie、Authorization、手机号、账号、`sesskey`、短期 token 与带签名的 query。公开例子使用合成编号与内容。

## 时间与分页

- 字幕 `BeginSec` / `EndSec` 是秒；BCut 的原始时间是毫秒，详见 [媒体与字幕](media.md)。
- 新版 `class_begin` 在参考实现中按 Unix 秒处理。界面内部的 JavaScript 日期和学习进度可能使用毫秒，不能混入原始 API 字段。
- 没有时区的学校本地时间在参考实现中按 `Asia/Shanghai` 解释；带 `Z` 或偏移的时间保留其时区。不要用开发机器的本地时区解释学校课表。
- 课程搜索使用 `page/per_page`，本人课程使用 `nowpage/per-page`，Moodle 使用 `offset/nextoffset`。不要全局替换参数名字。
- 搜索总数会变化，跨页可能重复；按平台、租户和课程 ID 去重。遍历有分页保护不等于服务端结果完整；不要用一个历史目录断言当前全量课程数。

## 错误与重试

读取失败先区分网络异常、HTTP 鉴权拒绝、业务码、登录 HTML、字段变化和资源未生成。不要把失败全部降级为空列表。`401/403` 不应通过伪造角色、修改许可布尔值或换学生编号处理。

GET 的受控重试、退避和取消由客户端决定；不要对上传建档、回调或作业提交套用统一的自动 POST 重试。特别是提交响应丢失时，先回读本人记录；客户端随机 `requestId` 并不是平台承诺的服务端幂等键。

这里记录的是参考实现和已观察字段。分页上限、并发数、超时、缓存 TTL、上传大小、域名白名单和 UI 提交限制属于客户端策略，除非有额外证据，不能写成平台的协议限制。
