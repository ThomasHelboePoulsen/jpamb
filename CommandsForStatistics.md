# JPAMB evaluation commands

Run these commands from the repository root in WSL.

## Run all 16 configurations

```bash
source .jpamb-eval/bin/activate
python benchmark_runner.py --repetitions 3 --jpamb-iterations 3 --method-timeout 20 \
  --csv results/ablation.csv --output results/ablation.html
```

This runs each configuration three times, with three JPAMB iterations per run
and a 20-second deadline per method iteration. The CSV and its
`results/ablation.runs.jsonl` companion hold the raw results. Reusing the CSV
path appends runs.

Open the ON/OFF comparison table in your Windows browser.

```bash
explorer.exe "$(wslpath -w "$PWD/results/ablation.html")"
```

## Compare selected configurations

This compares all components enabled with dynamic structure disabled.

```bash
python benchmark_runner.py --repetitions 3 --jpamb-iterations 3 --method-timeout 20 \
  --config all-enabled --config no-dynamic-structure \
  --csv results/selected.csv --output results/selected.html
```

Use `--config no-static,no-dictionary` to turn both components off in one
configuration. Add `--filter 'Randomness'` to run only matching methods.
Use the same method filter and JPAMB iteration count as your friend when
comparing scores.

## Show a table from saved results

The first command prints an aligned terminal table. The second saves an HTML
table with searchable per-method details. Both read existing files.

```bash
python benchmark_runner.py --from-saved results/ablation.csv

python benchmark_runner.py --from-saved results/ablation.csv --all-methods \
  --output results/ablation-details.html
```

Use `results/all-enabled_20s.csv` as the input to read your earlier all-enabled
run. Keep each CSV next to its `.runs.jsonl` companion.

## Run JPAMB directly

Run once with all components enabled, save ten iterations, or check the array
method on its own.

```bash
jpamb analyse dynamic-coverage-analysis --timeout 20
jpamb analyse dynamic-coverage-analysis --iterations 10 --timeout 20 \
  --csv results/all-enabled-direct.csv
jpamb analyse dynamic-coverage-analysis --filter arraySumIsLarge \
  --iterations 1 --timeout 20
```

Add `--no-static`, `--no-dictionary`, `--no-syntactic-structure`, or
`--no-dynamic-structure` to disable a component in a direct run.
