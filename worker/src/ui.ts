import { html, raw } from "hono/html";
import { DEFAULT_FEED_SLUG, type Episode, type Feed, type QueueItem, type Stats } from "./db";

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// The discharge-tube mark: a capsule (vacuum tube) with leads at both ends, a
// glowing amber anode and a dark cathode sphere, lifted straight from the
// "Elektrische Entladungen" plate this surface is colored after.
const MARK = `<svg class="mark" viewBox="0 0 36 20" aria-hidden="true" focusable="false">
  <line x1="0" y1="10" x2="3.5" y2="10" />
  <line x1="32.5" y1="10" x2="36" y2="10" />
  <rect x="3.5" y="2.5" width="29" height="15" rx="7.5" fill="none" />
  <circle class="anode" cx="13" cy="10" r="3.4" />
  <circle class="cathode" cx="23.5" cy="10" r="2.2" />
</svg>`;

// Same mark, fixed-color, as an inline favicon (data URIs can't read CSS vars).
const FAVICON =
  "data:image/svg+xml," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 20">` +
      `<g fill="none" stroke="#8a8c7b" stroke-width="1.6" stroke-linecap="round">` +
      `<line x1="0" y1="10" x2="3.5" y2="10"/><line x1="32.5" y1="10" x2="36" y2="10"/>` +
      `<rect x="3.5" y="2.5" width="29" height="15" rx="7.5"/></g>` +
      `<circle cx="13" cy="10" r="3.4" fill="#cf8230"/><circle cx="23.5" cy="10" r="2.2" fill="#41443c"/></svg>`,
  );

// A circle with its right half filled: a contrast/theme glyph for the light/dark key.
const THEME_ICON = `<svg class="theme-ico" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
  <circle cx="8" cy="8" r="6.6" fill="none" stroke="currentColor" stroke-width="1.4" />
  <path d="M8 1.4 a6.6 6.6 0 0 1 0 13.2 z" fill="currentColor" />
</svg>`;

function lamp(status: QueueItem["status"]): string {
  return `<span class="lamp st-${status}"><i></i>${status}</span>`;
}

function queueRow(item: QueueItem): string {
  const source = item.kind === "url" ? item.payload : `text: ${item.title ?? truncate(item.payload, 60)}`;
  const error = item.error ? `<div class="err">${esc(truncate(item.error, 300))}</div>` : "";
  const actions =
    item.status === "failed"
      ? `<form method="post" action="/api/queue/${esc(item.id)}/retry"><button class="btn btn-sm">retry</button></form>`
      : "";
  return `<tr>
    <td><code class="id">${esc(item.id.slice(0, 8))}</code></td>
    <td class="src">${esc(truncate(source, 80))}${error}</td>
    <td>${lamp(item.status)}</td>
    <td><time>${esc(item.created_at)}</time></td>
    <td class="actions">${actions}</td>
  </tr>`;
}

function episodeRow(ep: Episode, audioBase: string): string {
  const id = esc(String(ep.id));
  const pubLocal = esc(ep.published_at.replace(" ", "T").slice(0, 16));
  const size = ep.audio_bytes ? (ep.audio_bytes / 1024 / 1024).toFixed(1) + " MB" : `<span class="nil">-</span>`;
  const actions = `<details class="edit">
    <summary class="btn btn-sm">edit</summary>
    <form method="post" action="/api/episodes/${id}">
      <label class="field"><span>Title</span><input name="title" type="text" value="${esc(ep.title)}" /></label>
      <label class="field"><span>Description</span><textarea name="description" rows="3">${esc(ep.description)}</textarea></label>
      <label class="field"><span>Publish (UTC)</span><input name="published_at" type="datetime-local" value="${pubLocal}" /></label>
      <button type="submit" class="btn btn-primary btn-sm">Save</button>
    </form>
  </details>
  <form method="post" action="/api/episodes/${id}/delete" onsubmit="return confirm('Delete this episode? This removes its audio too.')">
    <button class="btn btn-sm danger">delete</button>
  </form>`;
  return `<tr>
    <td>${esc(ep.title)}</td>
    <td><a class="link" href="${esc(`${audioBase}/${ep.audio_key}`)}">mp3</a></td>
    <td class="num">${size}</td>
    <td><time>${esc(ep.published_at)}</time></td>
    <td class="actions">${actions}</td>
  </tr>`;
}

// Single-feed installs don't need a switcher; the active feed is already named
// in the submit zone. Only render the control when there's a choice to make.
function feedSwitcher(feeds: Feed[], selected: Feed): string {
  if (feeds.length < 2) return "";
  const tabs = feeds
    .map((f) => {
      const active = f.id === selected.id ? " active" : "";
      return `<a class="key${active}" href="/?feed=${encodeURIComponent(f.slug)}">${esc(f.title)}</a>`;
    })
    .join("");
  return `<nav class="switcher" aria-label="Feeds">${tabs}</nav>`;
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
      ? `<span class="nil">default</span>`
      : `<form method="post" action="/api/feeds/${slug}/delete" onsubmit="return confirm('Delete feed “${esc(
          f.title,
        )}” and ALL its episodes (audio included)? This cannot be undone.')"><button class="btn btn-sm danger">delete</button></form>`;
  const edit = `<details class="edit">
    <summary class="btn btn-sm">edit</summary>
    <form method="post" action="/api/feeds/${slug}">
      <label class="field"><span>Title</span><input name="title" type="text" value="${esc(f.title)}" /></label>
      <label class="field"><span>Description</span><textarea name="description" rows="2">${esc(f.description)}</textarea></label>
      <label class="field"><span>Author</span><input name="author" type="text" value="${esc(f.author)}" /></label>
      <label class="field"><span>Image URL</span><input name="image_url" type="url" value="${esc(f.image_url)}" /></label>
      <label class="field"><span>Website link</span><input name="link" type="url" value="${esc(f.link)}" /></label>
      <label class="check"><input name="explicit" type="checkbox" ${f.explicit ? "checked" : ""}/> explicit</label>
      <button type="submit" class="btn btn-primary btn-sm">Save</button>
    </form>
  </details>`;
  return `<tr>
    <td><code class="id">${slug}</code></td>
    <td>${esc(f.title)}</td>
    <td><a class="link" href="/feed/${slug}.xml">rss</a></td>
    <td class="actions">${edit}${del}</td>
  </tr>`;
}

function feedsPanel(feeds: Feed[]): string {
  const rows = feeds.map(feedManageRow).join("");
  const addForm = `<details class="edit add-feed">
    <summary class="btn btn-sm">+ add feed</summary>
    <form method="post" action="/api/feeds">
      <label class="field"><span>Slug</span><input name="slug" type="text" placeholder="a-z 0-9 -" required pattern="[a-z0-9-]+" /></label>
      <label class="field"><span>Title</span><input name="title" type="text" required /></label>
      <label class="field"><span>Description</span><textarea name="description" rows="2"></textarea></label>
      <label class="field"><span>Author</span><input name="author" type="text" /></label>
      <label class="field"><span>Image URL</span><input name="image_url" type="url" /></label>
      <label class="field"><span>Website link</span><input name="link" type="url" /></label>
      <label class="check"><input name="explicit" type="checkbox" /> explicit</label>
      <button type="submit" class="btn btn-primary btn-sm">Create feed</button>
    </form>
  </details>`;
  return `<div class="table-wrap"><table><thead><tr><th>slug</th><th>title</th><th>rss</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${addForm}`;
}

// One-line instrument readout (no cards). Status indicators stay dark until a
// count is non-zero, then light their signal color, the way a panel lamp would.
function readout(s: Stats): string {
  const m = (label: string, val: number) => `<span class="m"><b>${val}</b>${label}</span>`;
  const sig = (label: string, val: number, cls: string) =>
    `<span class="m${val > 0 ? " on " + cls : ""}">${val > 0 ? "<i></i>" : ""}<b>${val}</b>${label}</span>`;
  const stale = s.stale_synthesizing > 0 ? `<span class="m on fail"><i></i><b>${s.stale_synthesizing}</b>stale</span>` : "";
  const lastPub = s.last_published_at ? `last publish ${esc(s.last_published_at)} UTC` : "no episodes yet";
  const backlog = s.oldest_queued_at ? ` · oldest queued ${esc(s.oldest_queued_at)} UTC` : "";
  return `<div class="readout" aria-label="Status">
    ${m("feeds", s.feeds)}
    ${m("episodes", s.episodes)}
    ${sig("queued", s.by_status.queued, "q")}
    ${sig("synthesizing", s.by_status.synthesizing, "syn")}${stale}
    ${sig("failed", s.by_status.failed, "fail")}
    <span class="tick">${lastPub}${backlog}</span>
  </div>`;
}

// Set the persisted theme before first paint (no flash), and the toggle handler.
const THEME_SCRIPT = raw(
  `(function(){try{var t=localStorage.getItem('vb-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}catch(e){}})();` +
    `function vbTheme(){var d=document.documentElement,c=d.dataset.theme||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');` +
    `var n=c==='dark'?'light':'dark';d.dataset.theme=n;try{localStorage.setItem('vb-theme',n);}catch(e){}}`,
);

const STYLE = raw(`
  @font-face {
    font-family: "IBM Plex Mono"; font-style: normal; font-weight: 400;
    font-display: swap; src: url("/fonts/ibm-plex-mono-400.woff2") format("woff2");
  }
  @font-face {
    font-family: "IBM Plex Mono"; font-style: normal; font-weight: 600;
    font-display: swap; src: url("/fonts/ibm-plex-mono-600.woff2") format("woff2");
  }
  /* Light is the base; dark applies automatically unless the user forced light,
     and is forced when the user picks dark. data-theme (set by the toggle) wins. */
  :root {
    color-scheme: light dark;
    --bg: #e7e5d6; --surface: #f1efe3; --sunken: #dbd9ca;
    --ink: #1b1c17; --ink-soft: #565749; --line: #c4c2b1;
    --accent: #cf8230; --accent-edge: #9c5e1c; --on-accent: #1b1410;
    --celadon: #5d7a45; --celadon-edge: #445a32;
    --vermilion: #a93b27; --vermilion-edge: #7e2a1b;
    --steel: #54574d; --steel-soft: #6f7265;
    --r-key: 8px; --r-lamp: 3px;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg: #12130d; --surface: #1a1c14; --sunken: #0d0e08;
      --ink: #d9d7c4; --ink-soft: #8d8e7c; --line: #2d3026;
      --accent: #e0a44a; --accent-edge: #ab7a2c; --on-accent: #1b1410;
      --celadon: #94b16d; --celadon-edge: #6f8a4f;
      --vermilion: #d4694b; --vermilion-edge: #a8492f;
      --steel: #b6b8a6; --steel-soft: #8a8c7b;
    }
  }
  :root[data-theme="dark"] {
    color-scheme: dark;
    --bg: #12130d; --surface: #1a1c14; --sunken: #0d0e08;
    --ink: #d9d7c4; --ink-soft: #8d8e7c; --line: #2d3026;
    --accent: #e0a44a; --accent-edge: #ab7a2c; --on-accent: #1b1410;
    --celadon: #94b16d; --celadon-edge: #6f8a4f;
    --vermilion: #d4694b; --vermilion-edge: #a8492f;
    --steel: #b6b8a6; --steel-soft: #8a8c7b;
  }
  :root[data-theme="light"] { color-scheme: light; }

  * { box-sizing: border-box; }
  body {
    font: 14px/1.55 "IBM Plex Mono", ui-monospace, "SF Mono", "SFMono-Regular", Menlo, "Cascadia Mono", monospace;
    color: var(--ink); background: var(--bg);
    max-width: 60rem; margin: 0 auto; padding: 1.5rem 1.25rem 4rem;
    -webkit-font-smoothing: antialiased;
  }
  a { color: inherit; }
  .num, .id, time { font-variant-numeric: tabular-nums; }

  /* ---- masthead (no box, just a hairline) ---- */
  .masthead { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; padding: 0 0 0.85rem; border-bottom: 1px solid var(--line); }
  .mark { width: 38px; height: auto; color: var(--ink); flex: none; }
  .mark line, .mark rect { stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; }
  .mark .anode { fill: var(--accent); }
  .mark .cathode { fill: var(--steel); }
  .wordmark { font-weight: 600; letter-spacing: 0.02em; }
  .wordmark small { display: block; font-weight: 400; font-size: 0.72rem; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink-soft); }
  .mast-right { margin-left: auto; min-width: 0; display: flex; align-items: center; gap: 0.7rem; }
  .feed-name { min-width: 0; font-size: 0.82rem; color: var(--ink-soft); text-align: right; max-width: 16rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .theme-key { flex: none; display: inline-grid; place-items: center; width: 34px; height: 30px; padding: 0; color: var(--ink); }
  .theme-ico { width: 15px; height: 15px; }

  /* ---- status readout (one line) ---- */
  .readout { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.4rem 1.4rem; margin: 0.75rem 0 1.6rem; font-size: 0.68rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-soft); }
  .readout .m { display: inline-flex; align-items: baseline; gap: 0.4rem; }
  .readout .m b { font-size: 0.95rem; font-weight: 600; letter-spacing: 0; color: var(--ink); font-variant-numeric: tabular-nums; }
  .readout .m i { align-self: center; width: 7px; height: 7px; border-radius: var(--r-lamp); background: currentColor; box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 18%, transparent); }
  .readout .m.on.q { color: var(--steel); }
  .readout .m.on.syn { color: var(--accent); }
  .readout .m.on.syn i { animation: pulse 1.4s ease-in-out infinite; }
  .readout .m.on.fail { color: var(--vermilion); }
  .readout .m.on b { color: inherit; }
  .readout .tick { margin-left: auto; letter-spacing: 0; text-transform: none; font-size: 0.74rem; color: var(--ink-soft); }
  @media (prefers-reduced-motion: reduce) { .readout .m.on.syn i { animation: none; } }

  /* ---- feed switcher (function keys) ---- */
  .switcher { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0 0 1.6rem; }
  .key {
    text-decoration: none; padding: 0.35rem 0.85rem; border-radius: var(--r-key);
    border: 1px solid var(--line); border-bottom-width: 3px; background: var(--surface);
    font-size: 0.82rem; transition: transform .06s, background .12s;
  }
  .key.active { background: var(--accent); color: var(--on-accent); border-color: var(--accent-edge); font-weight: 600; }
  .key:active { transform: translateY(2px); border-bottom-width: 1px; }

  /* ---- zones (labelled sections, no card) ---- */
  .zone { margin-top: 2.2rem; }
  .zone > h2 {
    display: flex; align-items: baseline; gap: 0.6rem; flex-wrap: wrap;
    margin: 0 0 1rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--line);
    font-size: 0.78rem; font-weight: 600; letter-spacing: 0.2em; text-transform: uppercase;
  }
  .zone-meta { letter-spacing: 0; text-transform: none; font-weight: 400; font-size: 0.78rem; color: var(--ink-soft); }
  .empty { color: var(--ink-soft); font-size: 0.85rem; }

  /* ---- tables ---- */
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
  thead th { text-align: left; font-size: 0.68rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-soft); font-weight: 600; padding: 0.3rem 0.6rem; }
  tbody td { text-align: left; padding: 0.5rem 0.6rem; border-top: 1px solid var(--line); vertical-align: top; }
  thead th:first-child, tbody td:first-child { padding-left: 0; }
  .src { max-width: 26rem; overflow-wrap: anywhere; }
  .id { color: var(--ink-soft); }
  time { color: var(--ink-soft); font-size: 0.76rem; }
  .num { white-space: nowrap; }
  .nil { color: var(--ink-soft); opacity: 0.55; }
  .link { color: var(--accent); text-underline-offset: 2px; }
  .err { color: var(--vermilion); font-size: 0.76rem; white-space: pre-wrap; margin-top: 0.25rem; }
  td.actions { white-space: nowrap; }
  td.actions > * { display: inline-block; vertical-align: top; margin: 0 0.3rem 0 0; }

  /* ---- status lamps (in the queue table) ---- */
  .lamp { display: inline-flex; align-items: center; gap: 0.4rem; font-size: 0.78rem; color: var(--ink-soft); }
  .lamp i { width: 9px; height: 9px; border-radius: var(--r-lamp); flex: none; box-shadow: 0 0 0 2px color-mix(in srgb, currentColor 18%, transparent); }
  .st-queued i { background: var(--steel); }
  .st-synthesizing { color: var(--accent); }
  .st-synthesizing i { background: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
  .st-published { color: var(--celadon); }
  .st-published i { background: var(--celadon); }
  .st-failed { color: var(--vermilion); }
  .st-failed i { background: var(--vermilion); }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
  @media (prefers-reduced-motion: reduce) { .st-synthesizing i { animation: none; } }

  /* ---- controls ---- */
  .btn {
    font: inherit; cursor: pointer; color: var(--ink); background: var(--surface);
    border: 1px solid var(--line); border-bottom-width: 3px; border-radius: var(--r-key);
    padding: 0.5rem 1rem; transition: transform .06s, background .12s; list-style: none;
  }
  .btn::-webkit-details-marker { display: none; }
  .btn:hover { background: color-mix(in srgb, var(--ink) 5%, var(--surface)); }
  .btn:active { transform: translateY(2px); border-bottom-width: 1px; }
  .btn-sm { padding: 0.3rem 0.7rem; font-size: 0.78rem; }
  .btn-primary { background: var(--accent); color: var(--on-accent); border-color: var(--accent-edge); font-weight: 600; }
  .btn-primary:hover { background: color-mix(in srgb, #fff 8%, var(--accent)); }
  .danger { color: var(--vermilion); border-color: var(--vermilion-edge); }
  .danger:hover { background: color-mix(in srgb, var(--vermilion) 10%, var(--surface)); }
  :focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: var(--r-key); }

  input, textarea, select {
    font: inherit; color: var(--ink); background: var(--sunken);
    border: 1px solid var(--line); border-radius: var(--r-key); padding: 0.5rem 0.6rem;
    width: 100%; min-width: 0; max-width: 100%;
  }
  input::placeholder, textarea::placeholder { color: var(--ink-soft); opacity: 0.7; }
  textarea { resize: vertical; }

  .field { display: grid; gap: 0.25rem; min-width: 0; }
  .field > span { font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-soft); }
  .check { display: flex; align-items: center; gap: 0.45rem; font-size: 0.82rem; width: fit-content; }
  .check input { width: auto; }

  form.submit { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.7rem; max-width: 38rem; }
  form.submit .btn-primary { width: fit-content; }
  .or { font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-soft); text-align: center; }

  details.edit { display: inline-block; }
  details.edit[open] { display: block; }
  details.edit[open] > summary { margin-bottom: 0.6rem; }
  details.edit form { display: grid; grid-template-columns: minmax(0, 1fr); gap: 0.55rem; width: min(22rem, 100%); padding: 0.75rem; border: 1px solid var(--line); border-radius: var(--r-key); background: var(--sunken); }
  .add-feed { margin-top: 0.9rem; }
`);

export function renderHome(
  feeds: Feed[],
  feed: Feed,
  queue: QueueItem[],
  episodes: Episode[],
  stats: Stats,
  audioBase: string,
): ReturnType<typeof html> {
  const queueBody =
    queue.length === 0
      ? `<p class="empty">Nothing queued.</p>`
      : `<div class="table-wrap"><table><thead><tr><th>id</th><th>source</th><th>status</th><th>created (UTC)</th><th></th></tr></thead><tbody>${queue
          .map(queueRow)
          .join("")}</tbody></table></div>`;

  const episodesBody =
    episodes.length === 0
      ? `<p class="empty">No episodes yet.</p>`
      : `<div class="table-wrap"><table><thead><tr><th>title</th><th>audio</th><th>size</th><th>published (UTC)</th><th></th></tr></thead><tbody>${episodes
          .map((ep) => episodeRow(ep, audioBase))
          .join("")}</tbody></table></div>`;

  return html`<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light dark" />
<link rel="icon" href="${FAVICON}" />
<title>${feed.title} · vb control plane</title>
<script>${THEME_SCRIPT}</script>
<style>${STYLE}</style>
</head>
<body>
<header class="masthead">
  ${raw(MARK)}
  <span class="wordmark">vb<small>control plane</small></span>
  <div class="mast-right">
    <span class="feed-name">${feed.title}</span>
    <button type="button" class="btn theme-key" onclick="vbTheme()" aria-label="Toggle light or dark theme" title="Toggle theme">${raw(THEME_ICON)}</button>
  </div>
</header>

${raw(readout(stats))}
${raw(feedSwitcher(feeds, feed))}

<section class="zone">
  <h2>Submit <span class="zone-meta">${feed.description} · <a class="link" href="/feed/${esc(feed.slug)}.xml">feed.xml</a></span></h2>
  <form class="submit" method="post" action="/api/queue">
    <label class="field"><span>Feed</span>${raw(feedSelect(feeds, feed))}</label>
    <label class="field"><span>Article URL</span><input name="url" type="url" placeholder="https://example.com/article" /></label>
    <p class="or">or</p>
    <label class="field"><span>Raw text</span><textarea name="text" rows="4" placeholder="Paste an article body to read aloud"></textarea></label>
    <label class="field"><span>Title (for text submissions)</span><input name="title" type="text" /></label>
    <button type="submit" class="btn btn-primary">Queue episode</button>
  </form>
</section>

<section class="zone">
  <h2>Queue <span class="zone-meta">${queue.length} item${queue.length === 1 ? "" : "s"}</span></h2>
  ${raw(queueBody)}
</section>

<section class="zone">
  <h2>Episodes <span class="zone-meta">${episodes.length} published</span></h2>
  ${raw(episodesBody)}
</section>

<section class="zone">
  <h2>Feeds <span class="zone-meta">${feeds.length} configured</span></h2>
  ${raw(feedsPanel(feeds))}
</section>
</body>
</html>`;
}
