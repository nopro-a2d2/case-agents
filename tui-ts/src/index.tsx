import React from "react";
import { render } from "ink";
import { App } from "./components/App.js";
import { PythonBridge } from "./bridge.js";

const DEFAULT_MODEL = "claude-sonnet-4-6";

function parseArgs(): { caseId: string; root: string; pythonBin: string; model: string } {
  const args = process.argv.slice(2);
  let caseId = "";
  let root = "";
  let pythonBin = "python";
  let model = DEFAULT_MODEL;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--case" && args[i + 1]) caseId = args[++i];
    else if (args[i] === "--root" && args[i + 1]) root = args[++i];
    else if (args[i] === "--python" && args[i + 1]) pythonBin = args[++i];
    else if (args[i] === "--model" && args[i + 1]) model = args[++i];
  }

  if (!caseId || !root) {
    console.error("Usage: tsx src/index.tsx --case <id> --root <path> [--python <bin>] [--model <name>]");
    process.exit(1);
  }
  return { caseId, root, pythonBin, model };
}

const { caseId, root, pythonBin, model } = parseArgs();
const bridge = new PythonBridge(pythonBin, caseId, root);

const { unmount } = render(
  <App bridge={bridge} caseId={caseId} model={model} />,
  { exitOnCtrlC: false }
);

process.on("exit", () => {
  bridge.kill();
  unmount();
});
