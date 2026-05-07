import ReactDOM from "react-dom/client";
import { App } from "./App.js";
import "./index.css";

const params = new URLSearchParams(window.location.search);
const caseId = params.get("case") ?? "demo";
const root = params.get("root") ?? "";
const model = params.get("model") ?? "claude-sonnet-4-6";

// StrictMode is intentionally off: it double-mounts every component in dev,
// which causes the WebSocket bridge to connect → close → connect during the
// same render and creates surprising "stuck on Thinking…" races.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <App caseId={caseId} root={root} model={model} />
);
