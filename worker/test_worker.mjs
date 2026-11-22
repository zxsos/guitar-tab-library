import assert from "node:assert/strict";
import { handleRequest } from "./src/index.js";

function makeMockGitHubFetch({ seedCatalog = { version: 1, updatedAt: "2026-01-01T00:00:00.000Z", items: [] } } = {}) {
  const calls = [];
  let headSha = "deadbeef0000";
  let treeSha = "tree0000";
  let blobIdx = 0;
  const blobs = new Map();
  let lastTree = null;
  let lastCommit = null;

  const fetchFn = async (url, init = {}) => {
    const u = new URL(url);
    const method = (init.method || "GET").toUpperCase();
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ method, path: u.pathname, body });

    const jsonRes = (obj, status = 200) =>
      new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });

    if (method === "GET" && u.pathname.endsWith("/git/ref/heads/main")) {
      return jsonRes({ object: { sha: headSha } });
    }
    if (method === "GET" && u.pathname.includes("/git/commits/")) {
      return jsonRes({ sha: headSha, tree: { sha: treeSha } });
    }
    if (method === "GET" && u.pathname.endsWith("/contents/index.json")) {
      const b64 = Buffer.from(JSON.stringify(seedCatalog), "utf8").toString("base64");
      return jsonRes({ content: b64, encoding: "base64" });
    }
    if (method === "POST" && u.pathname.endsWith("/git/blobs")) {
      const sha = `blob_${++blobIdx}`;
      blobs.set(sha, body.content);
      return jsonRes({ sha }, 201);
    }
    if (method === "POST" && u.pathname.endsWith("/git/trees")) {
      lastTree = body;
      treeSha = "tree_new_1";
      return jsonRes({ sha: treeSha }, 201);
    }
    if (method === "POST" && u.pathname.endsWith("/git/commits")) {
      lastCommit = body;
      headSha = "commit_new_1";
      return jsonRes({ sha: headSha }, 201);
    }
    if (method === "PATCH" && u.pathname.endsWith("/git/refs/heads/main")) {
      return jsonRes({ object: { sha: body.sha } });
    }
    return jsonRes({ message: `Unmocked ${method} ${u.pathname}` }, 404);
  };

  return { fetchFn, calls, getLastTree: () => lastTree, blobs };
}

const VALID_CODE = `TITLE = "一直很安静"
TEMPO_BPM = 76
CAPO = 3

def build_measures():
    return [Measure(bar=1, events=[ev(0, 16, n(3, 0, "melody"))])]
`;

async function runTests() {
  // 1. Valid submission -> atomic 2-file tree commit
  {
    const mock = makeMockGitHubFetch();
    const req = new Request("https://worker.example/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "https://zxsos.github.io" },
      body: JSON.stringify({
        artist: "阿桑",
        title: "一直很安静",
        tier: "standard",
        score: 94,
        autoScore: 94,
        bpm: 76,
        capo: 3,
        bars: 68,
        notes: 646,
        code: VALID_CODE,
      }),
    });
    const res = await handleRequest(req, { GITHUB_TOKEN: "ghp_test", _fetch: mock.fetchFn, _skipRateLimit: true });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.ok, true);
    assert.equal(data.status, "saved");
    assert.equal(data.path, "scores/阿桑/一直很安静_标准_94分.py");
    assert.ok(data.htmlUrl.includes("github.com/zxsos/guitar-tab-library/blob/main/scores/"));
    const tree = mock.getLastTree();
    assert.equal(tree.tree.length, 2);
    assert.equal(tree.tree[0].path, "scores/阿桑/一直很安静_标准_94分.py");
    assert.equal(tree.tree[1].path, "index.json");
    console.log("PASS 1: valid atomic commit ->", data.path);
  }

  // 2. Duplicate sha256 -> duplicate without commit
  {
    const hex = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(VALID_CODE));
    const sha256 = Array.from(new Uint8Array(hex), (b) => b.toString(16).padStart(2, "0")).join("");
    const mock = makeMockGitHubFetch({
      seedCatalog: {
        version: 1,
        items: [{ path: "scores/阿桑/一直很安静_标准_94分.py", artist: "阿桑", title: "一直很安静", tier: "standard", sha256 }],
      },
    });
    const req = new Request("https://worker.example/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artist: "阿桑", title: "一直很安静", tier: "standard", score: 94, code: VALID_CODE }),
    });
    const res = await handleRequest(req, { GITHUB_TOKEN: "ghp_test", _fetch: mock.fetchFn, _skipRateLimit: true });
    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.status, "duplicate");
    assert.equal(mock.calls.filter((c) => c.method === "POST").length, 0);
    console.log("PASS 2: duplicate sha256 detected cleanly (0 commits)");
  }

  // 3. Path traversal rejected 400
  for (const badArtist of ["../evil", "a/b"]) {
    const mock = makeMockGitHubFetch();
    const req = new Request("https://worker.example/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artist: badArtist, title: "Demo", tier: "beginner", score: 80, code: VALID_CODE }),
    });
    const res = await handleRequest(req, { GITHUB_TOKEN: "ghp_test", _fetch: mock.fetchFn, _skipRateLimit: true });
    assert.equal(res.status, 400);
  }
  console.log("PASS 3: path traversal ('../evil', 'a/b') rejected with 400");

  // 4. Unsafe Python & workstation path leak rejected 400
  for (const badCode of [
    VALID_CODE + "\nimport subprocess\n",
    VALID_CODE + "\nos.system('rm -rf /')\n",
    VALID_CODE + "\neval('1+1')\n",
    VALID_CODE + "\n# /home/alice/secret\n",
  ]) {
    const mock = makeMockGitHubFetch();
    const req = new Request("https://worker.example/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artist: "Test", title: "Demo", tier: "beginner", score: 80, code: badCode }),
    });
    const res = await handleRequest(req, { GITHUB_TOKEN: "ghp_test", _fetch: mock.fetchFn, _skipRateLimit: true });
    assert.equal(res.status, 400);
  }
  console.log("PASS 4: unsafe Python & workstation path leaks rejected with 400");

  // 5. Invalid tier or out-of-range score rejected 400
  for (const [tier, score] of [["expert", 90], ["standard", 105], ["beginner", -1]]) {
    const mock = makeMockGitHubFetch();
    const req = new Request("https://worker.example/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artist: "Test", title: "Demo", tier, score, code: VALID_CODE }),
    });
    const res = await handleRequest(req, { GITHUB_TOKEN: "ghp_test", _fetch: mock.fetchFn, _skipRateLimit: true });
    assert.equal(res.status, 400);
  }
  console.log("PASS 5: invalid tier / out-of-range score rejected with 400");
}

runTests().catch((err) => {
  console.error(err);
  process.exit(1);
});
