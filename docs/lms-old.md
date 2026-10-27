# 旧乐学 Moodle

基础地址：`https://lexue.bit.edu.cn`。见 [接口清单](../catalog/endpoints.json) 的 `lexue.*` 和 [OpenAPI](../openapi/lexue.json)。这是 Cookie 会话、JSON RPC 和服务端 HTML 的混合接口，不能照搬新乐学的 `/api/activities`。

## 会话与本人课程

1. 使用本人正常登录的会话读取 `GET /my/`。
2. 从页面脚本中的 `M.cfg` 读取 `wwwroot` 和 `sesskey`，确认属于当前站点。
3. 调用以下课程概览 RPC；这个 POST 是读取，不是提交或修改课程。

```http
POST /lib/ajax/service.php?sesskey=<当前会话 sesskey>&info=core_course_get_enrolled_courses_by_timeline_classification
Content-Type: application/json
```

```json
[{
  "index": 0,
  "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
  "args": {
    "classification": "all",
    "limit": 100,
    "offset": 0,
    "sort": "fullname"
  }
}]
```

读取 `[0].error`、`[0].data.courses` 与 `nextoffset`。课程行消费 `id/fullname/startdate/visible/hidden/coursecategory`；`limit=100` 是参考客户端请求值，不是本次确认的平台上限。

`sesskey` 不是稳定 API key，不能从其它账号复制，也不应作为公开文档样例。会话和配置随登录变化，失效后走正常登录流程。

## 课程页与活动

`GET /course/view.php?id=<courseId>` 返回 HTML。参考解析器检查 `body` 上的 `course-{id}`，从 `.activity` 的 `module-{id}`、`modtype_*`、活动链接和 `.instancename` 读取活动。页面结构是当前证据，不是 Moodle 长期保证的 JSON schema。

| 模块 | 观察到的读取方式 |
| --- | --- |
| `resource` | 访问 `/mod/resource/view.php?id=…`，可能重定向到文件；参考客户端用 `Range: bytes=0-0` 探测名称、大小和最终文件 URL |
| `folder` | 从模块 HTML 提取实际附件链接 |
| `page` / `book` | 从当前模块页提取正文和实际附件；不保证自动遍历整本 book 的所有章节 |
| `url` | 识别为外链活动，参考资料读取器不继续抓取外部目标 |
| `assign` | 读取题目、附件和当前学生提交状态；最终上传及提交留给官方流程 |
| `quiz` / `vpl` / `workshop` | 保留活动入口；可尝试读取简介，状态不能按普通 assign 的完整语义处理 |

从已经属于本人课程的模块链接继续读取。不能仅凭一个数字猜它属于哪门课，或在遇到权限失败后改成别人的模块编号。

## 正文、附件和状态

正文通常在 `#region-main` 内的 `#intro` 或 `.generalbox`。资料附件可以来自 `<a href>`、`<object data>`、`<embed src>` 或 `<iframe src>`，只接收确实指向当前站点 `pluginfile.php` 的链接。

`GET /pluginfile.php/{contextId}/{filePath}` 是路径族；后缀含组件、文件区、item ID、子目录和文件名等多个路径段。应该保留页面返回的完整路径，再按需要设置 `forcedownload=1`，不要由文件名或模块编号猜出它。OpenAPI 的 `{filePath}` 是展示后缀的占位，代码生成器可能会对其中斜杠编码，不应把它当作可以无条件拼接的客户端方法。

`assign` 页的 `.submissionstatustable` 可包含状态、截止日期、最后修改和本人已交附件。原始响应仍是 HTML；`pending/submitted/unknown` 等是客户端根据文字归一化的结果，不是 Moodle 返回的 JSON 枚举。草稿、未尝试和已正式提交应分别解释。

截止日期的中文文本解析、`24:00` 和学校本地时区也属于客户端行为。缺少字段时保留未知，不能把解析不到时间当作没有截止日期。

## 当前范围

这份资料覆盖本人课程、模块内容、说明附件及可读取的本人状态。尚未整理 Moodle 原生文件草稿区、repository 文件选择器、编辑提交和最终确认的完整写入协议。不要因为新乐学已经支持上传，就把它的 payload 发到 Moodle。

来源：[LexueReader](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/src/lexue-reader.js)、[lexue-core](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/src/lexue-core.js)。参考解析器不执行抓取页面中的脚本；需要展示富文本的客户端应另做内容清理。
