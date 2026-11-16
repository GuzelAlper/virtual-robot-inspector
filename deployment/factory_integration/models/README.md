# Final models

The installer expects exactly these trained files in this directory:

- `best_gauge_locator.pt` — finds the gauge in the full camera frame;
- `best_gauge_distribution_reader.pt` — reads the normalized needle position.

Only the final inference weights are versioned. Training datasets, notebooks,
intermediate checkpoints and generated predictions are intentionally excluded.
