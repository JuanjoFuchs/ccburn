# Prediction Accuracy Research

## Problem Statement

The depletion projection ("depletes at X") is unstable throughout the month. It keeps shifting closer as the user actively consumes budget, rather than converging early to an accurate date. Users expect that with weeks of historical data, the prediction should stabilize.

## Current Implementation

`src/ccburn/utils/calculator.py` — `calculate_burn_rate()` uses **least-squares linear regression** over all snapshots from the window start.

- X-axis: wall-clock hours from first data point
- Y-axis: utilization percentage (0-100)
- Slope = burn rate in %/hour
- Depletion = `now + (100 - current_util) / slope`

## Observed Data (March 2026, Enterprise $1,300/month)

```
Actual milestones:
  10%: 03/02 22:00
  20%: 03/03 19:00
  30%: 03/04 21:00
  40%: 03/06 19:00
  50%: 03/09 17:00
  60%: 03/11 18:00
  70%: 03/12 15:00
  80%: 03/16 14:00
  85%: 03/16 19:00
  90%: 03/16 21:00
  95%: 03/17 16:00
```

Usage pattern is **bursty**: heavy during work hours (~10h/day), zero at night, multi-day weekend gaps.

Major idle gaps in the data:
```
02/27 03:31 -> 02/27 16:19 (13h gap)
02/27 22:01 -> 03/02 15:29 (65h gap)
03/03 23:37 -> 03/04 13:46 (14h gap)
03/06 19:02 -> 03/09 16:06 (69h gap)  <-- weekend
03/12 20:54 -> 03/16 14:33 (90h gap)  <-- long weekend
```

## How the Prediction Drifted

Simulated retroactive predictions (what each method would have said at each checkpoint):

```
When              Now  Target | Actual |       LinReg      Decay48       Simple
03/02 20:00        6%    10%  |    2h  |        n/a     3h(+1h)    28h(+26h)
03/03 14:00       14%    20%  |    5h  |   4h(-1h)    10h(+5h)    27h(+22h)
03/03 20:00       23%    30%  |   25h  |  12h(-13h)   11h(-14h)   20h(-5h)
03/09 18:00       51%    60%  |   48h  |  33h(-15h)   39h(-9h)    37h(-11h)
03/10 16:00       57%    60%  |   26h  |  10h(-16h)   11h(-15h)   11h(-15h)
03/12 15:00       70%    80%  |   95h  |  39h(-56h)   42h(-53h)   39h(-56h)
03/16 17:00       83%    85%  |    2h  |   8h(+6h)    11h(+9h)     9h(+7h)
03/17 13:00       92%    95%  |    3h  |  10h(+7h)    13h(+10h)   11h(+8h)
```

Mean absolute error:
- Linear regression: 16.5h
- Exp decay (48h half-life): 14.5h
- Simple average (util/elapsed): 18.8h

## Methods Tested

### 1. Linear Regression (current)

Full-window least-squares regression over all data points.

**Problem**: The regression slope is dominated by idle gaps. During a 90h weekend gap, the slope gets diluted. New active data points barely move the needle because the denominator (total time span) is huge.

Rate evolution over the month:
```
03/03: 0.59%/hr  (heavy initial usage)
03/05: 0.65%/hr  (still ramping)
03/09: 0.27%/hr  (69h weekend gap halved the rate)
03/10-03/17: ~0.24%/hr  (rate barely moves despite active usage)
```

### 2. Exponential Decay Weighted Regression

Weighted least-squares where recent points have higher weight. Weight = `exp(-decay * (t_last - t))`.

Tested half-lives: 12h, 24h, 48h, 72h, 96h.

**Finding**: Short half-lives (12h, 24h) give negative rates during idle periods (recent flat data dominates). Longer half-lives (48h, 72h) are marginally better than linear regression but not meaningfully so. The fundamental problem (idle gaps) remains.

### 3. Holt-Winters Exponential Smoothing

`statsmodels.tsa.holtwinters.ExponentialSmoothing` with additive trend and seasonal components.

Tested with daily (24h) and weekly (168h) seasonal periods.

**Problem**: Requires evenly-spaced data. Forward-filling gaps creates long flat stretches that the model learns as "the series plateaus." Result: Holt-Winters predicted NO depletion within 500 hours because it learned the idle pattern too well.

With daily seasonality (sp=24):
```
Next 12h forecast: 85.7, 86.3, 87.0, 86.4, 87.1, 87.4, 87.5, 87.5, 87.5, 87.5, 87.5, 87.5
```

### 4. Simple Average

`rate = current_utilization / elapsed_hours_since_window_start`

No regression — just total usage divided by total time. Similar accuracy to linear regression (18.8h MAE vs 16.5h). Simpler but equally affected by idle gaps.

## Root Cause Analysis

The core issue is not the algorithm — it's that **usage is bursty with multi-day gaps**:

1. During active sessions: actual burn rate is ~1-2%/hr
2. Full-window average: ~0.24%/hr (diluted by 160+ hours of idle time)
3. The 0.24%/hr rate projects depletion ~5x further out than reality during active use
4. As the user keeps burning, the prediction slowly catches up but is always lagging

No single-rate linear model can accurately predict depletion for this usage pattern because the rate is fundamentally bimodal (active vs idle).

## Ideas Not Yet Explored

### Gap-aware regression
Skip idle gaps (>N hours) in the x-axis, only count "active" hours. Would give a rate closer to the active-session rate. Risk: overestimates depletion speed during upcoming idle periods.

### Dual-rate model
Separate "active hours rate" and "idle hours rate" (or just "hours per day active"). Predict based on expected active hours remaining in the window.

### Show uncertainty range
Instead of a single depletion date, show a range like "depletes Mar 20-24" based on the spread between active-rate and average-rate projections.

### Better gap handling for Holt-Winters
Instead of forward-fill, interpolate only during expected active hours (e.g., 9am-7pm weekdays). Would give Holt-Winters cleaner signal about the daily/weekly seasonality.

### External forecasting API
Nixtla TimeGPT has a free tier and handles bursty time series well. Discarded because it adds an external API dependency.

### Amazon Chronos-T5-Tiny
8M parameter transformer, runs locally, zero-shot forecasting. Discarded because it adds PyTorch + transformers (~500MB+ dependencies) — too heavy for a CLI tool.

## Dependencies Installed During Research

- `statsmodels` — used for Holt-Winters testing, not yet used in production
- `numpy` — used for weighted regression testing (already an indirect dependency)

## Files

- `src/ccburn/utils/calculator.py` — current linear regression implementation
- `tests/test_calculator.py` — existing burn rate tests
- `tests/test_chart.py` — display window tests (depleted logic)

## Decision

Parked for now. The current linear regression works but is inaccurate for bursty usage. The prediction naturally converges as the window progresses but is unreliable in the first half of the month. Future work should focus on gap-aware regression or a dual-rate model as the most promising lightweight approaches.
