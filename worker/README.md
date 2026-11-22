# 部署 Cloudflare Worker（已发布，仅差填入 GitHub Secret）

Worker 已部署上线至 Cloudflare 账号 **`zcsos`**：
- **线上接口**：`https://guitar-tab-library-worker.zcsos.workers.dev`
- **入库模式**：`COMMIT_MODE = "direct"`（直接提交写入 `zxsos/guitar-tab-library` 的 `main` 分支）
- **练习播放器**：已默认绑定上述地址

---

### 仅需 1 步私钥配置即可开启自动入库（2 分钟完成）

出于安全原因，写入 GitHub 仓库的 Token 不能放进聊天或公开源码里，请由你本人私密写入 Cloudflare Secret：

#### 1. 生成最小权限 GitHub Token
1. 打开 GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**。
2. **Repository access** 选 **Only select repositories** → 只勾选 **`zxsos/guitar-tab-library`**。
3. **Permissions → Repository permissions** 只将 **Contents** 设为 **`Read and write`**，生成并复制 Token。

#### 2. 写入 Cloudflare Secret（二选一）

**方式 A（网页端最省事）：**
1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/) → 右上角切换到 **`zcsos`** 账号。
2. 进入 **Workers & Pages → `guitar-tab-library-worker` → Settings → Variables and Secrets**。
3. 点 **Add → Secret**：Name 填 `GITHUB_TOKEN`，Value 粘贴刚才的 Token，点击 **Deploy**。

**方式 B（本地终端命令行）：**
```bash
cd /path/to/guitar-tab-library/worker
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
```

配置完成后访问 `https://guitar-tab-library-worker.zcsos.workers.dev/health`，看到 `"configured": true` 即表示所有访客上传都会自动分类存库。
