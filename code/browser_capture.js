// Browser bridge used through cua_repl, not a standalone Node script.
// Numerical parsing, calculations, reports and publishing use archive_and_report.py.
// Reproduction requires an authenticated Cesim tab and the documented cua API.
// Do not run while the user-requested pause is active.
async function saveVerifiedSnapshot(tab, fs, root, name, expected, sourceUrl) {
  const snapshot = await tab.playwright.domSnapshot();
  if (!snapshot.includes(expected)) throw new Error('Page identity mismatch: ' + name);
  await fs.writeFile(root + '/' + name + '.json', JSON.stringify({
    captured_at: new Date().toISOString(), source_url: sourceUrl || null, snapshot
  }, null, 2));
}
// Use the bound tab's domSnapshot. A document.body evaluate previously returned
// another tab's content; those early *_before files are retained in quarantine.
// Actual capture actions: read current decision pages, open budget tabs,
// select initial0/practice1/practice2 result views, read full PrintablePage.
// No fills, decision imports, group-copy clicks or submission were performed.
