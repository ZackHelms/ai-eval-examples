# Trial statistics: what N trials can prove

Reference for choosing trial counts (rubric `script-fix-v0`'s stages: see
`.claude/plans/grader-01.global-rubric-design.md` § Trial stages). The
bounds are one-sided 95% lower bounds on the true pass rate (Clopper–Pearson).
The lower bound solves P(X ≥ k | p) = 0.05; for k = n it is 0.05^(1/n).
`scriptfix.stats.lower_bound` computes it (`30-grade-trials.ps1 -Report`
prints it per case and subject).

| Observed | True rate likely ≥ |
|---|---|
| 9/10 | 61% |
| 10/10 | 74% |
| 59/59 | 95% |
| 95/100 | 90% (89.8%) |
| 99/100 | 95% |

**Power:**

- **A 10-trial screen** (a case passes only at 10/10):
  - a subject truly at 80% fails it 89% of the time (1 − 0.8¹⁰);
  - a subject truly at 95% still fails it 40% of the time, so a failed
    screen triggers a full run, not a rejection.
- **The full bar, ≥95/100:**
  - a subject at 98% fails it about 2% of the time;
  - a subject at 90% passes it about 6% of the time;
  - in between, it's close to a coin toss.
- **At suite scale:** each case truly at 97% fails the bar on about 8% of
  full runs (P(≥ 6 failures in 100)). Across 50 such cases that's about 4
  false regressions per run. Requiring a second failed full run brings it
  under 1% per case (0.08² ≈ 0.6%).
- **Proving a true rate ≥95%** takes ≤1 failure in 100, or 59 passes in a
  row.
