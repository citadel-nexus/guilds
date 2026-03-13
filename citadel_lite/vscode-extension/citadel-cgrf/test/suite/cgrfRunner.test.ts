// test/suite/cgrfRunner.test.ts
// Unit tests for cgrfRunner JSON parsing.

import * as assert from "assert";
import type { ValidateResult, TierCheckResult, ReportResult } from "../../src/cgrfRunner";

suite("CGRF Runner JSON Parsing", () => {
  test("ValidateResult JSON structure", () => {
    const raw = JSON.stringify({
      command: "validate",
      tier: 1,
      module_path: "src/agents/sentinel_v2.py",
      compliant: true,
      checks: [
        { name: "parse", passed: true, message: "OK", required: true },
        { name: "module_docstring", passed: true, message: "Present", required: true },
      ],
      warnings: [],
    });
    const result: ValidateResult = JSON.parse(raw);
    assert.strictEqual(result.command, "validate");
    assert.strictEqual(result.compliant, true);
    assert.strictEqual(result.checks.length, 2);
    assert.strictEqual(result.checks[0].name, "parse");
    assert.strictEqual(result.tier, 1);
  });

  test("TierCheckResult JSON structure", () => {
    const raw = JSON.stringify({
      command: "tier-check",
      tier: 1,
      results: [
        { module_path: "a.py", compliant: true, failed_checks: [] },
        { module_path: "b.py", compliant: false, failed_checks: [{ name: "parse", message: "fail" }] },
      ],
      summary: { total: 2, passed: 1, failed: 1 },
    });
    const result: TierCheckResult = JSON.parse(raw);
    assert.strictEqual(result.command, "tier-check");
    assert.strictEqual(result.summary.total, 2);
    assert.strictEqual(result.results[1].compliant, false);
  });

  test("ReportResult JSON structure", () => {
    const raw = JSON.stringify({
      command: "report",
      tier: 2,
      modules: [
        { module_path: "x.py", compliant: true },
      ],
      summary: { total: 1, compliant: 1, non_compliant: 0 },
    });
    const result: ReportResult = JSON.parse(raw);
    assert.strictEqual(result.command, "report");
    assert.strictEqual(result.summary.compliant, 1);
  });

  test("Non-compliant result has failed checks", () => {
    const raw = JSON.stringify({
      command: "validate",
      tier: 1,
      module_path: "test.py",
      compliant: false,
      checks: [
        { name: "cgrf_metadata", passed: false, message: "Missing _CGRF_TIER", required: true },
      ],
      warnings: ["Declared tier mismatch"],
    });
    const result: ValidateResult = JSON.parse(raw);
    assert.strictEqual(result.compliant, false);
    assert.strictEqual(result.warnings.length, 1);
    const failed = result.checks.filter((c) => !c.passed && c.required);
    assert.strictEqual(failed.length, 1);
  });
});
