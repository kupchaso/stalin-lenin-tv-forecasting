# Stalin and Lenin mentions on Russian television

Course forecasting project by **Купча Софья and Пальцева Ксения**.

We plan to forecast two daily quantities for Stalin and Lenin, separately for Channel One, NTV, Russia 1 and Russia 24:

- The number of surname occurrences across all archived broadcasts.
- The number of broadcasts containing at least one surname occurrence.

The forecast horizon is one month after the latest available date. The current dataset ends on **October 2, 2026**; the forecast runs from **October 3 to November 2, 2026**, inclusive.

## Start here

- [Project proposal (PDF)](output/proposal/forecasting_proposal.pdf) and [editable LaTeX source](output/proposal/forecasting_proposal.tex).
- [Executed daily forecasting notebook](output/stalin_russia1/stalin_russia1_daily_forecast.ipynb): four models, historical evaluation and ten figures.
- [Detailed methodology and pilot results](output/stalin_russia1/README.md).
- [Daily forecasts from all four models](output/stalin_russia1/forecast_daily_all_models.csv).
- [Daily targets for both people and all four channels](data/tv_daily_targets.csv.gz), including broadcasts with mentions.
- [Exploratory data notebook](data_collection/notebooks/mentions_over_time.ipynb).

**The completed forecasting experiment currently covers Stalin on Russia 1.** Forecasting Lenin, the remaining channels and broadcasts with mentions is planned work. The prepared daily target table covers those series; it is not a set of completed forecasts.

## Data

The saved dataset comes from [GDELT](https://gdeltproject.org/), including its [television archive files](https://storage.googleapis.com/data.gdeltproject.org/gdeltv3/iatv/visualexplorer/). It covers January 1, 2023 through October 2, 2026 (Europe/Moscow).

The repository includes compressed exports of broadcast metadata and candidate counts, daily coverage, mention contexts and cached exploratory tables. These files are sufficient to reproduce the current count-based forecasting experiment without Google Cloud credentials.

`data/tv_daily_targets.csv.gz` has one row per channel and calendar day. `stalin_mentions` and `lenin_mentions` count matched surname tokens; `stalin_broadcasts` and `lenin_broadcasts` count available broadcasts with at least one match. The latter counts are bounded by `available_broadcasts`. All four target columns are blank on days without a complete inventory and all listed transcripts. Such days are missing observations, not zero counts.

Automatic transcript matches are candidates, not fully verified references to the historical individuals. The archive does not establish complete coverage of the entire television schedule. These limitations are documented in the pilot report.

Full original transcripts, inventories, the SQLite database, lecture extracts and cloud UI screenshots are retained in the local project folder but excluded from Git. Their total size is about 2.3 GB; the SQLite file alone exceeds GitHub's ordinary 100 MB file limit. Collection scripts and compressed exports remain in the repository.

## Models and evaluation

The preliminary experiment compares:

1. A constant-rate Gamma-Poisson baseline.
2. A constant-mean negative-binomial model with additional dispersion.
3. A negative-binomial regression with a time trend and partially pooled month and weekday effects.
4. Model 3 with a latent level following a random walk, estimated by a modular particle filter.

The fourth model uses a conditional/modular approximation, not a full joint Bayesian posterior for static parameters and latent states. Historical evaluation uses multiple expanding-window forecast origins. The report gives RMSE, CRPS, interval coverage and model comparisons; extensions do not improve every metric.

## Reproduce

Use Python 3.12 and install the recorded dependencies:

```sh
python -m pip install -r requirements.txt
```

Open the daily forecasting notebook and run its cells. Saved historical evaluations are reused by default; set `RUN_BACKTEST = True` to recompute them. The full model script can also be run from the repository root:

```sh
python analysis/stalin_models.py
python analysis/verify_forecast.py
python analysis/prepare_tv_targets.py
```

The LaTeX proposal can be compiled with a standard TeX installation:

```sh
pdflatex -output-directory=output/proposal output/proposal/forecasting_proposal.tex
```

`data_collection/` also contains the original acquisition workflow and broader exploratory work, including web data and Trump mentions collected before this project's scope was narrowed. They are not additional forecast targets in the current proposal.
