const { readdirSync, readFileSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const modules = require('./js-modules.cjs');

// Syntax: the modules as modules (strict mode included), the classic scripts
// with node itself.
for (const file of readdirSync('app/web/static').filter(f => f.endsWith('.js')).sort()) {
  if (modules.THIRD_PARTY.has(file)) continue;
  if (modules.sourceTypeOf(file) === 'script') {
    const result = spawnSync(process.execPath, ['--check', 'app/web/static/' + file], {stdio: 'inherit'});
    if (result.status !== 0) process.exit(1);
    continue;
  }
  try {
    modules.parse(file, readFileSync('app/web/static/' + file, 'utf8'));
  } catch (error) {
    console.error(`app/web/static/${file}: ${error.message}`);
    process.exit(1);
  }
}
// The module graph: imports resolve, the layering holds, no cycle is read at load.
modules.main();
// The CSP runs no inline event handler; controls name registered ones instead.
require('./check-inline-handlers.cjs').main();
require('./check-html-escaping.cjs').main();
// No em or en dashes in the text the scripts build (Norwegian copy rule).
require('./check-copy-dashes.cjs').main();

// ESLint last, because its API is asynchronous. Errors and warnings both fail
// the check: a warning that passes is one nobody fixes.
(async () => {
  const { ESLint } = require('eslint');
  const eslint = new ESLint();
  const results = await eslint.lintFiles(['app/web/static']);
  const output = (await eslint.loadFormatter('stylish')).format(results);
  if (output) console.log(output);
  const errors = results.reduce((n, r) => n + r.errorCount + r.fatalErrorCount, 0);
  const warnings = results.reduce((n, r) => n + r.warningCount, 0);
  if (errors || warnings) {
    console.error(`ESLint: ${errors} error(s), ${warnings} warning(s) in app/web/static`);
    process.exit(1);
  }
  console.log(`ESLint passed for ${results.length} files in app/web/static`);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
