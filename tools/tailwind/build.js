// Precompile Tailwind for each page and inline it between the tailwind markers,
// then regenerate the meta CSP script-src hashes for every inline <script> and inline
// event-handler attribute (so the CSP needs no 'unsafe-inline').
// Usage: npm install && npm run build   (re-run after changing classes in the HTML)
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const pages = [
  path.resolve(__dirname, '../../web_studio/index.html'),
  path.resolve(__dirname, '../../web_studio/download/AURA-REC.html'),
];
const START = '<!-- tailwind:start -->';
const END = '<!-- tailwind:end -->';
const bin = path.join(__dirname, 'node_modules/.bin/tailwindcss');

const unescapeAttr = (v) => v.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const sha = (t) => "'sha256-" + crypto.createHash('sha256').update(t, 'utf8').digest('base64') + "'";

function applyCspHashes(html) {
  const scripts = [...html.matchAll(/<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1]).filter((t) => t.trim());
  const handlers = [...html.matchAll(/\son[a-z]+="([^"]*)"/g)].map((m) => unescapeAttr(m[1]));
  const hashes = [...new Set([...scripts, ...handlers].map(sha))];
  return html.replace(/(script-src )([^;"]*)/, (_, head, body) => {
    const kept = body.split(/\s+/).filter((t) => t && t !== "'unsafe-inline'" && t !== "'unsafe-hashes'" && !t.startsWith("'sha256-"));
    return head + [...kept, "'unsafe-hashes'", ...hashes].join(' ');
  });
}

for (const page of pages) {
  const css = execFileSync(bin, [
    '-c', path.join(__dirname, 'tailwind.config.js'),
    '-i', path.join(__dirname, 'input.css'),
    '--content', page, '--minify',
  ], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  let html = fs.readFileSync(page, 'utf8');
  const a = html.indexOf(START), b = html.indexOf(END);
  if (a < 0 || b < 0) throw new Error('markers missing in ' + page);
  html = html.slice(0, a + START.length) + '\n  <style>' + css.trim() + '</style>\n  ' + html.slice(b);
  html = applyCspHashes(html);
  fs.writeFileSync(page, html);
  console.log(path.basename(page), (css.length / 1024).toFixed(1) + ' KB');
}
