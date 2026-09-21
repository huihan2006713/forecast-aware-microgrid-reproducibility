# A Forecast-Aware Computational Optimization Framework for Microgrid Procurement and Battery Scheduling with Contract Revision Costs
## Reproducibility package

Companion code for the paper "A Forecast-Aware Computational Optimization
Framework for Microgrid Procurement and Battery Scheduling with Contract
Revision Costs".

### Contents
- `code/`: pipeline scripts.
  - `data_build.py` rebuilds all derived 10-minute data files from the four
    official attachments (see Data provenance below).
  - `dayahead.py` implements the day-ahead experiment (Table 2, Figure 1).
  - `revision.py` implements the contract-revision experiment (Tables 3-5,
    Figure 2).
  - `revision_full.py`, `sensitivity_alpha.py`, `sensitivity_kappa.py`,
    `da_alpha_sweep.py`, `jan_all_alpha.py`, `jan_save.py`, and
    `stats_two_release.py` run the full evaluation, the sensitivity sweeps,
    January checks, and the solver statistics.
  - `regen_figs.py` regenerates Figures 1-2.
- `results/`: derived results (JSON/CSV) used in the manuscript, including
  `tariff_schedule_144.csv`, the complete 10-minute tariff reported by the
  benchmark.
- `hashes.json`: SHA-256 hashes of the four official attachments and of the
  derived data files.
- `requirements.txt`: pinned dependencies.

### Environment
Python 3.12.10, NumPy 2.3.5, SciPy 1.17.0 (bundled HiGHS 1.8.0), pandas 2.2.3,
openpyxl, Windows 11, Intel Core i7-14650HX, 32 GB RAM.

### Data provenance
The raw records are the four attachments of Problem C of the 2025 China
Undergraduate Mathematical Contest in Modeling (CUMCM): Attachment 1
(time-of-use tariff), Attachment 2 (2025 10-minute load and photovoltaic
output), Attachment 3 (photovoltaic forecast archive released at 00:00, 06:00,
12:00 and 18:00 with hourly resolution) and Attachment 4 (2025 real-time
tariff). They are obtained from the official problem archive at
https://www.mcm.edu.cn/html_cn/node/03c91a444e62eee81a3740fa97a461a6.html
(accessed 21 September 2026). This repository does not redistribute the
original competition records.

### Reproduction
1. Clone the repository and create a Python 3.12 environment.
2. Install the pinned dependencies with `python -m pip install -r requirements.txt`.
3. Download the four official attachments and place `附件1.xlsx` through
   `附件4.xlsx` in a new `raw_data/` directory at the repository root.
4. From the repository root, run:

   ```bash
   python code/data_build.py
   python code/dayahead.py linear
   python code/revision_full.py
   python code/sensitivity_alpha.py
   python code/sensitivity_kappa.py
   python code/da_alpha_sweep.py
   python code/jan_all_alpha.py
   python code/jan_save.py
   python code/stats_two_release.py
   python code/regen_figs.py
   ```

Processed data are written to `data/`, numerical outputs to `results/`, and
figures to `figures/`. The printed totals reproduce Tables 2-5 and Figures 1-2
of the manuscript. Use `hashes.json` to verify the downloaded attachments and
the rebuilt data files.
Solver tie-breaking can shift the emergency component of the 334-day totals by
at most 0.1% relative to the numbers quoted in the manuscript; all reported
conclusions are unaffected.
