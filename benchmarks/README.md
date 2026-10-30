# Benchmarks

Experiments that measure Syndra in production and on a local copy of it. Each folder is a self-contained experiment following the same template: `README.md` (question, environment, how to run), `measure.sh` (takes the measurements and stores the raw data), `analyze.py` (statistics from the CSV) and `results/` (raw CSVs and environment metadata).

## Index

| # | Experiment | Question | Runs against | Status |
|---|---|---|---|---|
| 01 | [Subprocess startup](./01_subprocess_startup/) | How much of the per-source time is startup and how much is actual work? | production, read-only | Measured |
| 02 | [ETL latency](./02_etl_latency/) | How is latency split across the stages, how did it evolve, and how much does each feed add? | production history, read-only | Measured |
| 03 | [Per-ticker query indexes](./03_jsonb_gin/) | Which index does the per-ticker query need, from what size, and is the Bronze GIN of ADR 012 still used? | local copy of production data | Measured |
| 04 | [Inference resources](./04_inference_resources/) | How do time and memory of FinBERT change from one text at a time to batches? | local, deployed image | Measured |
| 05 | [API latency](./05_api_latency/) | How long does a request take under the load of one client, with the cache warm and cold? | production, 0.4 requests/s | Measured, needs a test key |
| 06 | [Production metrics](./06_production_metrics/) | How much memory, CPU and disk does production use against its limits, how much of the 05 latency is network, how fast does the TSDB grow, and what keeps the CPU busy at rest? | production history, read-only | Measured |
| 07 | [Cost of the ML stages](./07_ml_stage_cost/) | Why do the ML stages barely grow with the number of articles: what is fixed per run and what is per article? | production history and scheduler, read-only | Measured |

## Rules

1. **Measuring and analysing are separate steps.** Raw data is always kept, so the analysis can be repeated without measuring again.
2. **Every run records its own environment:** date, repository commit, container image, cores, memory and library versions.
3. **A CSV is never edited by hand.** If a data point is wrong, measure again.
4. **Fixed seed** in anything involving randomness, such as bootstrap resampling.
5. **Fixed repetition count, 30.** The first one is reported separately because of the cache effect: the first import pays for the disk read that later ones find in the page cache. Where an experiment cannot follow this rule (02 uses every recorded run; 05 measures hundreds of requests per run; 06 reads time series, which are not repetitions), its README says why.
6. **Only clean runs count.** If the environment file says `dirty_tree: yes`, the code that ran was not the recorded commit, so the run cannot be traced back to it and is not used. Files under `results/` and `docs/` do not count; any other change or new file does.

No machine address or credential is written into these files: the SSH target comes from `VPS_USER` and `VPS_IP` in the root `.env`, which is not in git, and API keys are passed through the environment or a git-ignored file. Copies of production data (03 and 04) hold scraped article text, so they live in `~/.cache/syndra-bench/` and never in the repository. Every query against production runs in a session forced read-only.

## Shared code

`lib/` holds what the experiments share, so each `measure.sh` and `analyze.py` only says what is particular to its experiment:

- `common.sh`: reading `.env`, SSH and read-only `psql` against the VPS, the environment header, and a checksum-verified vegeta.
- `stats.py`: nearest-rank percentiles and bootstrap intervals, standard library only.
- `api_targets.py` and `vegeta_csv.py`: the request lists of the API latency experiment and the conversion of vegeta's output into the benchmark CSV.

[`hypothesis_tests/`](./hypothesis_tests/) runs the significance tests across experiments 02 to 05: Shapiro-Wilk, then Mann-Whitney with Holm's correction. It is the only analysis that needs a third-party package, scipy, so it has its own `requirements.txt` and leaves the standard-library rule of `lib/` untouched.

**Not measured:** the API's capacity, the request rate at which it degrades. Measuring it means pushing the API until it fails, which on the production VPS would break the service and share the two cores with the ETL; it needs a clone of the VPS and is left as future work.

## Statistics

Every analysis makes the same choices, so they are written down once here.

- Times are summarised with the **median**, not the mean. One network retry or a busy core is enough to drag the mean away from the usual case.
- Each median has a 95 % **bootstrap** confidence interval, with 10,000 resamples and seed 2026 (Efron and Tibshirani, 1993). The code is in `lib/stats.py`.
- Percentiles are **nearest-rank**, so they are always a value that was actually measured (Hyndman and Fan, 1996, definition 1).
- When two conditions are compared, [`hypothesis_tests/`](./hypothesis_tests/) checks that the difference is not noise.

Each run leaves an environment file next to its CSV, with the commit, image, cores, memory and library versions. Those are the values to quote for a run, not the ones in this README.
