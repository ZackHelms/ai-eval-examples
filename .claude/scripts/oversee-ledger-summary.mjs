#!/usr/bin/env node
// oversee-ledger-summary.mjs — plain Node ESM, zero dependencies.
//
// Summarizes `.claude/metrics/oversee-ledger.jsonl`, the oversee wrap-up
// outcome ledger (see `.claude/skills/task-scoping.md`).
//
// Row schema — one JSON object per line (JSONL; no wrapping array):
//
//   {"date":"YYYY-MM-DD","plan":"<slug>","task":1,
//    "category":"docs|config|tests|mechanical-edit|pattern-follow|code|cross-system|debug|art|script",
//    "model":"haiku|sonnet|opus|fable","effort":"low|medium|high|xhigh",
//    "first_pass":true,"warm_retries":0,"escalated_to":null,
//    "overseer_fixes":0,"validation_failures":0,"haiku_viable_retro":false,
//    "cause":"<short reason when not clean, else empty>"}
//
// Usage: node .claude/scripts/oversee-ledger-summary.mjs [ledger-path]
//   ledger-path defaults to .claude/metrics/oversee-ledger.jsonl (relative to
//   the current working directory).
//
// Behavior:
//   - missing file, or a file with zero valid data rows -> print
//     "no ledger rows yet" and exit 0.
//   - blank lines are tolerated (skipped silently).
//   - a malformed line prints a warning to stderr and is skipped; the
//     summary never crashes on bad input.
//   - output: a fixed-width table grouped by category x model with columns
//     attempts, first-pass rate, mean warm_retries, escalations,
//     overseer_fixes; then one TOTAL line; then a count of rows where
//     haiku_viable_retro=true but the row's model was not haiku (the
//     over-provisioning signal).

import { readFileSync } from 'node:fs';

function main() {
  const ledgerPath = process.argv[2] || '.claude/metrics/oversee-ledger.jsonl';

  let raw;
  try {
    raw = readFileSync(ledgerPath, 'utf8');
  } catch {
    console.log('no ledger rows yet');
    process.exit(0);
  }

  const lines = raw.split('\n');
  const rows = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '') continue;
    try {
      const row = JSON.parse(trimmed);
      rows.push(row);
    } catch {
      console.error(`warning: skipping malformed ledger line: ${trimmed}`);
    }
  }

  if (rows.length === 0) {
    console.log('no ledger rows yet');
    process.exit(0);
  }

  const groups = new Map();

  for (const row of rows) {
    const category = row.category ?? 'unknown';
    const model = row.model ?? 'unknown';
    const key = `${category} ${model}`;
    if (!groups.has(key)) {
      groups.set(key, {
        category,
        model,
        attempts: 0,
        firstPassCount: 0,
        warmRetriesSum: 0,
        escalations: 0,
        overseerFixes: 0,
      });
    }
    const g = groups.get(key);
    g.attempts += 1;
    if (row.first_pass === true) g.firstPassCount += 1;
    g.warmRetriesSum += Number(row.warm_retries) || 0;
    if (row.escalated_to !== null && row.escalated_to !== undefined) {
      g.escalations += 1;
    }
    g.overseerFixes += Number(row.overseer_fixes) || 0;
  }

  const sortedGroups = [...groups.values()].sort((a, b) => {
    if (a.category !== b.category) return a.category < b.category ? -1 : 1;
    return a.model < b.model ? -1 : a.model > b.model ? 1 : 0;
  });

  const cols = [
    { key: 'category', header: 'category', width: 16 },
    { key: 'model', header: 'model', width: 10 },
    { key: 'attempts', header: 'attempts', width: 9 },
    { key: 'firstPassRate', header: 'first-pass', width: 11 },
    { key: 'meanWarmRetries', header: 'mean_retries', width: 13 },
    { key: 'escalations', header: 'escalations', width: 12 },
    { key: 'overseerFixes', header: 'overseer_fixes', width: 15 },
  ];

  function pad(value, width) {
    const s = String(value);
    return s.length >= width ? s : s + ' '.repeat(width - s.length);
  }

  function formatRow(values) {
    return cols.map((c) => pad(values[c.key], c.width)).join('');
  }

  console.log(formatRow(Object.fromEntries(cols.map((c) => [c.key, c.header]))));

  let totalAttempts = 0;
  let totalFirstPass = 0;
  let totalWarmRetries = 0;
  let totalEscalations = 0;
  let totalOverseerFixes = 0;

  for (const g of sortedGroups) {
    const firstPassRate =
      g.attempts > 0 ? `${Math.round((g.firstPassCount / g.attempts) * 100)}%` : 'n/a';
    const meanWarmRetries = g.attempts > 0 ? (g.warmRetriesSum / g.attempts).toFixed(1) : '0.0';
    console.log(
      formatRow({
        category: g.category,
        model: g.model,
        attempts: g.attempts,
        firstPassRate,
        meanWarmRetries,
        escalations: g.escalations,
        overseerFixes: g.overseerFixes,
      }),
    );
    totalAttempts += g.attempts;
    totalFirstPass += g.firstPassCount;
    totalWarmRetries += g.warmRetriesSum;
    totalEscalations += g.escalations;
    totalOverseerFixes += g.overseerFixes;
  }

  const totalFirstPassRate =
    totalAttempts > 0 ? `${Math.round((totalFirstPass / totalAttempts) * 100)}%` : 'n/a';
  const totalMeanWarmRetries =
    totalAttempts > 0 ? (totalWarmRetries / totalAttempts).toFixed(1) : '0.0';

  console.log(
    formatRow({
      category: 'TOTAL',
      model: '',
      attempts: totalAttempts,
      firstPassRate: totalFirstPassRate,
      meanWarmRetries: totalMeanWarmRetries,
      escalations: totalEscalations,
      overseerFixes: totalOverseerFixes,
    }),
  );

  const overProvisioned = rows.filter(
    (row) => row.haiku_viable_retro === true && row.model !== 'haiku',
  ).length;

  console.log(
    `\nhaiku_viable_retro=true but ran above haiku: ${overProvisioned} row(s) (over-provisioning signal)`,
  );
}

main();
