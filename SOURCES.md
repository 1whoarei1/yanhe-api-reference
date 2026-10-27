# 来源与致谢

本目录整理原始 HTTP 接口、字段含义及多个客户端的行为差异。参考项目的代码及许可独立保留；本目录没有复制或分发它们的实现模块。

| 来源 | 本次使用的修订 / 材料 | 作用 | 许可说明 |
| --- | --- | --- | --- |
| [windlandneko/yanhekit](https://github.com/windlandneko/yanhekit) | `cb270ee0aa037400bc7d92bbb518392b804d6513` | 新版认证、8 个共用 HTTP 接口、签名、下载环境、字幕、工作区及外部转录服务对照 | [AGPL-3.0 LICENSE](https://github.com/windlandneko/yanhekit/blob/cb270ee0aa037400bc7d92bbb518392b804d6513/LICENSE)；未纳入 Python 或技能源码 |
| [1whoarei1/yanhe-refine](https://github.com/1whoarei1/yanhe-refine) | `8a292f47d7f25a697d01c9bd7c69189ce2edbf5a`，0.9.3 | 新旧延河、直播、资料、新旧乐学和上传 / 提交的客户端契约与已有验证范围 | [MIT LICENSE](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/LICENSE)；本目录使用源码作为证据 |
| [1whoarei1/yanhe-replay](https://github.com/1whoarei1/yanhe-replay) | 通过上述 Refine 内嵌播放器的固定快照核对 | 回放 / 直播、字幕和媒体协议参考 | 组件来源见 Refine 的第三方说明 |
| [lankerr/BIT_yanhe_download_2026](https://github.com/lankerr/BIT_yanhe_download_2026) 与 [BITNP/BIT_yanhe_download](https://github.com/BITNP/BIT_yanhe_download) | 通过 Refine 的固定实现和归属说明间接核对，本次未重新克隆或审计其当前主分支 | 旧站请求头、播放路径及短期播放凭据的研究来源 | 参考快照保留 MIT 归属，见 [Refine notices](https://github.com/1whoarei1/yanhe-refine/blob/8a292f47d7f25a697d01c9bd7c69189ce2edbf5a/THIRD_PARTY_NOTICES.md) |
| [Moodle](https://github.com/moodle/moodle) | BIT 旧乐学页面结构及 Refine 的解析实现 | 课程概览 RPC、模块页面和文件链接的系统背景 | 未分发 Moodle 源码，也未把通用上游文档当作 BIT 部署已经启用全部能力的证据 |

感谢这些项目的作者和维护者公开工具与研究。若以后引入实际代码，需单独记录具体文件、修订及许可证；接口资料的来源说明不代替代码分发时的归属与许可处理。
