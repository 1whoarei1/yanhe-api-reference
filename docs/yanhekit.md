# yanhekit 对照与整合

对照对象：[windlandneko/yanhekit](https://github.com/windlandneko/yanhekit)，固定修订 [cb270ee0aa037400bc7d92bbb518392b804d6513](https://github.com/windlandneko/yanhekit/tree/cb270ee0aa037400bc7d92bbb518392b804d6513)。这次整合的对象是底层接口说明和可验证的字段关系，面向任意客户端，不把浏览器扩展当成平台协议本身。

## 共用的 8 个 HTTP 接口

| 功能 | 上游入口 | 协议关系 |
| --- | --- | --- |
| 当前用户校验 | `Yanhekt.authenticate` | `/userapi/v1/infosimple` |
| 本人课程 | `Yanhekt.courses` | `/vlabpassportapi/v1/account-profile/course` |
| 学期列表 | `Yanhekt.search` | `/vlabpassportapi/v1/course/term-list` |
| 院系列表 | `Yanhekt.search` | `/vlabpassportapi/v1/user/structures` |
| 新版课程搜索 | `Yanhekt.search` | `/courseapi/v3/multi-search/get-course-list` |
| 课程及回放课次 | `Yanhekt.course` | `/courseapi/v3/multi-search/get-course-detail` |
| 单课次回放 | `Yanhekt.lecture` | `/courseapi/v3/portal-home-setting/get-sub-info` |
| 平台字幕 | `Yanhekt.fast_transcript` | `/courseapi/v3/web-socket/search-trans-result` |

已合并到 [新版接口](modern.md)、[媒体与字幕](media.md) 及机器可读清单。签名是客户端计算，不另算一个 HTTP 接口。

## 两个实现的差异

| 项目 | yanhekit 的对照版本 | 参考插件版本 | 底层文档中的处理 |
| --- | --- | --- | --- |
| token 提取 | 解码 Cookie 后匹配 JWT | 还接受序列化 Cookie 中的非 JWT Bearer | 记录两种接受范围，不声明 token 必须是 JWT |
| 登录 | 独立会话文件、SSO 及本地登录页 | 使用本人当前浏览器会话 | 认证会话与具体存储方式分开说明 |
| 课程搜索 | 默认单页 50，可指定排序 | 请求单页 40，固定最新优先 | 记录实际参数；分页值不作为平台上限 |
| 院系查找 | `named` 在传入列表按名称查找 | 递归遍历院系结构 | 提醒结构可能嵌套 |
| 课次遍历 | 日期分组递归，匹配回放状态 | 额外遍历带标题条目的 `child`、去重并区分直播 | 文档覆盖日期和章节，不复制上游遍历器 |
| 视频 | `duration_s`、`streams`，只处理回放结构 | `duration`、`mode`、`streams/candidates`，区分直播 | 原始服务端字段保持独立；客户端字段不是 API 原响应 |
| 媒体签名 | 对传入 URL 重建 `t` query | 仅对 `/play/` 地址使用新版签名 | 明确适用路径；旧媒体签名另列 |
| 字幕修订 | 同开始时间覆盖 | 覆盖后增加有效性过滤和排序 | 说明原始字段、修订和时间单位 |
| 校园网络优化 | Python 探测内网后改变连接解析，保留 TLS 主机校验 | 浏览器使用自身网络栈 | 作为运行环境差异记录，不混入 HTTP 参数 |
| 视频下载 | Python 并发分段、续传、本地文件工作区 | 浏览器流式写入、媒体格式处理 | 共享资源协议，下载调度和保存策略分别实现 |
| 直播 / 旧站 / 乐学 | 当前主客户端没有这些实现 | 有相应独立适配器 | 单独文档，不误写成上游已有功能 |

## 可以怎么复用

共同部分可以支撑独立的 Python、JavaScript 或其它语言 SDK：把认证后的 HTTP 会话、原始 API 响应、课次遍历、字幕归一化和媒体 URL 准备拆为模块。认证材料由调用方提供；SDK 不默认读取浏览器个人资料或系统钥匙串。

保留原始响应和可选的统一模型，避免为了兼容某个 UI 而丢弃 `sub_type/sub_status/live_url/resource_id/zhiyuan_id`。建议把 HTTP 传输层作为可注入组件，从而分别适配 requests、浏览器扩展和其它运行环境。字段归一化、重试、并发、缓存和文件保存应与平台请求契约分离。

如果以后需要互通本地工作区，可参考 [上游文件格式](https://github.com/windlandneko/yanhekit/blob/cb270ee0aa037400bc7d92bbb518392b804d6513/skills/yanhekit/references/files.md)：`course.json` 的 `course_id/title/teacher/term/lectures[]`，每项包含文件夹标识 `id` 和真实课次 `sub_id`。这不是课程搜索返回的 JSON，也不是插件公开目录格式；导入应显式转换，不能直接覆盖文件。

本次只准备文档、合成响应及 OpenAPI，没有安装 SDK、运行下载、提取 PPT 或启动识别。上游 Python 源码与技能未并入本目录。

## 外部服务参考

以下来自上游 `transcribe.py`，**不是延河课堂接口，也未由本次整理实际调用**：

基础地址 `https://member.bilibili.com/x/bcut/rubick-interface`。

| 请求 | 上游使用方式 |
| --- | --- |
| `POST /resource/create` | 表单字段 `type/name/size/resource_file_type/model_id`；读取 `upload_urls/per_size/in_boss_key/resource_id/upload_id` |
| `PUT <返回的分段 upload_url>` | 上传音频分段，收集响应 ETag |
| `POST /resource/create/complete` | 提交资源、上传编号及分段 ETag，获得 `download_url` |
| `POST /task` | JSON 中传 `resource/model_id`，读取 `task_id` |
| `GET /task/result` | 查询 `model_id/task_id`；上游把 `state=4` 当成功、`3` 当失败 |

上游当前模型值为 `7`，这不是对外部服务长期可用性或模型枚举的保证。返回 utterance 时间为毫秒。真正集成前还需独立确认当前服务、用户对音频外传的授权、限流和许可；本目录不添加外部服务权限，也不提供自动上传音频的示例。

上游 `server.py` 还有 `/api/events/login/resend/verify/cancel` 等 **本机登录 UI** 路由，带一次性 X-Token 和 Host 校验。它们只服务本地认证流程，不是公共课程 API，更不是运行中的通用视频 HTTP 服务，不能据此假定存在可直接接入的远程 SDK。

## 许可与来源

对照版本的 yanhekit 为 AGPL-3.0，参考插件自身代码为 MIT。本目录记录接口事实、差异和原创说明，未分发它们的实现代码。若之后选择直接纳入上游代码，应在那次整合中分别核对所用修订、许可证、来源和分发方案，不能仅凭“感谢上游”就把其代码改标为 MIT。完整来源见 [SOURCES.md](../SOURCES.md)。
