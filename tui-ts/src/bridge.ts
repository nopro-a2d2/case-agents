import { spawn, type ChildProcess } from "node:child_process";
import { createInterface } from "node:readline";
import type { StreamEvent } from "./types.js";

export class PythonBridge {
  private proc: ChildProcess;
  private handlers: Array<(ev: StreamEvent) => void> = [];
  private closeHandlers: Array<() => void> = [];

  constructor(pythonBin: string, caseId: string, root: string) {
    this.proc = spawn(
      pythonBin,
      ["-m", "case_agent", "headless", "--case", caseId, "--root", root],
      { stdio: ["pipe", "pipe", "inherit"], cwd: process.cwd() }
    );

    const rl = createInterface({ input: this.proc.stdout! });
    rl.on("line", (line: string) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      try {
        const ev = JSON.parse(trimmed) as StreamEvent;
        this.handlers.forEach((h) => h(ev));
      } catch {
        // ignore malformed lines
      }
    });

    this.proc.on("close", () => {
      this.closeHandlers.forEach((h) => h());
    });
  }

  onEvent(handler: (ev: StreamEvent) => void): void {
    this.handlers.push(handler);
  }

  onClose(handler: () => void): void {
    this.closeHandlers.push(handler);
  }

  send(
    prompt: string,
    opts?: { forceStrategy?: boolean; forceBrief?: boolean },
  ): void {
    const payload: Record<string, unknown> = { prompt };
    if (opts?.forceStrategy) payload.force_strategy = true;
    if (opts?.forceBrief) payload.force_brief = true;
    this.proc.stdin!.write(JSON.stringify(payload) + "\n");
  }

  abort(): void {
    this.proc.stdin!.write(JSON.stringify({ type: "abort" }) + "\n");
  }

  kill(): void {
    this.proc.kill();
  }
}
