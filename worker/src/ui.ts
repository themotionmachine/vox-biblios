import { html, raw } from "hono/html";
import { DEFAULT_FEED_SLUG, type Episode, type Feed, type QueueItem } from "./db";

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
  const id = esc(String(ep.id));
  const actions = `<details class="edit">
    <summary>edit</summary>
    <form method="post" action="/api/episodes/${id}">
      <input name="title" type="text" value="${esc(ep.title)}" />
      <textarea name="description" rows="3">${esc(ep.description)}</textarea>
      <button type="submit">Save</button>
    </form>
  </details>
  <form method="post" action="/api/episodes/${id}/delete" onsubmit="return confirm('Delete this episode? This removes its audio too.')">
    <button class="danger">delete</button>
  </form>`;
  return `<tr>
    <td>${esc(ep.title)}</td>
    <td><a href="${esc(`${audioBase}/${ep.audio_key}`)}">mp3</a></td>
    <td>${ep.audio_bytes ? (ep.audio_bytes / 1024 / 1024).toFixed(1) + " MB" : "—"}</td>
    <td>${esc(ep.published_at)}</td>
    <td class="actions">${actions}</td>
  </tr>`;
}

function feedSwitcher(feeds: Feed[], selected: Feed): string {
  const tabs = feeds
    .map((f) => {
      const active = f.id === selected.id ? " active" : "";
      return `<a class="feed-tab${active}" href="/?feed=${encodeURIComponent(f.slug)}">${esc(f.title)}</a>`;
    })
    .join("");
  return `<nav class="feeds">${tabs}</nav>`;
}

function feedSelect(feeds: Feed[], selected: Feed): string {
  const opts = feeds
    .map((f) => `<option value="${esc(f.slug)}"${f.id === selected.id ? " selected" : ""}>${esc(f.title)}</option>`)
    .join("");
  return `<select name="feed">${opts}</select>`;
}

function feedManageRow(f: Feed): string {
  const slug = esc(f.slug);
  const del =
    f.slug === DEFAULT_FEED_SLUG
      ? `<span class="muted">default</span>`
      : `<form method="post" action="/api/feeds/${slug}/delete" onsubmit="return confirm('Delete feed “${esc(
          f.title,
        )}” and ALL its episodes (audio included)? This cannot be undone.')"><button class="danger">delete</button></form>`;
  const edit = `<details class="edit">
    <summary>edit</summary>
    <form method="post" action="/api/feeds/${slug}">
      <input name="title" type="text" value="${esc(f.title)}" placeholder="Title" />
      <textarea name="description" rows="2" placeholder="Description">${esc(f.description)}</textarea>
      <input name="author" type="text" value="${esc(f.author)}" placeholder="Author" />
      <input name="image_url" type="url" value="${esc(f.image_url)}" placeholder="Image URL" />
      <input name="link" type="url" value="${esc(f.link)}" placeholder="Website link" />
      <label class="row"><input name="explicit" type="checkbox" ${f.explicit ? "checked" : ""}/> explicit</label>
      <button type="submit">Save</button>
    </form>
  </details>`;
  return `<tr>
    <td><code>${slug}</code></td>
    <td>${esc(f.title)}</td>
    <td><a href="/feed/${slug}.xml">rss</a></td>
    <td class="actions">${edit}${del}</td>
  </tr>`;
}

function feedsPanel(feeds: Feed[]): string {
  const rows = feeds.map(feedManageRow).join("");
  const addForm = `<details class="edit add-feed">
    <summary>+ add feed</summary>
    <form method="post" action="/api/feeds">
      <input name="slug" type="text" placeholder="slug (a-z 0-9 -)" required pattern="[a-z0-9-]+" />
      <input name="title" type="text" placeholder="Title" required />
      <textarea name="description" rows="2" placeholder="Description"></textarea>
      <input name="author" type="text" placeholder="Author" />
      <input name="image_url" type="url" placeholder="Image URL" />
      <input name="link" type="url" placeholder="Website link" />
      <label class="row"><input name="explicit" type="checkbox" /> explicit</label>
      <button type="submit">Create feed</button>
    </form>
  </details>`;
  return `<table><thead><tr><th>slug</th><th>title</th><th>rss</th><th></th></tr></thead><tbody>${rows}</tbody></table>${addForm}`;
}

export function renderHome(
  feeds: Feed[],
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
  td.actions { white-space: nowrap; display: flex; gap: 0.5rem; align-items: flex-start; }
  td.actions button { padding: 0.2rem 0.6rem; font-size: 0.8rem; }
  td.actions form { margin: 0; }
  details.edit summary { cursor: pointer; font-size: 0.8rem; opacity: 0.8; list-style: none; }
  details.edit[open] { padding: 0.4rem 0; }
  details.edit form { display: grid; gap: 0.4rem; margin-top: 0.4rem; min-width: 18rem; }
  button.danger { color: #b3261e; border-color: color-mix(in srgb, #b3261e 40%, transparent); }
  nav.feeds { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 1rem; }
  .feed-tab { text-decoration: none; padding: 0.25rem 0.7rem; border-radius: 99px; border: 1px solid color-mix(in srgb, currentColor 20%, transparent); font-size: 0.85rem; }
  .feed-tab.active { background: color-mix(in srgb, currentColor 12%, transparent); font-weight: 600; }
  label.row { display: flex; gap: 0.4rem; align-items: center; font-size: 0.85rem; width: fit-content; }
  select { font: inherit; padding: 0.45rem 0.6rem; border-radius: 6px; border: 1px solid color-mix(in srgb, currentColor 25%, transparent); background: transparent; }
</style>
</head>
<body>
${raw(feedSwitcher(feeds, feed))}
<h1>${feed.title}</h1>
<p class="muted">${feed.description} · <a href="/feed/${esc(feed.slug)}.xml">feed.xml</a></p>

<h2>Submit</h2>
<form class="submit" method="post" action="/api/queue">
  ${raw(feedSelect(feeds, feed))}
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
    : raw(`<table><thead><tr><th>title</th><th>audio</th><th>size</th><th>published (UTC)</th><th></th></tr></thead><tbody>${episodes
        .map((ep) => episodeRow(ep, audioBase))
        .join("")}</tbody></table>`)}

<h2>Feeds</h2>
${raw(feedsPanel(feeds))}
</body>
</html>`;
}
