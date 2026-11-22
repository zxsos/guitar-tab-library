/**
 * Cloudflare Worker backend for zxsos/guitar-tab-library.
 * Accepts validated `score_data.py` submissions from the web player and commits
 * `<artist>/<title>_<tierLabel>_<score>分.py` + updated `index.json` atomically.
 */

const TIER_LABELS = {
  beginner: "新手",
  standard: "标准",
  advanced: "进阶",
};

const MAX_BODY_BYTES = 204800; // 200 KB
const RATE_WINDOW_MS = 10 * 60 * 1000;
const RATE_MAX_REQS = 10;
const rateBuckets = new Map();

export function sanitizeSegment(raw, fieldName = "名称") {
  const s = String(raw ?? "").trim();
  if (!s) {
    throw new ValidationError(`${fieldName}不能为空`);
  }
  if (s.includes("..") || s.includes("/") || s.includes("\\")) {
    throw new ValidationError(`${fieldName}不能包含路径字符 / \\ 或 ..`);
  }
  let clean = s
    .replace(/[\u0000-\u001f\u007f]/g, "")
    .replace(/[:*?"<>|]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/^[._-]+|[._-]+$/g, "");
  if (clean.length > 60) {
    clean = clean.slice(0, 60).replace(/[._-]+$/g, "");
  }
  if (!clean) {
    throw new ValidationError(`${fieldName}包含过多非法字符`);
  }
  return clean;
}

export function buildScorePath(artist, title, tier, score) {
  const tierLabel = TIER_LABELS[tier];
  if (!tierLabel) {
    throw new ValidationError(`无效难度档位 '${tier}'，仅支持 beginner / standard / advanced`);
  }
  const intScore = Math.round(Number(score));
  if (!Number.isFinite(intScore) || intScore < 0 || intScore > 100) {
    throw new ValidationError(`无效分数 '${score}'，必须在 0..100 之间`);
  }
  const safeArtist = sanitizeSegment(artist, "歌手目录");
  const safeTitle = sanitizeSegment(title, "曲目名称");
  const relPath = `scores/${safeArtist}/${safeTitle}_${tierLabel}_${intScore}分.py`;
  if (!/^scores\/[^/]+\/[^/]+\.py$/.test(relPath)) {
    throw new ValidationError("生成的保存路径不合法");
  }
  return {
    relPath,
    safeArtist,
    safeTitle,
    tierLabel,
    intScore,
  };
}

const LEAK_REGEX = /(textedit:\/\/|\/home\/|\/Users\/|C:\\Users\\)/i;
const UNSAFE_PY_REGEX = /(\bos\.system\b|\bsubprocess\b|\bsocket\b|\burllib\b|\brequests\b|\bshutil\.rmtree\b|\b__import__\b|\b(?:eval|exec|open)\s*\()/i;

export function validatePythonSource(code) {
  const text = String(code ?? "").replace(/\r\n/g, "\n").trimEnd();
  if (!text) {
    throw new ValidationError("源码 score_data.py 不能为空");
  }
  const bytes = new TextEncoder().encode(text + "\n");
  if (bytes.byteLength > MAX_BODY_BYTES) {
    throw new ValidationError("源码体积超过 200 KB 上限");
  }
  if (!text.includes("def build_measures") || !text.includes("Measure(") || !text.includes("ev(")) {
    throw new ValidationError("源码缺少必要的 fingerstyle score_data.py 结构（def build_measures / Measure / ev）");
  }
  if (LEAK_REGEX.test(text)) {
    throw new ValidationError("源码包含未脱敏的本地路径或 textedit:// 链接，已拦截保存");
  }
  if (UNSAFE_PY_REGEX.test(text)) {
    throw new ValidationError("源码包含非乐谱数据类的系统/网络调用，已安全拦截");
  }
  return text + "\n";
}

export function validateSubmission(payload) {
  if (!payload || typeof payload !== "object") {
    throw new ValidationError("请求体必须是 JSON 对象");
  }
  const pathInfo = buildScorePath(payload.artist, payload.title, payload.tier, payload.score);
  const normalizedCode = validatePythonSource(payload.code);
  const autoScoreRaw = Number(payload.autoScore);
  const autoScore = Number.isFinite(autoScoreRaw)
    ? Math.max(0, Math.min(100, Math.round(autoScoreRaw)))
    : pathInfo.intScore;
  const toPosInt = (v) => (Number.isFinite(Number(v)) && Number(v) >= 0 ? Math.round(Number(v)) : 0);

  return {
    ...pathInfo,
    tier: payload.tier,
    autoScore,
    bpm: toPosInt(payload.bpm),
    capo: toPosInt(payload.capo),
    bars: toPosInt(payload.bars),
    notes: toPosInt(payload.notes),
    code: normalizedCode,
  };
}

class ValidationError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function corsHeadersFor(request, env) {
  const origin = request.headers.get("Origin") || "";
  const allowed = String(env.ALLOWED_ORIGINS || "https://zxsos.github.io")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  let allowOrigin = allowed[0] || "*";
  if (allowed.includes("*")) {
    allowOrigin = "*";
  } else if (origin && allowed.includes(origin)) {
    allowOrigin = origin;
  }
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

function jsonResponse(data, status, corsHeaders) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...corsHeaders,
    },
  });
}

function checkRateLimit(request) {
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "local";
  const now = Date.now();
  const recent = (rateBuckets.get(ip) || []).filter((ts) => now - ts < RATE_WINDOW_MS);
  if (recent.length >= RATE_MAX_REQS) {
    return false;
  }
  recent.push(now);
  rateBuckets.set(ip, recent);
  return true;
}

function decodeBase64Utf8(b64) {
  const bin = atob(String(b64 || "").replace(/\s+/g, ""));
  const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

async function ghApi(fetchFn, token, path, method = "GET", body = undefined) {
  const url = `https://api.github.com${path}`;
  const headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "guitar-tab-library-worker/1.0",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const resp = await fetchFn(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await resp.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = { message: text };
  }
  return { ok: resp.ok, status: resp.status, data: json };
}

export async function handleRequest(request, env = {}) {
  const cors = corsHeadersFor(request, env);
  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }

  const url = new URL(request.url);
  const owner = env.GITHUB_OWNER || "zxsos";
  const repo = env.GITHUB_REPO || "guitar-tab-library";
  const branch = env.GITHUB_BRANCH || "main";
  const commitMode = (env.COMMIT_MODE || "direct").toLowerCase();
  const fetchFn = env._fetch || globalThis.fetch;

  if (request.method === "GET" && url.pathname === "/health") {
    return jsonResponse(
      { ok: true, repo: `${owner}/${repo}`, branch, commitMode, configured: Boolean(env.GITHUB_TOKEN) },
      200,
      cors
    );
  }

  if (request.method === "GET" && url.pathname === "/catalog") {
    if (env.GITHUB_TOKEN) {
      const res = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/contents/index.json?ref=${encodeURIComponent(branch)}`);
      if (res.ok && res.data?.content) {
        const parsed = JSON.parse(decodeBase64Utf8(res.data.content));
        return jsonResponse(parsed, 200, cors);
      }
    }
    const rawUrl = `https://raw.githubusercontent.com/${owner}/${repo}/${encodeURIComponent(branch)}/index.json`;
    const rawResp = await fetchFn(rawUrl, { headers: { "User-Agent": "guitar-tab-library-worker/1.0" } });
    if (!rawResp.ok) {
      return jsonResponse({ ok: false, error: `无法读取谱库索引 (${rawResp.status})` }, rawResp.status, cors);
    }
    const parsed = await rawResp.json();
    return jsonResponse(parsed, 200, cors);
  }

  if (request.method === "POST" && url.pathname === "/submit") {
    if (!env.GITHUB_TOKEN) {
      return jsonResponse(
        { ok: false, error: "服务端尚未配置 GITHUB_TOKEN Secret，请先按 worker/README.md 部署" },
        503,
        cors
      );
    }
    if (!env._skipRateLimit && !checkRateLimit(request)) {
      return jsonResponse({ ok: false, error: "请求过于频繁，请几分钟后再试" }, 429, cors);
    }

    const contentLen = Number(request.headers.get("Content-Length") || 0);
    if (contentLen > MAX_BODY_BYTES + 16384) {
      return jsonResponse({ ok: false, error: "请求体过大" }, 413, cors);
    }

    let rawBody;
    try {
      rawBody = await request.text();
      if (rawBody.length > MAX_BODY_BYTES + 16384) {
        return jsonResponse({ ok: false, error: "请求体超过大小限制" }, 413, cors);
      }
    } catch {
      return jsonResponse({ ok: false, error: "无法读取请求内容" }, 400, cors);
    }

    let payload;
    try {
      payload = JSON.parse(rawBody);
    } catch {
      return jsonResponse({ ok: false, error: "请求体 JSON 格式无效" }, 400, cors);
    }

    let sub;
    try {
      sub = validateSubmission(payload);
    } catch (err) {
      return jsonResponse({ ok: false, error: err.message }, err.status || 400, cors);
    }

    const hash = await sha256Hex(sub.code);
    const encBranch = encodeURIComponent(branch);

    // 1. Read HEAD ref & commit tree
    const refRes = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/ref/heads/${encBranch}`);
    if (!refRes.ok) {
      return jsonResponse({ ok: false, error: `读取仓库分支失败 (${refRes.status}): ${refRes.data?.message || ""}` }, 502, cors);
    }
    const headSha = refRes.data.object.sha;

    const commitRes = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/commits/${headSha}`);
    if (!commitRes.ok) {
      return jsonResponse({ ok: false, error: "读取基准提交失败" }, 502, cors);
    }
    const baseTreeSha = commitRes.data.tree.sha;

    // 2. Read current index.json for dedup & update
    let catalog = { version: 1, updatedAt: new Date().toISOString(), items: [] };
    const idxRes = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/contents/index.json?ref=${encBranch}`);
    if (idxRes.ok && idxRes.data?.content) {
      try {
        const parsed = JSON.parse(decodeBase64Utf8(idxRes.data.content));
        if (parsed && Array.isArray(parsed.items)) catalog = parsed;
      } catch {
        // Keep clean fallback catalog if malformed
      }
    }

    const dup = catalog.items.find(
      (it) =>
        it.sha256 === hash &&
        it.artist === sub.safeArtist &&
        it.title === sub.safeTitle &&
        it.tier === sub.tier
    );
    const encodedPath = sub.relPath.split("/").map(encodeURIComponent).join("/");
    const repoHtmlBase = `https://github.com/${owner}/${repo}`;
    if (dup) {
      const dupUrl = `${repoHtmlBase}/blob/${branch}/${dup.path.split("/").map(encodeURIComponent).join("/")}`;
      return jsonResponse(
        {
          ok: true,
          status: "duplicate",
          path: dup.path,
          sha256: hash,
          htmlUrl: dupUrl,
          message: "云端谱库已收录完全相同的源码，无需重复提交",
        },
        200,
        cors
      );
    }

    const nowIso = new Date().toISOString();
    const newItem = {
      path: sub.relPath,
      artist: sub.safeArtist,
      title: sub.safeTitle,
      tier: sub.tier,
      tierLabel: sub.tierLabel,
      score: sub.intScore,
      autoScore: sub.autoScore,
      bpm: sub.bpm,
      capo: sub.capo,
      bars: sub.bars,
      notes: sub.notes,
      sha256: hash,
      updatedAt: nowIso,
    };
    const filtered = catalog.items.filter((it) => it.path !== sub.relPath);
    const updatedCatalog = {
      version: 1,
      updatedAt: nowIso,
      items: [newItem, ...filtered],
    };
    const catalogStr = JSON.stringify(updatedCatalog, null, 2) + "\n";

    // 3. Create blobs + tree + commit atomically
    const codeBlob = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/blobs`, "POST", {
      content: sub.code,
      encoding: "utf-8",
    });
    const idxBlob = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/blobs`, "POST", {
      content: catalogStr,
      encoding: "utf-8",
    });
    if (!codeBlob.ok || !idxBlob.ok) {
      return jsonResponse({ ok: false, error: "创建 Git 文件对象失败" }, 502, cors);
    }

    const treeRes = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/trees`, "POST", {
      base_tree: baseTreeSha,
      tree: [
        { path: sub.relPath, mode: "100644", type: "blob", sha: codeBlob.data.sha },
        { path: "index.json", mode: "100644", type: "blob", sha: idxBlob.data.sha },
      ],
    });
    if (!treeRes.ok) {
      return jsonResponse({ ok: false, error: `创建 Git Tree 失败: ${treeRes.data?.message || ""}` }, 502, cors);
    }

    const commitMsg = `Add ${sub.safeArtist}/${sub.safeTitle} (${sub.tierLabel}, ${sub.intScore}分)`;
    const newCommit = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/commits`, "POST", {
      message: commitMsg,
      tree: treeRes.data.sha,
      parents: [headSha],
    });
    if (!newCommit.ok) {
      return jsonResponse({ ok: false, error: "创建 Git Commit 失败" }, 502, cors);
    }
    const newCommitSha = newCommit.data.sha;

    if (commitMode === "pr") {
      const prBranch = `submit/${Date.now()}-${hash.slice(0, 8)}`;
      const mkBranch = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/refs`, "POST", {
        ref: `refs/heads/${prBranch}`,
        sha: newCommitSha,
      });
      if (!mkBranch.ok) {
        return jsonResponse({ ok: false, error: "创建投稿分支失败" }, 502, cors);
      }
      const prRes = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/pulls`, "POST", {
        title: commitMsg,
        head: prBranch,
        base: branch,
        body: `来自练习播放器的自动化谱库提交：\n- 文件：\`${sub.relPath}\`\n- 难度：${sub.tierLabel}\n- 评分：${sub.intScore} 分（自动建议 ${sub.autoScore} 分）\n- SHA-256：\`${hash}\``,
      });
      if (!prRes.ok) {
        return jsonResponse({ ok: false, error: "创建 Pull Request 失败" }, 502, cors);
      }
      return jsonResponse(
        {
          ok: true,
          status: "pr_created",
          path: sub.relPath,
          commitSha: newCommitSha,
          htmlUrl: `${repoHtmlBase}/blob/${prBranch}/${encodedPath}`,
          prUrl: prRes.data.html_url,
          sha256: hash,
        },
        200,
        cors
      );
    }

    const updRef = await ghApi(fetchFn, env.GITHUB_TOKEN, `/repos/${owner}/${repo}/git/refs/heads/${encBranch}`, "PATCH", {
      sha: newCommitSha,
      force: false,
    });
    if (!updRef.ok) {
      return jsonResponse({ ok: false, error: `推送主分支失败 (${updRef.status}): ${updRef.data?.message || ""}` }, 502, cors);
    }

    return jsonResponse(
      {
        ok: true,
        status: "saved",
        path: sub.relPath,
        commitSha: newCommitSha,
        htmlUrl: `${repoHtmlBase}/blob/${branch}/${encodedPath}`,
        sha256: hash,
      },
      200,
      cors
    );
  }

  return jsonResponse({ ok: false, error: "Not Found" }, 404, cors);
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
};
