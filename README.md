# Guitar TAB Score Library

纯 GitHub 驱动的指弹吉他源码库与自动编译发布中心，配套 [在线指弹练习播放器](https://zxsos.github.io/guitar-tab-player/) 与 [fingerstyle-guitar-tab-skill](https://github.com/zxsos/fingerstyle-guitar-tab-skill)。

访客打开网页播放器即可 **免账号直接浏览「在线曲库」、按歌手听歌看谱、2D/3D 跟练与下载 PDF**；创作者或维护者只需将 `score_data.py`（或 `.mid` / `.musicxml` / `.mxl`）提交 **Pull Request**，GitHub Actions 会在云端自动完成质检、编译与上架。

---

## 目录规范

```text
scores/
  <歌手>/
    <曲名>_<档位>.py             # 唯一源码（纯 Python 数据文件，体积 <= 200 KB）
inbox/
  <歌手>/                        # 可选：直接 PR 投递 .mid / .musicxml / .mxl 待转源码
scripts/
  build_library.py               # 零外部依赖的静态安全门禁、增量编译与 Pages 打包脚本
.github/workflows/
  pr-check.yml                   # PR 自动安全校验、试编 PDF/PNG/MP3 并回复质检报告
  publish-library.yml            # 合并 main 后增量编译，刷新 index.json 并部署同域 Pages
index.json                       # 轻量索引（由 publish-library.yml 自动维护）
```

---

## 工作流全貌（100% 纯 GitHub，零外置服务器）

1. **导入练琴包一键去 GitHub 提 PR**：
   - 在 [练习播放器](https://zxsos.github.io/guitar-tab-player/) 拖入包含 `score_data.py` 的 `.zip` 练习包后，系统会在浏览器本地自动解析把位/声部信息并对比 `index.json` 预判重；
   - 未收录时点击 **「复制源码并去 GitHub 提 PR」**，自动复制标准化源码并打开 GitHub 新建文件页，选 *Create a new branch and start a pull request* 即可发起 PR（若你是仓库管理员，也可直接 Commit 到 `main`）；
   - 你也可以直接在 GitHub 本仓库 `scores/<歌手>/` 或 `inbox/<歌手>/` 上传文件发起 PR。
2. **PR 自动质检与云端试编（`pr-check.yml`）**：
   - 仅持只读权限，运行静态 AST 与正则安全检查（禁止系统/网络/动态执行与本地路径泄露）；
   - 云端调用 `tab_engine.py build` 编译出六线谱 PDF、高清 PNG 谱页、320 kbps MP3、`sync_manifest.json` 与 `*_bundle.zip`，并在 PR 评论区回复质检摘要。
3. **合并即上架（`publish-library.yml`）**：
   - 点击 **Merge** 后按 `SHA-256` 增量缓存只编译新曲目，刷新 `index.json`，并自动发布到同域静态产物站 `https://zxsos.github.io/guitar-tab-library/`（`catalog.json`）；
   - 播放器顶部 **「在线曲库」** 会立即同步收录新歌。
