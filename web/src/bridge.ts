import type { StreamEvent } from "./types.js";

export interface BridgeOptions {
  url: string; // e.g. /ws (vite proxy) or ws://host:port/ws
  caseId: string;
  root: string;
}

export class WSBridge {
  private ws: WebSocket | null = null;
  private handlers: Array<(ev: StreamEvent) => void> = [];
  private openHandlers: Array<() => void> = [];
  private closeHandlers: Array<(reason: string) => void> = [];
  private outbox: string[] = [];

  constructor(private opts: BridgeOptions) {}

  connect(): void {
    if (this.ws) {
      console.debug("[bridge] connect() ignored — already have ws");
      return;
    }
    const u = new URL(this.opts.url, window.location.origin);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    u.searchParams.set("case", this.opts.caseId);
    u.searchParams.set("root", this.opts.root);
    const url = u.toString();
    console.debug("[bridge] connecting to", url);
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      console.debug("[bridge] open; flushing", this.outbox.length, "queued frames");
      while (this.outbox.length) {
        const frame = this.outbox.shift()!;
        ws.send(frame);
      }
      this.openHandlers.forEach((h) => h());
    };
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data as string) as StreamEvent;
        this.handlers.forEach((h) => h(ev));
      } catch (err) {
        console.error("[bridge] failed to parse frame", err, e.data);
      }
    };
    ws.onclose = (e) => {
      console.debug("[bridge] close code=", e.code, "reason=", e.reason);
      this.ws = null;
      this.closeHandlers.forEach((h) => h(e.reason || "closed"));
    };
    ws.onerror = (e) => {
      console.error("[bridge] error", e);
      this.handlers.forEach((h) => h({ type: "error", error: "websocket error" }));
    };
  }

  onEvent(h: (ev: StreamEvent) => void): void {
    this.handlers.push(h);
  }
  onOpen(h: () => void): void {
    this.openHandlers.push(h);
  }
  onClose(h: (reason: string) => void): void {
    this.closeHandlers.push(h);
  }

  private sendFrame(frame: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(frame);
    } else if (this.ws && this.ws.readyState === WebSocket.CONNECTING) {
      // Queue until onopen flushes.
      console.debug("[bridge] queuing frame (ws still CONNECTING)");
      this.outbox.push(frame);
    } else {
      console.error("[bridge] sendFrame: ws unavailable; state=", this.ws?.readyState);
      this.handlers.forEach((h) =>
        h({ type: "error", error: `ws not open (state=${this.ws?.readyState ?? "null"})` }),
      );
    }
  }

  send(prompt: string, opts?: { forceStrategy?: boolean }): void {
    const payload: Record<string, unknown> = { prompt };
    if (opts?.forceStrategy) payload.force_strategy = true;
    this.sendFrame(JSON.stringify(payload));
    console.debug("[bridge] queued/sent prompt (len=" + prompt.length + ")");
  }

  abort(): void {
    this.sendFrame(JSON.stringify({ type: "abort" }));
  }

  close(): void {
    this.ws?.close();
    this.ws = null;
    this.outbox = [];
  }
}
