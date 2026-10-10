// Precompile Tailwind for each page and inline it between the tailwind markers.
// Usage: npm install && npm run build   (re-run after changing classes in the HTML)
const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const pages = [
  path.resolve(__dirname, '../../web_studio/index.html'),
  path.resolve(__dirname, '../../web_studio/download/AURA-REC.html'),
];
const START = '<!-- tailwind:start -->';
const END = '<!-- tailwind:end -->';
const bin = path.join(__dirname, 'node_modules/.bin/tailwindcss');

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
  fs.writeFileSync(page, html);
  console.log(path.basename(page), (css.length / 1024).toFixed(1) + ' KB');
}
