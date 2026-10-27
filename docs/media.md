# 媒体与字幕

视频源和字幕源都是前一步接口返回的资源，不是由课程标题或编号自行拼出的固定文件地址。

## 新版回放字段

`get-sub-info` 的 `data.video_list` 可以是按键组织的对象，遍历其值：

| 字段 | 语义 |
| --- | --- |
| `type=2` 或 `"2"` | 屏幕画面 |
| `type=3` 或 `"3"` | 教室画面 |
| `status=2` 或 `"2"` | 参考客户端接受的就绪视频 |
| `preview_url` | 当前返回的媒体地址 |
| `duration` | 课次时长，参考客户端按秒读取 |

`video_list` 的对象键不是可靠的机位类型；按每个值的 `type/status` 识别。一个画面缺失或返回 404，不代表另一个画面不可用。文件扩展名和响应 Content-Type / 播放器能力一起判断。

## 新版 `/play/` 地址签名

参考插件仅对返回 URL 的 pathname 以 `/play/` 开头的地址重建 `t` query。取当前合法登录 profile，按下面的字段顺序计算：

```text
timestamp = 当前 Unix 秒
digest = MD5(pathname + userId + tenantId + reverse(phone) + timestamp)
t = userId + "-" + timestamp + "-" + digest
```

参与拼接的数值转换为字符串，不加入分隔符；pathname 保留 URL 本身的路径语义，时间单位不能用毫秒。参考实现将 query 替换为单个 `t` 参数。手机号只用于内存计算，不出现在文档示例、日志或导出数据。

yanhekit 的 `Yanhekt.sign` 使用同一套字段关系，但当前对传入地址一律重建 query；插件先判断 `/play/`。因此迁移时要区分具体媒体路径，不能让通用网络层对所有 CDN URL 盲目覆盖已有 query。

来源：[插件 signedUrl](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/src/watch/core.js)、[yanhekit client.py](https://github.com/windlandneko/yanhekit/blob/cb270ee0aa037400bc7d92bbb518392b804d6513/skills/yanhekit/scripts/client.py)。这类计算是在当前会话基础上准备媒体请求，不能代替服务端授权。

## 新版直播字段

`data.live_url` 中的 `output`、`output_ppt`、`output_student` 分别对应教室、屏幕和学生机位。每项可能直接是字符串，也可能包含 `m3u8/m3u8_lhd/m3u8_lsd/flv/flv_lhd/flv_lsd` 等候选字段。

回放的 `video_list` 与直播的 `live_url` 不是可互换的结构。直播结束后可能暂时没有回放，随后才生成回放信息。媒体地址应重新读取，避免把旧直播地址持久化成永久资源。

## 旧版媒体地址

旧站返回 `cvideo.yanhekt.cn` 或 `coss.yanhekt.cn` 地址时，参考实现使用旧站短期 video token 和公开客户端常量：

```text
marker = MD5(CLIENT_KEY + "_200")
Xclient_Signature = MD5(CLIENT_KEY + "_v1_" + timestamp)
```

在文件名前的倒数第二个路径段插入 `marker`，已经存在时不重复插入；query 更新 `Xvideo_Token/Xclient_Timestamp/Xclient_Signature/Xclient_Version/Platform`，其中版本为 `v1`，平台为 `yhkt_user`。其它原有 query 的保留规则与新版替换全部 query 的行为不同。

旧直播返回其它受支持的延河媒体域名时，参考实现保留原地址，不强套 `cvideo/coss` 的改写。上述行为的来源为 [legacy-core](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/src/watch/legacy-core.js)，旧 API 的请求头签名另见 [旧版接口](legacy.md)。

## 媒体请求的层次

- `HEAD` 可以用于探测，但部分服务器返回 `405/501`。参考播放器在这两种情况下交由实际媒体读取判断，不能仅凭 HEAD 不支持就判为坏源。
- HLS 要依次解析主清单、媒体清单、相对分段、初始化段、字节范围和可能的 AES-128 key URI。分段和 key 的地址解析必须以各自清单 URL 为基准。
- MP4 可能依赖 Range；FLV 通常需要对应的流媒体解封装能力。直播 HLS 的滑动窗口不能按完整回放清单处理。
- 浏览器下载、网页 `fetch`、扩展后台 `fetch` 的重定向和 CORS 行为不同。“网页 fetch 失败”不自动等于“服务器不存在此文件”。
- 参考插件约束媒体来源为延河 HTTPS 域名，并为扩展发出的部分请求配置 Referer / Origin。这是具体浏览器实现策略；其它客户端应根据所用运行环境处理相同 HTTP 语义。

长期缓存仅保存课程和课次元数据。媒体地址、签名 query、鉴权结果和未完成直播清单不应当成永久可复用记录。参考客户端的缓存时长不是媒体服务承诺的有效期。

## 平台字幕

合成响应片段：

```json
{
  "code": 0,
  "list": [{
    "all_content": [
      {"BeginSec": "68.0", "EndSec": "72.5", "Text": "示例字幕。"},
      {"BeginSec": "68.0", "EndSec": "73.0", "Text": "示例字幕的修订。"}
    ]
  }]
}
```

遍历全部 `all_content`；将开始和结束转为有限数值，要求 `0 <= start < end` 且文本非空。同一开始时间可能重复出现修订，参考实现保留后出现的一项，再按开始时间排序。yanhekit 当前也按开始时间覆盖重复项，但没有与插件完全相同的排序和无效段过滤。

推荐在各 SDK 内统一为 `{start, end, text}`，单位保持秒。这是归一化后的客户端数据，不是服务器原字段名。导出 SRT / VTT 时再格式化毫秒，字幕重叠和文件换行由输出层处理。

字幕时间轴可能与某一视频机位存在整体偏移。校准量的约定可用 `displayStart = BeginSec + offsetSeconds`，正值表示字幕更晚出现。校准是本地映射，不应覆盖原始平台时间，也不能把 `1:08` 误读为 `1.08` 秒。

BCut 是独立第三方服务；它返回的 `start_time/end_time` 为毫秒，需要除以 1000，且结果不是平台字幕。本文档未启动识别或上传音频，外部服务接口只列于 [yanhekit 对照](yanhekit.md)。
