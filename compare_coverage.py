#!/usr/bin/env python3

""" COMMANDS FOR COVERAGE ANALYSIS

for getting the normal table and some methods:

python3 compare_coverage.py --output tables.md


For getting every method as well as normal table:

python3 compare_coverage.py --all-methods --output tables.md


TO RUN THE ANALYSIS WITH DIFFERENT CONFIGS
LOOK AT THESE COMMANDS 
jpamb analyse dynamic-coverage-analysis --iterations 1 --csv both-enabled.csv
jpamb analyse dynamic-coverage-analysis --iterations 1 --no-static --csv no-static.csv
jpamb analyse dynamic-coverage-analysis --iterations 1 --no-syntactic --csv no-syntactic.csv
jpamb analyse dynamic-coverage-analysis --iterations 1 --no-static --no-syntactic --csv neither.csv

"""
"""Compare JPAMB coverage CSVs using Python's standard library.

Put this script beside your four CSVs and run:
    python3 compare_coverage.py --output tables.md

Or give the directory containing the CSVs:
    python3 compare_coverage.py results --output tables.md

Recognised file names and configuration labels:
    neither*.csv       -> Neither
    no-static*.csv     -> Syntactic only
    no-syntactic*.csv  -> Static only
    both-enabled*.csv  -> Both

For repetitions, save each complete run separately, for example:
    neither_run01.csv, neither_run02.csv, ...
The other configurations use the corresponding prefixes above.
Balanced repeated rows within one CSV are also accepted: the first occurrence
of every method forms run 1, the second forms run 2, and so on. All iterations
must be recorded in the CSV; increasing JPAMB's iteration count only helps this
script if the exporter preserves the individual results.

The report prints to the terminal; --output also saves it as Markdown.
Add --all-methods to include methods with unchanged average coverage.
With multiple runs, cells show mean +/- sample standard deviation.
"""

import argparse
import csv
import math
import statistics
from dataclasses import dataclass
from pathlib import Path


CONFIGURATIONS = (
    ("Neither", "neither"),
    ("Syntactic only", "no-static"),
    ("Static only", "no-syntactic"),
    ("Both", "both-enabled"),
)
REQUIRED_COLUMNS = {
    "method", "covered_instructions", "total_instructions",
    "coverage_percent", "observed_outcomes", "analysis_seconds",
}


@dataclass(frozen=True)
class Result:
    covered: int
    total: int
    outcomes: frozenset[str]
    seconds: float

    @property
    def coverage(self) -> float:
        return 100 * self.covered / self.total


def read_runs(path: Path) -> list[dict[str, Result]]:
    """Read one or more complete runs; reject incomplete repetitions."""
    by_method: dict[str, list[Result]] = {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}: missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            try:
                method = row["method"].strip()
                covered = int(row["covered_instructions"])
                total = int(row["total_instructions"])
                supplied_percent = float(row["coverage_percent"])
                seconds = float(row["analysis_seconds"])
                if not method or total <= 0 or not 0 <= covered <= total:
                    raise ValueError("invalid method or instruction counts")
                if not math.isfinite(seconds) or seconds < 0:
                    raise ValueError("analysis_seconds must be finite and non-negative")
                if not math.isfinite(supplied_percent) or not math.isclose(
                    supplied_percent, 100 * covered / total, abs_tol=0.01
                ):
                    raise ValueError("coverage_percent disagrees with instruction counts")
                outcomes = frozenset(
                    value.strip() for value in row["observed_outcomes"].split(";")
                    if value.strip()
                )
                result = Result(covered, total, outcomes, seconds)
            except (ValueError, TypeError, AttributeError) as error:
                raise ValueError(f"{path.name}, line {reader.line_num}: {error}") from error
            by_method.setdefault(method, []).append(result)

    repetitions = {len(results) for results in by_method.values()}
    if not repetitions:
        raise ValueError(f"{path.name}: no data rows")
    if len(repetitions) != 1:
        raise ValueError(
            f"{path.name}: methods have different numbers of rows; "
            "save complete runs with one result per method per iteration"
        )
    return [
        {method: results[index] for method, results in by_method.items()}
        for index in range(next(iter(repetitions)))
    ]


def load_data(directory: Path) -> dict[str, list[dict[str, Result]]]:
    data = {}
    reference = None
    for label, prefix in CONFIGURATIONS:
        files = sorted(directory.glob(f"{prefix}*.csv"))
        if not files:
            raise ValueError(f"No {prefix}*.csv files found in {directory}")
        runs = []
        for path in files:
            for run in read_runs(path):
                if reference is None:
                    reference = run
                if set(run) != set(reference):
                    raise ValueError(
                        f"{path.name}: method list differs from the other runs; "
                        f"{len(set(reference) - set(run))} missing, "
                        f"{len(set(run) - set(reference))} extra"
                    )
                for method, result in run.items():
                    if result.total != reference[method].total:
                        raise ValueError(
                            f"{path.name}: instruction total changed for {method}; "
                            "compare runs from the same benchmark version"
                        )
                runs.append(run)
        data[label] = runs
    return data


def format_values(values: list[float], digits: int = 2, unit: str = "") -> str:
    text = f"{statistics.mean(values):.{digits}f}{unit}"
    if len(values) > 1:
        deviation_unit = " pp" if unit == "%" else unit
        text += f" ± {statistics.stdev(values):.{digits}f}{deviation_unit}"
    return text


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    def line(cells):
        return "| " + " | ".join(str(cell).replace("|", "\\|") for cell in cells) + " |"

    return "\n".join([
        line(headers),
        line(["---"] + ["---:"] * (len(headers) - 1)),
        *(line(row) for row in rows),
    ])

def make_timing_table(data: dict) -> str:
    """Show mean time and standard deviation per method, in milliseconds."""
    labels = [label for label, _ in CONFIGURATIONS]
    methods = sorted(data["Neither"][0])
    rows = []

    for method in methods:
        cells = [method.removeprefix("jpamb.cases.")]

        for label in labels:
            times_ms = [
                run[method].seconds * 1000
                for run in data[label]
            ]
            cells.append(format_values(times_ms, digits=2, unit=" ms"))

        rows.append(cells)

    return markdown_table(["Method", *labels], rows)


def make_report(data: dict, all_methods: bool = False) -> str:
    labels = [label for label, _ in CONFIGURATIONS]
    methods = sorted(data["Neither"][0])
    smith_methods = [method for method in methods if "Ljpamb/utils/Smith;" in method]
    mean_coverage = {
        label: {
            method: statistics.mean(run[method].coverage for run in data[label])
            for method in methods
        }
        for label in labels
    }

    summary = [["Recorded runs", *(str(len(data[label])) for label in labels)]]
    for title, selected in [
        ("Average instruction coverage", methods),
        (f"Average coverage: {len(smith_methods)} Smith methods", smith_methods),
    ]:
        summary.append([title, *(
            format_values([
                statistics.mean(run[method].coverage for method in selected)
                for run in data[label]
            ], unit="%") if selected else "—"
            for label in labels
        )])

    summary.append(["Methods with higher mean coverage than neither", *(
        str(sum(
            mean_coverage[label][method] > mean_coverage["Neither"][method] + 1e-9
            for method in methods
        )) if label != "Neither" else "—"
        for label in labels
    )])
    summary.append(["Methods with 100% coverage per run", *(
        format_values([
            sum(result.covered == result.total for result in run.values())
            for run in data[label]
        ], digits=1) for label in labels
    )])
    summary.append(["Method–outcome pairs per run", *(
        format_values([
            sum(len(result.outcomes) for result in run.values())
            for run in data[label]
        ], digits=1) for label in labels
    )])
    summary.append(["Sum of recorded analysis times per run", *(
        format_values([
            sum(result.seconds for result in run.values())
            for run in data[label]
        ], digits=3, unit=" s") for label in labels
    )])

    selected_methods = [
        method for method in methods
        if all_methods or (
            max(mean_coverage[label][method] for label in labels)
            - min(mean_coverage[label][method] for label in labels) > 1e-9
        )
    ]
    coverage_rows = [
        [method.removeprefix("jpamb.cases."), *(
            format_values([run[method].coverage for run in data[label]], unit="%")
            for label in labels
        )]
        for method in selected_methods
    ]
    detail = markdown_table(["Method", *labels], coverage_rows) if coverage_rows else (
        "No differences in average instruction coverage between configurations."
    )
    
    return "\n\n".join([
        "# Coverage comparison",
        f"The same {len(methods)} methods are present in every recorded run. "
        "Syntactic only = no-static*.csv; Static only = no-syntactic*.csv.",
        "## Summary",
        markdown_table(["Measurement", *labels], summary),
        "Each method has equal weight in average coverage. With repeated runs, "
        "values show mean ± sample standard deviation across runs; pp means "
        "percentage points. Summary deviations describe run-level totals or "
        "averages, not variation between methods, and are not confidence intervals.",
        "Method–outcome pairs count each outcome once within each method and run, "
        "including `ok` and `*`. Results are averaged across runs, rather than "
        "combining discoveries from all repetitions. Recorded analysis times "
        "are summed; they are not the wall-clock duration of the JPAMB command.",
        "## Instruction coverage by method",
        "All methods are shown." if all_methods else (
            "Only methods with different mean coverage between configurations "
            "are shown. Use --all-methods to include every method."
        ),
        detail,
        "## Analysis time by method",
        "Mean ± sample standard deviation, in milliseconds.",
        make_timing_table(data),
        "These tables are descriptive comparisons. One recorded run does not "
        "measure run-to-run variation; repeated runs must be genuine separate "
        "executions, not duplicate copies of the same result.",
    ]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", nargs="?", type=Path, default=Path("."), help="Directory containing the CSVs (default: current directory)")
    parser.add_argument("--output", type=Path, help="Also save the tables to a Markdown file")
    parser.add_argument("--all-methods", action="store_true", help="Show every method in the coverage table")
    args = parser.parse_args()
    try:
        if not args.directory.is_dir():
            raise ValueError(f"Not a directory: {args.directory}")
        if args.output is not None:
            input_paths = {
                path.resolve() for _, prefix in CONFIGURATIONS
                for path in args.directory.glob(f"{prefix}*.csv")
            }
            if args.output.resolve() in input_paths:
                raise ValueError("--output must not overwrite an input CSV")
        report = make_report(load_data(args.directory), args.all_methods)
        if args.output is not None:
            args.output.write_text(report, encoding="utf-8")
    except (OSError, ValueError, csv.Error) as error:
        parser.exit(2, f"Error: {error}\n")
    print(report, end="")


if __name__ == "__main__":
    main()
