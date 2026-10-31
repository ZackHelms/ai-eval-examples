"""Trial-count statistics: a lower bound on a pass rate from N trials.

``lower_bound`` is the one-sided Clopper-Pearson bound used by the trial
stages (``.claude/notes/20261031-trial-statistics.md``): the true pass rate
is at least this value with the given confidence.
"""

from __future__ import annotations

import math

# Bisection halves [0, 1] each step; 60 steps is far below float resolution.
_BISECTION_STEPS = 60


def _upper_tail(passes: int, n: int, p: float) -> float:
    """Return P(X >= passes) for X ~ Binomial(n, p), with 0 < p < 1.

    Terms are summed in log space so n in the hundreds or thousands doesn't
    overflow ``math.comb`` products or underflow ``p ** i``.
    """
    log_p = math.log(p)
    log_q = math.log1p(-p)
    terms = []
    for i in range(passes, n + 1):
        log_comb = math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
        terms.append(math.exp(log_comb + i * log_p + (n - i) * log_q))
    return math.fsum(terms)


def lower_bound(passes: int, n: int, confidence: float = 0.95) -> float:
    """Return the one-sided Clopper-Pearson lower bound on a pass rate.

    The bound is the p solving ``P(X >= passes | n, p) = 1 - confidence``.
    ``passes == 0`` gives 0.0, and so does ``n == 0``: no trials is no
    evidence. When ``passes == n`` the bound has the closed form
    ``(1 - confidence) ** (1 / n)``.

    Raises ValueError unless ``0 <= passes <= n`` and ``0 < confidence < 1``.
    """
    if not 0 < confidence < 1:
        raise ValueError(f"confidence must be between 0 and 1 exclusive, got {confidence}")
    if n < 0 or passes < 0 or passes > n:
        raise ValueError(f"need 0 <= passes <= n, got passes={passes}, n={n}")
    if n == 0 or passes == 0:
        return 0.0
    alpha = 1 - confidence
    if passes == n:
        return alpha ** (1 / n)
    # The tail is increasing in p, so bisect for where it crosses alpha.
    low, high = 0.0, 1.0
    for _ in range(_BISECTION_STEPS):
        mid = (low + high) / 2
        if _upper_tail(passes, n, mid) < alpha:
            low = mid
        else:
            high = mid
    return (low + high) / 2
