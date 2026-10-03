const fs = require('node:fs');
const crypto = require('node:crypto');
const root = 'app/web/static/vendor/';
const manifest = JSON.parse(fs.readFileSync(root + 'manifest.json', 'utf8'));
for (const file of fs.readdirSync(root).filter(f => f !== 'manifest.json')) {
  const actual = crypto.createHash('sha256').update(fs.readFileSync(root + file)).digest('hex');
  if (!manifest[file] || actual !== manifest[file].sha256) throw new Error('Unverified vendored file: '+file);
}
for (const file of Object.keys(manifest)) {
  if (!fs.existsSync(root + file)) throw new Error('Missing vendored file: '+file);
}
const packaged = fs.readFileSync('node_modules/dompurify/dist/purify.min.js');
if (!packaged.equals(fs.readFileSync(root + 'purify.min.js'))) throw new Error('DOMPurify differs from the locked package');
console.log('Vendored file hashes and locked DOMPurify match');
