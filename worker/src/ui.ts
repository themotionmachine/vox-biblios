import { html, raw } from "hono/html";
import type { Episode, Feed, QueueItem } from "./db";

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

const STATUS_COLORS: Record<QueueItem["status"], string> = {
  queued: "#8a6d1f",
  synthesizing: "#1f5e8a",
  published: "#2e7d32",
  failed: "#b3261e",
};

function queueRow(item: QueueItem): string {
  const source = item.kind === "url" ? item.payload : `text: ${item.title ?? truncate(item.payload, 60)}`;
  const error = item.error ? `<div class="error">${esc(truncate(item.error, 300))}</div>` : "";
  const actions =
    item.status === "failed"
      ? `<form method="post" action="/api/queue/${esc(item.id)}/retry"><button>retry</button></form>`
      : "";
  return `<tr>
    <td><code>${esc(item.id.slice(0, 8))}</code></td>
    <td class="src">${esc(truncate(source, 80))}${error}</td>
    <td><span class="badge" style="background:${STATUS_COLORS[item.status]}">${item.status}</span></td>
    <td>${esc(item.created_at)}</td>
    <td>${actions}</td>
  </tr>`;
}

function episodeRow(ep: Episode, audioBase: string): string {
  return `<tr>
    <td>${esc(ep.title)}</td>
    <td><a href="${esc(`${audioBase}/${ep.audio_key}`)}">mp3</a></td>
    <td>${ep.audio_bytes ? (ep.audio_bytes / 1024 / 1024).toFixed(1) + " MB" : "—"}</td>
    <td>${esc(ep.published_at)}</td>
  </tr>`;
}

export function renderHome(
  feed: Feed,
  queue: QueueItem[],
  episodes: Episode[],
  audioBase: string,
): ReturnType<typeof html> {
  return html`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${feed.title} — control plane</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 15px/1.5 ui-sans-serif, system-ui, sans-serif; max-width: 56rem; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.3rem; } h2 { font-size: 1.05rem; margin-top: 2rem; }
  table { border-collapse: collapse; width: 100%; font-size: 0.875rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid color-mix(in srgb, currentColor 15%, transparent); vertical-align: top; }
  .badge { color: white; padding: 0.1rem 0.5rem; border-radius: 99px; font-size: 0.75rem; }
  .src { max-width: 28rem; overflow-wrap: anywhere; }
  .error { color: #b3261e; font-size: 0.8rem; white-space: pre-wrap; }
  form.submit { display: grid; gap: 0.5rem; max-width: 36rem; margin: 1rem 0; }
  input, textarea, button { font: inherit; padding: 0.45rem 0.6rem; border-radius: 6px; border: 1px solid color-mix(in srgb, currentColor 25%, transparent); background: transparent; }
  button { cursor: pointer; width: fit-content; padding-inline: 1rem; }
  .muted { opacity: 0.65; font-size: 0.85rem; }
</style>
</head>
<body>
<h1>${feed.title}</h1>
<p class="muted">${feed.description} · <a href="/feed.xml">feed.xml</a></p>

<h2>Submit</h2>
<form class="submit" method="post" action="/api/queue">
  <input name="url" type="url" placeholder="https://example.com/article" />
  <textarea name="text" rows="4" placeholder="…or paste raw text"></textarea>
  <input name="title" type="text" placeholder="Title (optional, used for text submissions)" />
  <button type="submit">Queue episode</button>
</form>

<h2>Queue</h2>
${queue.length === 0
    ? html`<p class="muted">Nothing queued.</p>`
    : raw(`<table><thead><tr><th>id</th><th>source</th><th>status</th><th>created (UTC)</th><th></th></tr></thead><tbody>${queue
        .map(queueRow)
        .join("")}</tbody></table>`)}

<h2>Episodes</h2>
${episodes.length === 0
    ? html`<p class="muted">No episodes yet.</p>`
    : raw(`<table><thead><tr><th>title</th><th>audio</th><th>size</th><th>published (UTC)</th></tr></thead><tbody>${episodes
        .map((ep) => episodeRow(ep, audioBase))
        .join("")}</tbody></table>`)}
</body>
</html>`;
}
