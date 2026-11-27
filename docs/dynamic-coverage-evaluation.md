# Dynamic coverage evaluation

Run these commands from the repository root with JPAMB and the dynamic solution
installed in the same environment. See [Python setup](python.md) for installation.

```bash
jpamb analyse dynamic-coverage-analysis
jpamb analyse dynamic-coverage-analysis --no-static
jpamb analyse dynamic-coverage-analysis --no-dictionary
jpamb analyse dynamic-coverage-analysis --no-syntactic-structure
jpamb analyse dynamic-coverage-analysis --no-dynamic-structure
```

All four components are enabled by default. An environment variable set to
`1`, `true`, or `yes` (case-insensitive) disables the corresponding component.
A CLI flag disables its component even if the environment leaves it enabled.
Each invocation passes the effective settings to its analyzer subprocesses.

| CLI flag | Environment setting | Disabled guidance |
| --- | --- | --- |
| `--no-static` | `DISABLE_STATIC_SEEDS` | Static Smith seeds and static mutation targets |
| `--no-dictionary` | `DISABLE_DICTIONARY` | Source literals, dictionary expansion, and associated arithmetic guidance |
| `--no-syntactic-structure` | `DISABLE_SYNTACTIC_STRUCTURE` | Initial Smith structure inferred from source |
| `--no-dynamic-structure` | `DISABLE_DYNAMIC_STRUCTURE` | Structure expansion and targeted input generation from Smith reads |

Source-inferred structure and execution-time discovery are independent. The
interpreter and coverage-based fuzzing run with all four components disabled
too. Ordinary evaluations start fresh. Step-wise checkpoints include the
effective settings and the experiment configuration.

## Saving a run

```bash
jpamb analyse dynamic-coverage-analysis --iterations 10 --csv results/all-enabled.csv
jpamb analyse dynamic-coverage-analysis --iterations 10 --no-syntactic-structure --csv results/no-syntactic-structure.csv
jpamb analyse dynamic-coverage-analysis --iterations 10 --no-static --no-dictionary --csv results/no-static-no-dictionary.csv
```

JPAMB prints its usual method, total, and category score tables. The evaluation
table adds coverage, observed outcomes, and analysis time. `--iterations`
controls JPAMB's internal method iterations and defaults to three. Exploratory
runs can use any positive count. The official `--report` validation still
requires three iterations and applies the existing report rules.

The optional CSV has one row per attempted method and internal iteration.
`run_id` identifies the JPAMB invocation, `iteration` is one-based, and
`repetition` is the one-based invocation number assigned by the comparison
runner when used. The four Boolean columns state the effective settings.
Instructions count distinct bytecode instructions executed in the identified
method, divided by its own instruction count. `observed_outcomes` is a JSON
array of distinct outcomes seen during that execution. The `*` outcome is
JPAMB's nontermination query, while a row with status `timeout` means the
analyzer process exceeded its deadline.

`analysis_seconds` measures wall time for analyzer setup, bytecode loading,
guidance, input generation, initial seed execution, and fuzzing. It ends before
serialization and output. `jpamb_absolute_ns` and `jpamb_relative_db` are
runit's subprocess timing and calibrated relative timing. `score` uses the
official categories fitted over the invocation and that iteration's
predictions. The mean of a method's iteration scores gives its official
per-method score.

Keep each CSV with its companion `<name>.runs.jsonl`. The versioned companion
contains one JSON object per run with its status, identifiers, settings,
requested iterations, expected methods, timing, and any error.
`evaluation_elapsed_seconds` measures the CLI from entry to scoring completion.
The runner adds `elapsed_seconds` for the entire JPAMB subprocess, including
startup and output. The `official` object records the suite score and timing, method scores and timing, category
breakdowns, expected outcomes, report validity, and the native JPAMB report
S-expression with predictions and calibrations. Missing values are blank in the
CSV or null in JSON. The companion represents non-finite official numerical
values as strings. Reusing the same CSV path appends runs after validating both
files.

## Comparing independent repetitions

Omit `--config` to evaluate all 16 configurations. To select configurations,
repeat `--config` with `all-enabled`, `all-disabled`, or a comma-separated list
of component flags without the leading dashes. The runner sets the four
components from this selection independently of inherited disable variables.

```bash
python benchmark_runner.py --repetitions 3 --jpamb-iterations 3 --method-timeout 20 \
  --csv results/matrix.csv --output results/matrix.html

python benchmark_runner.py --repetitions 3 --jpamb-iterations 3 --method-timeout 20 \
  --config all-enabled --config no-static,no-dictionary \
  --csv results/selected.csv --output results/selected.md

python benchmark_runner.py --from-saved results/selected.csv --all-methods --output results/selected-details.html
```

The ablation table shows one row per configuration. Read the four ON/OFF
columns in order, then compare scores and timing. Match row numbers with the
coverage and run status table. JPAMB abs is the absolute time reported by
JPAMB. Wall time is measured by the runner for the full JPAMB command.

Omit `--output` to print an aligned terminal table. Open an `.html` output file
in a browser, or use an `.md` path to save a Markdown report. `--all-methods`
adds per-method detail.

Each repetition launches a fresh JPAMB command. For each repetition, the
comparison averages coverage over the internal iterations for each method and
then gives each method equal weight. The Smith column applies the same
calculation to methods with a Smith parameter. For each iteration, the number
of observed method–outcome pairs is the sum of distinct outcome counts per
method. The run averages those iteration counts. The analysis time column
sums per-method times and averages the sums over the internal iterations.
Official scores and JPAMB timing come directly from scoring results.

The table reports means and sample standard deviations across complete
repetitions. A single repetition reports only its measured value. Failed,
incomplete, and timed-out runs are listed separately. `--method-timeout`
sets JPAMB's per-method deadline. `--timeout` sets a deadline for the entire
JPAMB command.
Repeat `--from-saved` to combine exports from the same benchmark method set.
