"""Statistics shared by the analyze.py scripts.

Standard library only, so any python3 can rerun an analysis without installing
anything. Every random draw goes through an explicitly seeded generator.

Usage: import stats, after adding benchmarks/lib to sys.path.
"""
import math

# Fixed seed and resample count, so rerunning an analysis gives the same intervals.
SEED = 2026
RESAMPLES = 10_000


def percentile(sorted_values, p):
    """Nearest-rank percentile: always an observed value, never an interpolation.

    It is the inverse of the empirical distribution function: the smallest value
    with at least p % of the sample at or below it.
    Reference: Hyndman and Fan (1996), Sample Quantiles in Statistical Packages, definition 1.

    Args:
        sorted_values: the sample, already sorted in ascending order.
        p: percentile between 0 and 100.
    """
    # k is a 1-based rank; max() makes p = 0 return the minimum instead of index -1.
    k = max(1, math.ceil(p / 100 * len(sorted_values)))
    return sorted_values[k - 1]


def _interval(estimates):
    """Return the 2.5 and 97.5 percentiles of the bootstrap estimates.

    This is the percentile method. The list is sorted in place.
    Reference: Efron and Tibshirani (1993), An Introduction to the Bootstrap.
    """
    estimates.sort()
    # With 10,000 estimates this leaves out 250 on each side.
    return estimates[int(0.025 * len(estimates))], estimates[int(0.975 * len(estimates)) - 1]


def ci95(values, statistic, rng, resamples=RESAMPLES):
    """95 % bootstrap confidence interval of statistic(values).

    Each resample draws len(values) values with replacement.
    Reference: Efron and Tibshirani (1993), An Introduction to the Bootstrap.

    Args:
        values: the observed sample.
        statistic: function from a list to a number, such as statistics.median.
        rng: a seeded random.Random, see https://docs.python.org/3/library/random.html

    Returns:
        A (low, high) tuple.
    """
    n = len(values)
    return _interval([statistic(rng.choices(values, k=n)) for _ in range(resamples)])


def ci95_percentiles(values, ps, rng, resamples=RESAMPLES):
    """Bootstrap intervals for several percentiles, sharing each resample.

    Sorting each resample once and reading every percentile from it is cheaper
    than one bootstrap per percentile.

    Returns:
        A dict from each p in ps to its (low, high) tuple.
    """
    n = len(values)
    estimates = {p: [] for p in ps}
    for _ in range(resamples):
        sample = sorted(rng.choices(values, k=n))
        for p in ps:
            estimates[p].append(percentile(sample, p))
    return {p: _interval(estimates[p]) for p in ps}


def ci95_each(values, statistic, rng, resamples=RESAMPLES):
    """Bootstrap intervals for a statistic that returns several estimates at
    once, such as the two coefficients of a fit, sharing each resample.

    Returns:
        A list of (low, high) tuples, in the order the statistic returns its estimates.
    """
    n = len(values)
    draws = [statistic(rng.choices(values, k=n)) for _ in range(resamples)]
    return [_interval([draw[i] for draw in draws]) for i in range(len(draws[0]))]


def ci95_difference(a, b, statistic, rng, resamples=RESAMPLES):
    """Bootstrap interval of statistic(b) - statistic(a), resampling each group.

    The groups are resampled independently, each with its own size. If the
    interval excludes zero, the difference is not resampling noise.

    Returns:
        A (low, high) tuple.
    """
    na, nb = len(a), len(b)
    return _interval([
        statistic(rng.choices(b, k=nb)) - statistic(rng.choices(a, k=na))
        for _ in range(resamples)
    ])
