# Pure-GitHub 指弹谱库自动化工作流设计

## 背景与目标

访客在 [guitar-tab-player](https://zxsos.github.io/guitar-tab-player/) 网页播放器导入本地生成的练习压缩包（或手持 `score_data.py` / `.mid` / `.musicxml`）时，希望在不依赖任何 Cloudflare Worker、外置代理服务器或私密转发 Token 的前提下：

1. 将可复现唯一源码 `score_data.py` 按歌手分文件夹自动保存并向本仓库发起审核 PR；
2. 发起 PR 后由 GitHub Actions 自动执行安全检测、音乐与指法校验，并试编出 PDF、高清谱页 PNG、320 kbps MP3 及完整压缩包供审核；
3. 仓库维护者点击 **Merge** 合入 `main` 后，GitHub Actions 自动增量编译全库产物，刷新 `index.json` 与 `catalog.json`，并部署至同域 GitHub Pages（`https://zxsos.github.io/guitar-tab-library/`）；
4. 任何访客打开网页播放器即可直接浏览「在线曲库」，按歌手选歌、试听、看谱、2D/3D 练习与下载 PDF，无需登录 GitHub 账号。

## 架构概览

- **投递与审核入口（PR）**
  - 浏览器端保留 `score_data.py` 本地解析、SHA-256 预判重与把位/声部硬件信息提取（小节数、Capo、最高品格、声部交叉检查）。
  - 用户确认歌手、曲名与档位后，一键复制规范源码并跳转到 GitHub 原生新文件 PR 页面（`github.com/zxsos/guitar-tab-library/new/main?filename=scores/<歌手>/<曲名>_<档位>.py`）；贡献者亦可直接向 `scores/<歌手>/` 或 `inbox/<歌手>/` 提交 PR（支持 `.py` 及 `.mid`/`.musicxml`/`.mxl`）。
- **无权限 PR 试编门禁（`.github/workflows/pr-check.yml`）**
  - `build-and-verify` 任务仅持 `contents: read` 只读权限；
  - `scripts/build_library.py` 先在执行任何源码前跑静态安全门禁（限制 200 KB、拦截本地路径泄露、AST 与正则拦截系统/网络/动态执行模块），随后拉取 [fingerstyle-guitar-tab-skill](https://github.com/zxsos/fingerstyle-guitar-tab-skill) 引擎与 `lilypond`、`fluidsynth`、`ffmpeg`、`pdftoppm` 完成全套编译与四重质量校验；
  - 仅在 PR 分支下帖回中文质检汇总与试听产物包。PR 中不修改 `index.json`，避免多 PR 并发合并冲突。
- **合并即上架与增量发布（`.github/workflows/publish-library.yml`）**
  - 仅对合入 `main` 的已审核曲谱运行，按 `sha256[:16]` 缓存历史产物（`.build-cache`），只对新增或变更曲目调用 LilyPond / FluidSynth；
  - 生成静态站点 `_site/`（包含 `catalog.json`、`songs/<sha256[:12]>/` 下的 `sync_manifest.json`、MP3、PDF、PNG 谱页、`*_bundle.zip` 与 `score_data.py`），并自动刷新根目录下 `index.json`；
  - 部署至同域名 `https://zxsos.github.io/guitar-tab-library/`，网页播放器同域直连加载，完全免跨域、免后端服务器维护。
