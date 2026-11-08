// The stand-in for the backend. A real local HTTP server, so the page's own fetch, stream reader
// and decoder run as in production, chunk by chunk, and a test can hold a stream open or cut its
// connection. Every /api/* request of the page goes here; anything else outside the site is
// blocked and fails the test, so no test can reach a model (ADR-0017).

import { createServer, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";

import { test as base, expect, type Page } from "@playwright/test";

export type Frame = { event: string; data?: Record<string, unknown> };
/** A recorded stream: its frames, plus where it waits for the test and where the line drops. */
export type Item = Frame | typeof HOLD | typeof CUT;
export const HOLD = "hold" as const;
export const CUT = "cut" as const;

type Script = { items: Item[]; status?: number; bytesPerWrite?: number };
export type ChatBody = {
  message: string;
  idempotency_key: string;
  conversation_id?: string;
  lang?: string;
};

// The server's frame format (backend/portfolio_agent/sse.py).
const encode = ({ event, data }: Frame) => `event: ${event}\ndata: ${JSON.stringify({ ...data, v: 1 })}\n\n`;

export class Api {
  url = "";
  readonly chats: ChatBody[] = [];
  readonly feedback: Record<string, unknown>[] = [];
  readonly deleted: string[] = [];
  readonly health: string[] = [];
  readonly unexpected: string[] = [];
  feedbackStatus = 204;
  deleteStatus = 204;
  private script: Script[] = [];
  private gates: (() => void)[] = [];
  private waiting: (() => void)[] = [];
  private open = new Set<ServerResponse>();
  private server = createServer(async (req, res) => {
    const path = req.url ?? "";
    const chunks: Buffer[] = [];
    for await (const c of req) chunks.push(c as Buffer);
    const body = Buffer.concat(chunks).toString();
    if (path.startsWith("/api/health")) {
      this.health.push(path);
      return res.writeHead(200, { "Content-Type": "application/json" }).end('{"status":"ok"}');
    }
    if (path === "/api/feedback" && req.method === "POST") {
      this.feedback.push(JSON.parse(body));
      return res.writeHead(this.feedbackStatus).end();
    }
    const del = /^\/api\/conversations\/(.+)$/.exec(path);
    if (del && req.method === "DELETE") {
      this.deleted.push(decodeURIComponent(del[1]));
      return res.writeHead(this.deleteStatus).end();
    }
    if (path === "/api/chat" && req.method === "POST") {
      this.chats.push(JSON.parse(body));
      return void this.play(res);
    }
    this.unexpected.push(`${req.method} ${path}`);
    res.writeHead(500).end();
  });

  async listen() {
    await new Promise<void>((done) => this.server.listen(0, "127.0.0.1", done));
    this.url = `http://127.0.0.1:${(this.server.address() as AddressInfo).port}`;
  }

  async close() {
    for (const res of this.open) res.destroy();
    this.server.closeAllConnections();
    await new Promise((done) => this.server.close(done));
  }

  /** The next /api/chat answers with this. Several calls queue up, one per request. */
  queue(items: Item[], options: Omit<Script, "items"> = {}) {
    this.script.push({ items, ...options });
  }

  /** Waits until the stream reaches a HOLD. */
  async held() {
    await expect.poll(() => this.gates.length, { message: "stream reached its HOLD" }).toBeGreaterThan(0);
  }

  /** Lets a stream go on from its HOLD. */
  async release() {
    await this.held();
    this.gates.shift()!();
  }

  private async play(res: ServerResponse) {
    const script = this.script.shift();
    if (!script) {
      this.unexpected.push("POST /api/chat with no recording queued");
      return res.writeHead(500).end();
    }
    if (script.status && script.status !== 200) return res.writeHead(script.status).end();
    this.open.add(res);
    res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
    res.flushHeaders();
    for (const item of script.items) {
      if (item === HOLD) {
        await new Promise<void>((go) => this.gates.push(go));
      } else if (item === CUT) {
        await new Promise((go) => setTimeout(go, 150)); // what was sent reaches the page first
        res.destroy();
        this.open.delete(res);
        return;
      } else {
        await this.write(res, encode(item), script.bytesPerWrite);
      }
    }
    res.end();
    this.open.delete(res);
  }

  private async write(res: ServerResponse, text: string, size?: number) {
    const bytes = Buffer.from(text);
    if (!size) return void res.write(bytes);
    // Splits frames, and the characters inside them, across network chunks.
    for (let i = 0; i < bytes.length; i += size) {
      res.write(bytes.subarray(i, i + size));
      await new Promise((go) => setTimeout(go, 0));
    }
  }
}

async function connect(page: Page, api: Api, blocked: string[]) {
  await page.route("**/*", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/")) return route.continue({ url: `${api.url}${url.pathname}${url.search}` });
    if (url.hostname === "localhost") return route.continue();
    if (url.protocol === "data:" || url.protocol === "blob:") return route.continue();
    blocked.push(url.href);
    return route.abort();
  });
}

type Fixtures = { api: Api; pageErrors: string[] };

export const test = base.extend<Fixtures>({
  api: async ({}, provide) => {
    const api = new Api();
    await api.listen();
    await provide(api);
    await api.close();
    expect(api.unexpected, "requests the recordings did not expect").toEqual([]);
  },
  pageErrors: async ({ page }, provide) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await provide(errors);
    expect(errors, "uncaught errors on the page").toEqual([]);
  },
  page: async ({ page, api }, provide) => {
    const blocked: string[] = [];
    await connect(page, api, blocked);
    await provide(page);
    expect(blocked, "requests that left the site").toEqual([]);
  },
});

export { expect };

/** Opens the chat page. The first paint is server-rendered, so it waits for React to attach. */
export async function openChat(page: Page, lang: "he" | "en" = "he") {
  await page.goto(`/${lang}`);
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
  await hydrated(page);
}

export async function hydrated(page: Page) {
  await page.waitForFunction(() => {
    const el = document.querySelector("textarea");
    return !el || Object.keys(el).some((k) => k.startsWith("__reactProps"));
  });
}

/** Types a question and sends it with Enter, as a visitor would. */
export async function ask(page: Page, question: string) {
  const field = page.locator("textarea");
  await field.fill(question);
  await field.press("Enter");
}
