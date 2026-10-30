# Hypothesis tests

**Question:** are the differences that the experiments find between two conditions real, or could they be noise?

**What is tested:** every comparison of two conditions in experiments 02 to 05: one feed against three per ETL stage (02), each index variant against no index (03), each batch size against production (04), and the cold cache against the warm one (05). Experiments 01 and 06 compare nothing. 07 compares two coefficients of a fit, not two samples, and its bootstrap intervals already answer the question.

**Method:**

1. **Shapiro-Wilk** [1] on each sample, to decide between a t-test and a rank test. Durations have a floor and a long right tail of retries and cold reads, so normality is the exception.
2. **Mann-Whitney U** [2] for every comparison. It compares the order of the observations, not their values, so it needs no normality and an outlier counts as one more rank. It also matches the medians that every experiment reports; a t-test would compare means.
3. **Holm's correction** [3] over all the comparisons at once, so that the chance of any false positive stays below 5 %.

Besides the p-value, each row gives `p_b_greater`, U divided by the number of pairs: the probability that a value of b is larger than one of a, the common language effect size [4]. 0.5 means no difference. The size of the difference is read from the medians and their bootstrap intervals, in each experiment's summary.

Shapiro-Wilk and Mann-Whitney come from SciPy [5]. Holm's correction is written by hand in `analyze.py`, following [3], because it is a few lines.

**Run:** the only analysis here that needs a third-party package, so it has its own environment.

    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
    venv/bin/python analyze.py results/hypothesis_YYYYMMDD

It reads the most recent raw CSV of each experiment, prints which ones to stderr, and writes `results/hypothesis_YYYYMMDD_normality.csv` and `results/hypothesis_YYYYMMDD_mannwhitney.csv`.

**Limits:** with thousands of runs, as in 02, even a tiny difference comes out significant, so significance only says that a difference exists, not that it matters. A sample that does not reject normality is not shown to be normal: the ones in 03 and 04 have 29 repetitions, too few for the test to see much. Mann-Whitney is valid either way, which is why it is used for every comparison instead of switching test case by case.

## References

1. S. S. Shapiro and M. B. Wilk. An analysis of variance test for normality (complete samples). *Biometrika*, 52(3-4):591-611, 1965.
2. H. B. Mann and D. R. Whitney. On a test of whether one of two random variables is stochastically larger than the other. *The Annals of Mathematical Statistics*, 18(1):50-60, 1947.
3. S. Holm. A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics*, 6(2):65-70, 1979.
4. K. O. McGraw and S. P. Wong. A common language effect size statistic. *Psychological Bulletin*, 111(2):361-365, 1992.
5. P. Virtanen et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. *Nature Methods*, 17:261-272, 2020. Functions used: [`scipy.stats.shapiro`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.shapiro.html) and [`scipy.stats.mannwhitneyu`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html).
