// test/suite/runTests.ts
// VS Code test runner entry point.

import * as path from "path";

async function main() {
  try {
    const { runTests } = await import("@vscode/test-electron");
    const extensionDevelopmentPath = path.resolve(__dirname, "../../");
    const extensionTestsPath = path.resolve(__dirname, "./index");

    await runTests({
      extensionDevelopmentPath,
      extensionTestsPath,
    });
  } catch (err) {
    console.error("Failed to run tests:", err);
    process.exit(1);
  }
}

main();
