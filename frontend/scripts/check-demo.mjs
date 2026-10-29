// Behavioral checks without adding a test framework: compile the real TS modules in memory.
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";

function moduleAt(path) {
  const context = vm.createContext({ exports: {}, process, AbortSignal, AbortController, Headers, TextDecoder, TypeError, Error,
    console: { error() {} }, fetch: async () => { throw new TypeError("offline"); } });
  const source = ts.transpileModule(fs.readFileSync(path, "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  vm.runInContext(source, context);
  return context;
}

(async () => {
  const ctx = moduleAt("src/lib/api.ts"), api = ctx.exports;
  assert.equal(api.recordingFallback(new api.LiveRunError("queue", 429)), "capacity");
  assert.equal(api.recordingFallback(new api.LiveRunError("server", 503)), "unavailable");
  for (const status of [400, 401, 403, 404]) assert.equal(api.recordingFallback(new api.LiveRunError("denied", status)), null);
  assert.equal(api.recordingFallback(new TypeError("offline")), "unavailable");
  assert.equal(api.recordingFallback(new Error("unknown")), null);
  ctx.fetch = async () => new Response(JSON.stringify({ detail: "capacity full" }), { status: 429 });
  await assert.rejects(api.startLiveRun("checkout"), (error) => error.status === 429 && error.message === "capacity full");
  ctx.fetch = async () => new Response("", { status: 200 });
  let failed = false;
  await new Promise((resolve) => api.streamRun("test", () => {}, resolve, () => { failed = true; }));
  assert.ok(failed, "a stream closing before an outcome must surface a failure");
  ctx.fetch = async () => new Response('data: {"seq":1,"type":"report"}\n\nevent: end\n\n', { status: 200 });
  failed = false;
  const events = [];
  await new Promise((resolve) => api.streamRun("test", (event) => events.push(event), resolve, () => { failed = true; }));
  assert.equal(events[0].type, "report"); assert.equal(failed, false);
  ctx.fetch = async () => new Response("denied", { status: 403 });
  let streamError;
  await new Promise((resolve) => api.streamRun("test", () => {}, resolve, (error) => { streamError = error; }));
  assert.equal(api.recordingFallback(streamError), null, "stream permission errors must not be hidden by replay");
  const { reduce, initialState, needsReview } = moduleAt("src/lib/run.ts").exports;
  assert.equal(needsReview({ secondOpinion: { verdict: "concerns" } }), true);
  assert.equal(needsReview({ secondOpinion: { verdict: "reject" } }), true);
  assert.equal(needsReview({ secondOpinion: { verdict: "approve" } }), false);
  assert.equal(needsReview({ report: { outcome: "fixed", second_opinion: { verdict: "concerns" } } }), true, "historical test-green reports retain their recorded review objections");
  const state = reduce(initialState, { seq: 1, type: "regression_test", accepted: true, path: "tests/test_bug.py", tests: { bug: "failed" }, reasons: { bug: "expected 422, received 201" } });
  assert.equal(state.regressionReasons.bug, "expected 422, received 201");
  assert.equal(reduce(state, { seq: 2, type: "excluded_tests", classes: ["NeedsDBTest"], reason: "network" }).excludedTests[0], "NeedsDBTest");
  console.log("Demo failover, stream completion and evidence-reducer checks passed");
})().catch((error) => { console.error(error); process.exitCode = 1; });
