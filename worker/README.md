# 部署 Cloudflare Worker（让任何访客上传都能自动存库）

只需一次性执行 3 步（完全免费额度，约 2 分钟）：

### 第 1 步：生成最小权限的 GitHub Token
1. 打开 GitHub **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**。
2. **Repository access** 选 **Only select repositories** → 只勾选 **`zxsos/guitar-tab-library`**。
3. **Permissions → Repository permissions** 只开：
   - **Contents**: `Read and write`
   - （可选，仅当你把 `COMMIT_MODE` 改成 `"pr"` 时需要）**Pull requests**: `Read and write`
4. 复制生成的 Token。

### 第 2 步：登录 Cloudflare 并写入密钥
在 `worker/` 目录下执行：

```bash
npx wrangler login
npx wrangler secret put GITHUB_TOKEN   # 粘贴第 1 步的 Token
```

### 第 3 步：部署并绑定到播放器

```bash
npx wrangler deploy
```

部署完成后终端会打印你的 Worker 地址（例如 `https://guitar-tab-library-worker.<你的子域>.workers.dev`）：
- 在练习播放器导入弹窗的「接口设置」里填入该地址（立即生效）；
- 或者把该地址写进 `guitar-tab-player/index.html` 的 `DEFAULT_LIBRARY_WORKER_URL` 并推送，所有访客即可免配置直接使用。
