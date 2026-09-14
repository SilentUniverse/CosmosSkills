const fs = require('node:fs');

function steps(rows) {
  return rows.map(step => ({ title: step.title, category: step.category, error: step.error,
    duration: step.duration, steps: steps(step.steps) }));
}

module.exports = class EvidenceReporter {
  constructor() { this.errors = []; }
  onBegin(config, suite) { this.suite = suite; }
  onError(error) { this.errors.push(error); }
  onEnd(result) {
    const specs = this.suite.allTests().map(test => ({ title: test.title,
      tests: [{ expectedStatus: test.expectedStatus, results: test.results.map(attempt => ({
        status: attempt.status, errors: attempt.errors, retry: attempt.retry,
        steps: steps(attempt.steps), attachments: attempt.attachments.map(item => ({name: item.name, path: item.path}))
      })) }] }));
    fs.writeFileSync(process.env.COSMOS_UI_REPORT, JSON.stringify({ schema_version: 1,
      kind: 'cosmos-playwright', run_id: process.env.COSMOS_RUN_ID,
      status: result.status, errors: this.errors, suites: [{specs}] }));
  }
};
