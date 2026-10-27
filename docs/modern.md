# 新版延河课堂

基础地址：`https://aita.yanhekt.cn`。完整路径及来源见 [接口清单](../catalog/endpoints.json) 的 `modern.*`，可导入 [OpenAPI](../openapi/modern.json)。

## 会话校验

已完成平台正常登录后，从自己会话中的 `_token` 提取当前 Bearer，再调用：

```http
GET /userapi/v1/infosimple
Authorization: Bearer <当前会话 token>
```

消费的返回形状为 `{ "code": 200, "params": { ... } }`。`params.id` 是当前用户，`tenant_id` 是租户，`phone` 参与特定媒体地址签名，`account` 用于页面许可查询。不要在数据集或调试回执中保留这些实际值。

Cookie 值不一定是裸 JWT。yanhekit 当前通过 URL 解码后提取 JWT；参考插件还兼容 PHP 序列化 `_token` 包装中的非 JWT Bearer。两个解析器的接受范围不同，不能把“匹配不到 JWT”直接当成未登录。Cookie 的路径也可能不是站点根路径。

## 本人课程

```http
GET /vlabpassportapi/v1/account-profile/course?force_mycourse=1&nowpage=1&per-page=100
Authorization: Bearer <当前会话 token>
```

读取 `params.result.data` 与 `params.result.total`。课程行在该接口常用 `Id/Title/Teacher/TermName`，搜索接口却使用另一组小写字段。根据空页或累计数处理结束条件；客户端自己的最大分页数应另行说明。

## 搜索与筛选

```http
GET /courseapi/v3/multi-search/get-course-list?tenant=21&title=<关键词>&order=c.created_at%20desc&page=1&per_page=40
Authorization: Bearer <当前会话 token>
tenant-id: 21
```

`21` 只是本例租户值，实际取当前 profile。关键词用 URL 编码。读取 `data.list` 与 `data.total`，课程字段包括 `id/title/realname/term_name/kkxy_name`。

先通过 `/vlabpassportapi/v1/course/term-list` 的 `params.list` 把 `term_name` 转为 `term` 编号；通过 `/vlabpassportapi/v1/user/structures` 的 `params.data` 把院系名称转为 `struc_ids[]`。院系结构可以嵌套，应遍历树。找不到筛选项要报告或返回明确的筛选空结果，不能忽略筛选后查询全站。

yanhekit 暴露的排序对照为 `newest → c.created_at desc`、`oldest → c.created_at asc`、`popular → c.click_record_num desc`。参考插件当前仅使用最新优先。`per_page=40/50/100` 等是客户端选择；服务器支持的最大页大小未由本次整理确认。

这个搜索查询新版索引，不会检索旧站 `www.yanhekt.cn`。新版搜不到不能证明旧课不存在，也不能用两边的数字 ID 直接替换。

## 课程详情和课次

```http
GET /courseapi/v3/multi-search/get-course-detail?course_id=10001
```

合成的最小响应片段：

```json
{
  "code": 0,
  "data": {
    "id": 10001,
    "title": "示例课程",
    "realname": "示例教师",
    "term_name": "2026-2027-1",
    "zhiyuan_id": "30001",
    "sub_list": {
      "2026": [{
        "id": 200001,
        "sub_title": "示例课次",
        "class_begin": 1790000000,
        "playback_status": "1"
      }]
    }
  }
}
```

`sub_list` 不是固定深度数组，日期分组和章节分组都可能出现。递归处理对象、数组及课次的 `child`，按课次编号去重。`playback_status == "1"` 表示参考实现接受的回放条目；标题分组、安排和未生成的录像应分开处理。不能把“课次列表长度”当成“可播放文件数”。

`zhiyuan_id` 可作为新乐学关联候选，仍要检查课程身份。其它教师课程由 `get-course-teacher-others?course_id=…&per_page=20` 返回 `data[]`。这类元数据不保证每个关联课程都有当前用户可用的录像。

## 当天课表和直播

`/courseapi/v2/course-live/get-my-course-day?day=YYYY-MM-DD` 返回 `list.*.course[]`。关注 `course_id/sub_id/course_begin/course_over/room_name/sub_status`，日期按学校时区理解。

课程详情中 `type=course_live` 且尚未成为回放的条目，可依据 `sub_status` 区分：`1` 直播、`2` 未开始，其它值由参考实现归为已结束。真正打开时重新查询 `get-sub-info`，不要永久缓存旧直播状态。

```http
GET /courseapi/v3/portal-home-setting/get-sub-info?course_id=10001&sub_id=200001
```

回放消费 `duration` 和 `video_list`；直播消费 `sub_type/sub_status/live_url`。这两种返回共用接口，不能强制一律存在 `duration` 或 `video_list`。

`GET /coursesourceapi/course/study-auth/{courseId}/{subId}` 使用当前租户的 `Tenant-Id` 和 profile 的 `account` 作为 `username` 请求头；返回 `code=200`、`data.hasPermission`。这是页面许可诊断字段。页面标志与媒体服务的响应可能不一致；修改客户端布尔值不能赋予服务端权限。完整播放状态还要看媒体实际响应，不能把一个字段解释为任意课程都获得授权。

## 平台字幕

`GET /courseapi/v3/web-socket/search-trans-result?sub_id=…&format=json` 返回 `list[].all_content[]`。原始字段是 `BeginSec/EndSec/Text`，并不是 SRT，也不是 BCut 的结果。修订、去重、时间单位和视频偏移见 [媒体与字幕](media.md)。

## 平台资料

1. 调用 `get-course-resource?course_id=…&page=…&per_page=100`，读取 `data[]`；依据返回数量和 `total` 分页。
2. 行 `id` 是资料行编号，下载所需编号优先取非 `0` 的 `resource_id`，否则取 `old_resource_id`。
3. 名称由 `resource_name` 和可选 `resource_suffix` 组成，大小来自 `resource_size`。下载开放状态与资源是否存在分别判断。
4. 使用 `GET /spidermaterial/spider-material/web/download/dlUrl?ids=<资源编号>`，读取 `state=200` 的 `data` 字符串下载地址。

不要把资料行 `id` 直接当作下载资源 ID，也不要从文件名猜下载 URL。这个接口与新乐学 `/api/uploads/…` 是两套资源系统。
