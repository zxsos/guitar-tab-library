import assert from "node:assert/strict";
import fs from "node:fs";
import worker, { validateScorePy, sanitizeSegment } from "./src/index.js";

// 1. Validate real score passes
const realPy = fs.readFileSync(new URL("../scores/泽野弘之/Call_of_Silence_标准.py", import.meta.url), "utf8");
const okRes = validateScorePy(realPy);
assert.equal(okRes.ok, true);

// 2. Reject unsafe imports & path leaks
assert.equal(validateScorePy("import os\ndef build_measures(): Measure(); ev()").ok, false);
assert.equal(validateScorePy("# /home/user/a.py\ndef build_measures(): Measure(); ev()").ok, false);
assert.equal(validateScorePy("def build_measures(): eval('1'); Measure(); ev()").ok, false);

// 3. Sanitize path segments
assert.equal(sanitizeSegment("../周杰伦/晴天"), "周杰伦_晴天");
assert.equal(sanitizeSegment("   ", "未分类"), "未分类");

// 4. Health & CORS preflight
const env = { ALLOWED_ORIGINS: "https://zxsos.github.io" };
const hResp = await worker.fetch(new Request("https://relay.test/health", { headers: { Origin: "https://zxsos.github.io" } }), env);
assert.equal(hResp.status, 200);
assert.equal(hResp.headers.get("Access-Control-Allow-Origin"), "https://zxsos.github.io");
const hBody = await hResp.json();
assert.equal(hBody.ok, true);
assert.equal(hBody.configured, false);

const optResp = await worker.fetch(new Request("https://relay.test/submit", { method: "OPTIONS", headers: { Origin: "https://zxsos.github.io" } }), env);
assert.equal(optResp.status, 204);

// 5. Reject foreign origin
const badOrigin = await worker.fetch(new Request("https://relay.test/submit", {
  method: "POST",
  headers: { Origin: "https://evil.example", "Content-Type": "application/json" },
  body: "{}",
}), env);
assert.equal(badOrigin.status, 403);

console.log("Worker unit tests: 5/5 PASS");
