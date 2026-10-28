# 自建旧版 session 索引

采集器使用 [bit-admin / Yanhekt-AutoSlides](https://github.com/bit-admin/Yanhekt-AutoSlides) 的 Apache-2.0 索引器，固定修订为 `84fff4da48c6f466073334613bc1eaeb48383d53`。感谢作者公开实现。我们增加了 Linux 后台监督、明文导出与有界并发；构建产物保留许可证、修改说明、原始文件和逐文件校验值。

这是独立采集的旧站元数据，不读取已停用的旧表，也不解密上游 release。已取回明文快照并接入 Refine 0.9.8 / Replay 0.4.3 的本地测试包；普通包仍通过在线索引查询，尚未发布自建数据服务。

## 采集与整理

- 固定扫描 session ID `1..1000000`。最新优先策略为：先扫描 `892999→1`，完成后补扫 `931999→893000` 与 `932000→1000000`。`893000` 来自用户提供的本学期起点估算，只决定扫描顺序；所有区间仍会覆盖，不通过缺号抽样跳过。
- 每个 session 保存原站返回的 `course_id`。同一课程的课次可以任意不连续；导出以 course ID 聚合，同名不同 ID 的课程分别保留。
- 历史优先扫描一直到 session ID `1`，包含 2024–2025 之前的 2023–2024、2022–2023 及更早课程；自建导出没有最低学年限制，已采集的早期课程会保留。上游客户端分片的默认最低学期不用于我们的明文导出。
- 每批读取 session 并补充课程详情；不启用视频地址采集、媒体下载和远程数据上传。
- 用户授权提速后，改为**最多 5 个并发请求**，全局请求开始间隔至少 **200ms**，另有最多 10% 抖动；目标总速率约每秒 5 次。网络延迟、课程补全和重试会降低实际课次扫描速度。
- 所有请求共享额度和限速器。每组结果全部结束后按扫描顺序保存；临时故障停在失败 ID，后续已响应但未提交的 ID 会重取。SQLite 数据和游标在同一事务内提交。
- 遇到 HTTP 错误、超时或系统繁忙，沿用指数退避；关闭时等待当前请求结束并保存断点。

初始部署使用每秒一次的串行配置；上述并发配置是后续授权的更新。不要同时启动五个共享同一游标的采集进程。

用户提供的学期起点参考如下，全部为估算；课程最终学期仍读取原站 `course.school_year/semester`：

| 学期 | 估算首个 session ID |
| --- | ---: |
| 2026–2027 第一学期 | 893000 |
| 2025–2026 第二学期 | 823000 |
| 2025–2026 第一学期 | 743000 |
| 2024–2025 第二学期 | 678000 |
| 2024–2025 第一学期 | 605000 |
| 2023–2024 第二学期 | 543000 |
| 2023–2024 第一学期 | 463000 |
| 2021-03 | 1 |

原来 `931999→1` 的游标自动拆分迁移到两个不重叠区间，原始记录保留；不会把延后的编号标成已扫描，也不会重置已完成进度。`historicalPriorityDone` 仅表示历史优先区间已扫完，不代表所有往年课程已收齐；最后仍需补扫其余范围，以免估算边界交错造成遗漏。

按用户给出的例子定点核对，`session/916997` 的匿名元数据返回成功，course ID 为 `73499`，学期为 `2026-2027-1`。原站页面的观看权限与元数据可读性分别判断；本采集器不尝试播放或绕过权限，也不根据页面无法观看就把 session 判为不存在。

## 构建与运行

需要 Python、Node 22 的 `node:sqlite`、esbuild，以及固定修订的上游检出。构建器只修改临时副本，自动运行上游与本地并发测试；测试失败不生成新归档。

```sh
python tools/build-session-index-server.py \
  --upstream /path/to/Yanhekt-AutoSlides \
  --esbuild /path/to/node_modules/esbuild/bin/esbuild \
  --output /path/to/deploy.tar.gz
python -m unittest discover -s tests -p 'test_session_index_server.py'
```

服务器根目录为 `~/.local/share/yanhe-session-index`。部署代码前停止用户服务、备份原数据库和代码，核对归档与 `source/SOURCE.json`；保留 `data/` 和 `supervisor.json`。单进程文件锁防止重复启动。更新后沿用原有 lane key 与 SQLite 表结构，无需重新扫描。

```sh
systemctl --user start yanhe-session-index.service
systemctl --user status yanhe-session-index.service
python3 ~/.local/share/yanhe-session-index/runner.py status
journalctl --user -u yanhe-session-index.service -n 20 --no-pager
systemctl --user stop yanhe-session-index.service
```

服务由 systemd 用户实例运行，启用 linger 后独立于 SSH 和 Codex。按用户要求不创建持续监测或定时通知。

## 数据文件

- `data/yanhekt-index.db`：SQLite 主库，保留 session 详情、课程信息和扫描游标。
- `exports/catalog.json`：明文课程目录；每门课程包含 `id/name/number/term/teachers/sessions`。课次 ID 升序，播放仍以 session ID 为目标。
- `exports/catalog.json.gz`：同一 JSON 的 gzip 压缩，无加密。
- `exports/status.json`：覆盖范围、数量和目录 SHA-256。

每批自动导出；Windows 取回的文件只是快照。`partial: true` 表示仍在采集；扫描结束仅指上述固定范围，不能据此推断范围之外不存在课次。`requests` 统计已结束批次，运行中批次的请求数见日志。

原始修改文件保存在 `source/upstream/`；本地补丁在 `source/local/session-index-concurrency.py`，修改标识为 `bounded-concurrency-v1`。

## 插件正式发布与快照测试

Refine 0.10.0 / Replay 0.5.0 的正式 ZIP 均提供 `课程目录/课程目录.json` 与 `课程目录/旧版课次目录.json`，通过插件界面分别导入。数据仅作为 Release 资产，留在本地忽略路径，不提交 Git；旧版 XLSX 表不包含。

本次快照生成于 `2026-10-28T10:10:33Z`，包含 **14,435 门课程、132,050 个 session**，SHA-256 `5b8ad0082b96d49a22931a9a78d66bd34e504b1bdc454fab78d1e5a63c78288d`。`partial: true` 明确标记仍在采集。正式包不默认把快照注入运行时，用户导入后在 IndexedDB 持久化并优先使用；开发者仍可显式构建带 `legacy-session-index.json` 的本地包。

两插件按快照的 course→session 明确关系检索和每页 40 门分页；早期课程保留。课次列表允许不连续，点击时按 session ID 向原站解析视频。内部 `indexSource=autoslides` 为兼容标记，导入的数据来源为 `self-collected`。

隔离浏览器使用实际两份发布目录，验证导入、刷新恢复、不连续 session 归属与无需上游索引的查询。学校响应为合成夹具，没有执行真实媒体播放或下载。早期 7,508 门 / 48,931 个 session 的本地快照测试记录不作为本次发布数量。数据格式见 [目录数据](catalogs.md)。
