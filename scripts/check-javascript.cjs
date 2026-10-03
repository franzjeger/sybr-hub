const { readdirSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
for (const file of readdirSync('app/web/static').filter(f => f.endsWith('.js'))) {
  const result = spawnSync(process.execPath, ['--check', 'app/web/static/' + file], {stdio: 'inherit'});
  if (result.status !== 0) process.exit(1);
}
// A global declared in two scripts: the later one silently replaces the other.
require('./js-globals.cjs').main();
// The CSP runs no inline event handler; controls name registered ones instead.
require('./check-inline-handlers.cjs').main();
require('./check-html-escaping.cjs').main();
// No em or en dashes in the text the scripts build (Norwegian copy rule).
require('./check-copy-dashes.cjs').main();

// ESLint last, because its API is asynchronous. Errors fail the check;
// warnings (unused locals) are printed and do not.
(async () => {
  const { ESLint } = require('eslint');
  const eslint = new ESLint();
  const results = await eslint.lintFiles(['app/web/static']);
  const output = (await eslint.loadFormatter('stylish')).format(results);
  if (output) console.log(output);
  const errors = results.reduce((n, r) => n + r.errorCount + r.fatalErrorCount, 0);
  const warnings = results.reduce((n, r) => n + r.warningCount, 0);
  if (errors) {
    console.error(`ESLint: ${errors} error(s) in app/web/static`);
    process.exit(1);
  }
  console.log(`ESLint passed for ${results.length} files in app/web/static (${warnings} warning(s))`);
})().catch(error => {
  console.error(error);
  process.exit(1);
});
