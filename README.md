# Guitar TAB Score Library

收录由 [fingerstyle-guitar-tab-skill](https://github.com/zxsos/fingerstyle-guitar-tab-skill) 编配与验证的指弹吉他唯一源码 `score_data.py`，配合 [在线练习播放器](https://zxsos.github.io/guitar-tab-player/) 使用：上传包含源码的乐谱包时，可自动评分并按**歌手目录**直接保存至本仓库。

## 目录规范

```text
scores/
  <歌手>/
    <歌名>_<难度>_<分数>分.py
index.json
worker/
```

- 难度标签：`新手`（`beginner`）、`标准`（`standard`）、`进阶`（`advanced`）
- 质量评分：`0–100分`（由浏览器端按结构完整度、声部与品格合规度、编配细节、同步清单四项自动计算并支持保存前手动确认）
- 每份 `.py` 均可搭配 `tab_engine.py build` 重新导出六线谱 PDF、320 kbps 试听 MP3、同步清单与 `.zip` 练习包。

## 部署自动保存后端（Cloudflare Worker）

详见 [worker/README.md](worker/README.md)，3 步即可免费启用“任何访客上传自动保存”。
