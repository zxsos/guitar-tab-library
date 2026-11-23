const MAX_PY_BYTES = 204_800;
const TIER_LABELS = { beginner: "新手", standard: "标准", advanced: "进阶" };
const SAFE_IMPORTS = new Set(["__future__", "dataclasses", "typing", "math", "enum"]);
const LEAK_RE = /(textedit:\/\/|\/home\/|\/Users\/|C:\\Users\\)/i;
const UNSAFE_RE =
  /(\bos\.system\b|\bsubprocess\b|\bsocket\b|\burllib\b|\brequests\b|\bshutil\.rmtree\b|\b__import__\b|\b__subclasses__\b|\b__globals__\b|\b__builtins__\b|\b__code__\b|\b(?:eval|exec|open|compile|getattr|setattr|delattr|globals|locals|vars|input|breakpoint)\s*\()/i;

const RATE_WINDOW_MS = 10 * 60 * 1000;
const RATE_MAX_REQ = 6;
const RATE_MIN_GAP_MS = 10 * 1000;
const ipHits = new Map();

export function sanitizeSegment(raw, fallback = "Untitled") {
  let s = String(raw || "").trim();
  if (s.includes("..") || s.includes("/") || s.includes("\\")) {
    s = s.replace(/[\\/]+/g, "_").replace(/\.\./g, "");
  }
  s = s.replace(/[\u0000-\u001f\u007f]/g, "");
  s = s.replace(/[:*?"<>|]/g, "_");
  s = s.replace(/\s+/g, "_");
  s = s.replace(/^[._-]+|[._-]+$/g, "");
  if (s.length > 60) s = s.slice(0, 60).replace(/[._-]+$/g, "");
  return s || fallback;
}

export function normalizePy(code) {
  return String(code ?? "").replace(/\r\n/g, "\n").trimEnd() + "\n";
}

export function validateScorePy(code) {
  const norm = normalizePy(code);
  const byteLen = new TextEncoder().encode(norm).length;
  if (!norm.trim()) return { ok: false, error: "源码为空" };
  if (byteLen > MAX_PY_BYTES) return { ok: false, error: "源码超过 200 KB 上限" };
  if (LEAK_RE.test(norm)) return { ok: false, error: "包含本地路径或未脱敏链接" };
  if (!norm.includes("def build_measures") || !norm.includes("Measure(") || !norm.includes("ev(")) {
    return { ok: false, error: "缺少 score_data.py 必要结构" };
  }
  if (UNSAFE_RE.test(norm)) return { ok: false, error: "包含不允许的 Python 调用" };

  for (const line of norm.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const mFrom = trimmed.match(/^from\s+([A-Za-z0-9_.]+)\s+import\b/);
    if (mFrom) {
      const top = mFrom[1].split(".")[0];
      if (!SAFE_IMPORTS.has(top)) return { ok: false, error: `禁止导入模块: ${top}` };
    }
    const mImp = trimmed.match(/^import\s+([A-Za-z0-9_.,\s]+)/);
    if (mImp) {
      for (const part of mImp[1].split(",")) {
        const top = part.trim().split(/\s+/)[0].split(".")[0];
        if (top && !SAFE_IMPORTS.has(top)) return { ok: false, error: `禁止导入模块: ${top}` };
      }
    }
  }
  return { ok: true, norm };
}

export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function encodeBase64Utf8(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function decodeBase64Utf8(b64) {
  const bin = atob(String(b64 || "").replace(/\s+/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

function encodePath(p) {
  return p.split("/").map(encodeURIComponent).join("/");
}

function isOriginAllowed(origin, env) {
  if (!origin) return false;
  const allowRaw = (env.ALLOWED_ORIGINS || "https://zxsos.github.io").split(",").map((s) => s.trim()).filter(Boolean);
  if (allowRaw.includes(origin)) return true;
  if (/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(origin)) return true;
  return false;
}

function corsHeaders(origin, env) {
  const h = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
  if (isOriginAllowed(origin, env)) {
    h["Access-Control-Allow-Origin"] = origin;
  }
  return h;
}

function jsonResp(data, status, origin, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(origin, env) },
  });
}

function checkRateLimit(ip, now = Date.now()) {
  if (!ip) return { ok: true };
  const prev = (ipHits.get(ip) || []).filter((t) => now - t < RATE_WINDOW_MS);
  if (prev.length && now - prev[prev.length - 1] < RATE_MIN_GAP_MS) {
    ipHits.set(ip, prev);
    return { ok: false, error: "提交过于频繁，请稍后再试" };
  }
  if (prev.length >= RATE_MAX_REQ) {
    ipHits.set(ip, prev);
    return { ok: false, error: "短时间内提交次数过多，请 10 分钟后再试" };
  }
  prev.push(now);
  ipHits.set(ip, prev);
  if (ipHits.size > 500) {
    for (const [k, v] of ipHits.entries()) {
      if (!v.some((t) => now - t < RATE_WINDOW_MS)) ipHits.delete(k);
    }
  }
  return { ok: true };
}

async function ghApi(env, path, { method = "GET", body } = {}) {
  const url = `https://api.github.com${path}`;
  const resp = await fetch(url, {
    method,
    headers: {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "guitar-tab-library-relay/1.0",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await resp.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* non-json */ }
  return { ok: resp.ok, status: resp.status, data: json, text };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    const owner = env.GITHUB_OWNER || "zxsos";
    const repo = env.GITHUB_REPO || "guitar-tab-library";
    const branch = env.GITHUB_BRANCH || "main";

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin, env) });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResp(
        { ok: true, repo: `${owner}/${repo}`, branch, mode: "pr", configured: Boolean(env.GITHUB_TOKEN) },
        200,
        origin,
        env
      );
    }

    if (request.method !== "POST" || url.pathname !== "/submit") {
      return jsonResp({ ok: false, error: "Not Found" }, 404, origin, env);
    }

    if (origin && !isOriginAllowed(origin, env)) {
      return jsonResp({ ok: false, error: "Origin not allowed" }, 403, origin, env);
    }

    if (!env.GITHUB_TOKEN) {
      return jsonResp({ ok: false, error: "中转服务尚未配置 GITHUB_TOKEN" }, 503, origin, env);
    }

    const ip = request.headers.get("CF-Connecting-IP") || "";
    const rl = checkRateLimit(ip);
    if (!rl.ok) {
      return jsonResp({ ok: false, error: rl.error }, 429, origin, env);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return jsonResp({ ok: false, error: "无效的 JSON 请求体" }, 400, origin, env);
    }

    const check = validateScorePy(payload && payload.code);
    if (!check.ok) {
      return jsonResp({ ok: false, error: check.error }, 400, origin, env);
    }

    const artist = sanitizeSegment(payload.artist, "未分类");
    const title = sanitizeSegment(payload.title, "Untitled");
    const tier = TIER_LABELS[payload.tier] ? payload.tier : "standard";
    const tierLabel = TIER_LABELS[tier];
    const relPath = `scores/${artist}/${title}_${tierLabel}.py`;
    const hash = await sha256Hex(check.norm);
    const shortHash = hash.slice(0, 10);
    const prBranch = `submit/${shortHash}`;

    // 1. Check exact file on main for dedup
    let existingFileSha = null;
    const existing = await ghApi(env, `/repos/${owner}/${repo}/contents/${encodePath(relPath)}?ref=${encodeURIComponent(branch)}`);
    if (existing.ok && existing.data && existing.data.content) {
      existingFileSha = existing.data.sha || null;
      try {
        const curNorm = normalizePy(decodeBase64Utf8(existing.data.content));
        if ((await sha256Hex(curNorm)) === hash) {
          return jsonResp(
            {
              ok: true,
              status: "duplicate",
              path: relPath,
              url: existing.data.html_url || `https://github.com/${owner}/${repo}/blob/${branch}/${encodePath(relPath)}`,
            },
            200,
            origin,
            env
          );
        }
      } catch {
        // Ignore decode failure and continue
      }
    }

    // 2. Check index.json on main for hash dedup across paths
    const idxRes = await ghApi(env, `/repos/${owner}/${repo}/contents/index.json?ref=${encodeURIComponent(branch)}`);
    if (idxRes.ok && idxRes.data && idxRes.data.content) {
      try {
        const idxJson = JSON.parse(decodeBase64Utf8(idxRes.data.content));
        const dup = (idxJson.items || []).find((it) => it && it.sha256 === hash);
        if (dup) {
          return jsonResp(
            {
              ok: true,
              status: "duplicate",
              path: dup.path || relPath,
              url: `https://github.com/${owner}/${repo}/blob/${branch}/${encodePath(dup.path || relPath)}`,
            },
            200,
            origin,
            env
          );
        }
      } catch {
        // Ignore index parse errors
      }
    }

    // 3. Check if an open PR for this exact hash already exists
    const openPrs = await ghApi(
      env,
      `/repos/${owner}/${repo}/pulls?state=open&head=${encodeURIComponent(`${owner}:${prBranch}`)}`
    );
    if (openPrs.ok && Array.isArray(openPrs.data) && openPrs.data.length > 0) {
      const pr = openPrs.data[0];
      return jsonResp(
        { ok: true, status: "pr_exists", path: relPath, prNumber: pr.number, prUrl: pr.html_url },
        200,
        origin,
        env
      );
    }

    // 4. Create branch from main HEAD
    const refRes = await ghApi(env, `/repos/${owner}/${repo}/git/ref/heads/${encodeURIComponent(branch)}`);
    if (!refRes.ok || !refRes.data || !refRes.data.object) {
      return jsonResp({ ok: false, error: `读取主分支失败 (${refRes.status})` }, 502, origin, env);
    }
    const baseSha = refRes.data.object.sha;

    const mkRef = await ghApi(env, `/repos/${owner}/${repo}/git/refs`, {
      method: "POST",
      body: { ref: `refs/heads/${prBranch}`, sha: baseSha },
    });
    if (!mkRef.ok && mkRef.status !== 422) {
      return jsonResp({ ok: false, error: `创建提交分支失败 (${mkRef.status})` }, 502, origin, env);
    }

    // Check if file already exists on prBranch (e.g. retried submission)
    let branchFileSha = existingFileSha;
    if (mkRef.status === 422) {
      const bf = await ghApi(env, `/repos/${owner}/${repo}/contents/${encodePath(relPath)}?ref=${encodeURIComponent(prBranch)}`);
      if (bf.ok && bf.data && bf.data.sha) branchFileSha = bf.data.sha;
    }

    // 5. Commit normalized score_data.py onto prBranch
    const commitMsg = `Add ${artist} - ${title} (${tierLabel})`;
    const putBody = {
      message: commitMsg,
      content: encodeBase64Utf8(check.norm),
      branch: prBranch,
      ...(branchFileSha ? { sha: branchFileSha } : {}),
    };
    const putRes = await ghApi(env, `/repos/${owner}/${repo}/contents/${encodePath(relPath)}`, {
      method: "PUT",
      body: putBody,
    });
    if (!putRes.ok) {
      return jsonResp(
        { ok: false, error: `写入曲谱文件失败 (${putRes.status}: ${(putRes.data && putRes.data.message) || "unknown"})` },
        502,
        origin,
        env
      );
    }

    // 6. Open PR
    const scoreLine = Number.isFinite(Number(payload.qualityScore)) ? `${Math.round(Number(payload.qualityScore))}分` : "-";
    const diffLine = Number.isFinite(Number(payload.difficulty)) ? `Lv.${Number(payload.difficulty).toFixed(1)}` : "-";
    const prBody = [
      "由在线指弹播放器访客导入自动提交：",
      "",
      `- **路径**：\`${relPath}\``,
      `- **歌手 / 曲目**：${artist} - ${title}（${tierLabel}）`,
      `- **客户端预检**：${scoreLine} · ${diffLine}`,
      `- **SHA-256**：\`${hash}\``,
    ].join("\n");

    const prRes = await ghApi(env, `/repos/${owner}/${repo}/pulls`, {
      method: "POST",
      body: { title: commitMsg, head: prBranch, base: branch, body: prBody },
    });
    if (!prRes.ok || !prRes.data) {
      return jsonResp(
        { ok: false, error: `创建 PR 失败 (${prRes.status}: ${(prRes.data && prRes.data.message) || "unknown"})` },
        502,
        origin,
        env
      );
    }

    return jsonResp(
      { ok: true, status: "pr_created", path: relPath, prNumber: prRes.data.number, prUrl: prRes.data.html_url },
      201,
      origin,
      env
    );
  },
};
