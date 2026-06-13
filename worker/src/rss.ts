import type { Episode, Feed } from "./db";

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** D1 datetime('now') strings are 'YYYY-MM-DD HH:MM:SS' in UTC. */
function toRfc2822(d1Datetime: string): string {
  return new Date(d1Datetime.replace(" ", "T") + "Z").toUTCString();
}

function formatDuration(totalSecs: number): string {
  const h = Math.floor(totalSecs / 3600);
  const m = Math.floor((totalSecs % 3600) / 60);
  const s = totalSecs % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

export function renderRss(
  feed: Feed,
  episodes: Episode[],
  opts: { feedUrl: string; audioBase: string },
): string {
  const items = episodes
    .map((ep) => {
      const audioUrl = `${opts.audioBase}/${ep.audio_key}`;
      const duration =
        ep.duration_secs != null ? `\n      <itunes:duration>${formatDuration(ep.duration_secs)}</itunes:duration>` : "";
      return `    <item>
      <title>${esc(ep.title)}</title>
      <description>${esc(ep.description)}</description>
      <enclosure url="${esc(audioUrl)}" length="${ep.audio_bytes}" type="audio/mpeg"/>
      <guid isPermaLink="false">${esc(ep.guid)}</guid>
      <pubDate>${toRfc2822(ep.published_at)}</pubDate>${duration}
    </item>`;
    })
    .join("\n");

  const image = feed.image_url
    ? `\n    <itunes:image href="${esc(feed.image_url)}"/>\n    <image>
      <url>${esc(feed.image_url)}</url>
      <title>${esc(feed.title)}</title>
      <link>${esc(feed.link)}</link>
    </image>`
    : "";

  return `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>${esc(feed.title)}</title>
    <link>${esc(feed.link)}</link>
    <description>${esc(feed.description)}</description>
    <language>${esc(feed.language)}</language>
    <itunes:explicit>${feed.explicit ? "yes" : "no"}</itunes:explicit>
    <atom:link href="${esc(opts.feedUrl)}" rel="self" type="application/rss+xml"/>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>${image}
${items}
  </channel>
</rss>
`;
}
