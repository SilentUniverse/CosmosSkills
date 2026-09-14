const { spawnSync } = require('node:child_process');
const path = require('node:path');
const report = path.resolve(process.argv[2]);
const cli = path.join(path.dirname(require.resolve('@playwright/test/package.json')), 'cli.js');
const result = spawnSync(process.execPath, [cli, 'test'], { stdio: 'inherit', env: {
  ...process.env, COSMOS_UI_REPORT: report, COSMOS_RUN_ID: path.basename(path.dirname(report)),
  COSMOS_UI_OUTPUT: path.join(path.dirname(report), 'browser-artifacts')
} });
process.exit(result.status === null ? 125 : result.status);
