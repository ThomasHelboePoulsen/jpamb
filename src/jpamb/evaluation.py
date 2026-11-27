"""Measurements from JPAMB evaluations, their persistence, and comparisons."""

import csv
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from html import escape
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

import jvm
import sexpr

if TYPE_CHECKING:
    from jpamb.analyse import ResultSummary, Summary
    from jpamb.case import Benchmark

MEASUREMENT_ENV = "JPAMB_COVERAGE_MEASUREMENT"
SCHEMA_VERSION = 1
STATUSES = ("success", "failed", "timeout")
ABLATION_COMPONENTS = (
    ("static", "Static"),
    ("dictionary", "Dict"),
    ("dynamic_structure", "DynStruct"),
    ("syntactic_structure", "Syntactic"),
)


@dataclass(frozen=True)
class ComponentSettings:
    static: bool = True
    dictionary: bool = True
    syntactic_structure: bool = True
    dynamic_structure: bool = True

    @classmethod
    def from_environment(
        cls, env: Mapping[str, str] | None = None
    ) -> "ComponentSettings":
        if env is None:
            env = os.environ
        keys = cls().environment()
        return cls(
            *(env.get(key, "").lower() not in {"1", "true", "yes"} for key in keys)
        )

    def environment(self) -> dict[str, str]:
        """Set every toggle explicitly for child-process configuration isolation."""
        return {
            "DISABLE_STATIC_SEEDS": "0" if self.static else "1",
            "DISABLE_DICTIONARY": "0" if self.dictionary else "1",
            "DISABLE_SYNTACTIC_STRUCTURE": "0" if self.syntactic_structure else "1",
            "DISABLE_DYNAMIC_STRUCTURE": "0" if self.dynamic_structure else "1",
        }


@dataclass(frozen=True)
class MethodMeasurement:
    method: str
    iteration: int
    status: str = "success"
    covered_instructions: int | None = None
    total_instructions: int | None = None
    observed_outcomes: tuple[str, ...] | None = None
    analysis_seconds: float | None = None
    score: float | None = None
    jpamb_absolute_ns: int | None = None
    jpamb_relative_db: float | None = None
    error: str | None = None

    def __post_init__(self):
        if not self.method or self.iteration < 1 or self.status not in STATUSES:
            raise ValueError("Invalid method, iteration, or status")
        covered, total = self.covered_instructions, self.total_instructions
        if (covered is None) != (total is None) or (
            covered is not None and not 0 <= covered <= total
        ):
            raise ValueError("Invalid instruction counts")
        if self.analysis_seconds is not None and (
            not math.isfinite(self.analysis_seconds) or self.analysis_seconds < 0
        ):
            raise ValueError("Analysis time must be finite and non-negative")
        if self.observed_outcomes is not None:
            if any(not isinstance(outcome, str) for outcome in self.observed_outcomes):
                raise ValueError("Observed outcomes must be strings")
            object.__setattr__(
                self, "observed_outcomes", tuple(sorted(set(self.observed_outcomes)))
            )

    @property
    def coverage_percent(self) -> float | None:
        if self.total_instructions:
            return 100 * self.covered_instructions / self.total_instructions
        return None


@dataclass(frozen=True)
class EvaluationRun:
    run_id: str
    settings: ComponentSettings
    iterations: int
    status: str
    measurements: tuple[MethodMeasurement, ...] = ()
    elapsed_seconds: float | None = None
    repetition: int | None = None
    error: str | None = None
    official: dict | None = None
    expected_methods: tuple[str, ...] = ()
    evaluation_elapsed_seconds: float | None = None

    def __post_init__(self):
        if not self.run_id or self.iterations < 1 or self.status not in STATUSES:
            raise ValueError("Invalid run identifier, iteration count, or status")
        if self.repetition is not None and self.repetition < 1:
            raise ValueError("Repetition must be positive")
        for elapsed in (self.elapsed_seconds, self.evaluation_elapsed_seconds):
            if elapsed is not None and (not math.isfinite(elapsed) or elapsed < 0):
                raise ValueError("Elapsed time must be finite and non-negative")
        if len(set(self.expected_methods)) != len(self.expected_methods):
            raise ValueError(f"Run {self.run_id} has duplicate expected methods")
        entries = {(row.method, row.iteration) for row in self.measurements}
        if len(entries) != len(self.measurements):
            raise ValueError(f"Run {self.run_id} has duplicate method/iteration rows")
        if any(row.iteration > self.iterations for row in self.measurements):
            raise ValueError(
                f"Run {self.run_id} has rows beyond its requested iterations"
            )
        if self.expected_methods and not {name for name, _ in entries}.issubset(
            self.expected_methods
        ):
            raise ValueError(f"Run {self.run_id} has rows for unexpected methods")

    @property
    def complete(self) -> bool:
        return (
            self.status == "success"
            and bool(self.expected_methods)
            and len(self.measurements) == self.iterations * len(self.expected_methods)
            and all(
                row.status == "success" and row.error is None
                for row in self.measurements
            )
        )


def _json_number(value: float) -> int | float | str:
    """Preserve the official scorer's non-finite values in standard JSON."""
    return value if math.isfinite(value) else str(value)


def official_results(
    benchmark: "Benchmark", summary: "Summary", scored: "ResultSummary"
) -> dict:
    """Capture JPAMB's score rows and the complete native framework report."""
    from jpamb.case import Experiment

    methods = {}
    for group, rows in scored.results:
        for row in rows:
            method = f"{group}.{row.methodname}"
            methods[method] = {
                "group": group,
                "score": _json_number(row.score),
                "jpamb_relative_db": _json_number(row.rel_time),
                "jpamb_absolute_ns": _json_number(row.abs_time),
            }

    categories = {}
    for category, tracker in scored.categories.items():
        wager = tracker.wager()
        iterations = scored.config.iterations
        categories[category.name] = {
            "hits": tracker.hits,
            "misses": tracker.misses,
            "found_per_iteration": tracker.hits / iterations,
            "missed_per_iteration": tracker.misses / iterations,
            "probability": _json_number(wager.to_probability()),
            "wager": _json_number(wager.wager),
            "reward": _json_number(wager.reward()),
            "score": _json_number(
                (wager.score(False) * tracker.misses + wager.score(True) * tracker.hits)
                / iterations
            ),
        }

    return {
        "total_score": _json_number(scored.total_score),
        "mean_rel_time_db": _json_number(scored.mean_rel_time),
        "total_abs_time_ns": _json_number(scored.total_abs_time),
        "invalid": scored.invalid,
        "methods": methods,
        "categories": categories,
        "expected_outcomes": {
            entry.encode(): sorted(
                benchmark.experiments[Experiment(entry, None)].results
            )
            for entry in summary.config.experiments
        },
        "framework_report": sexpr.pretty(summary.__sexpr__(), indent=0),
    }


SETTING_FIELDS = tuple(field.name for field in fields(ComponentSettings))
MEASUREMENT_FIELDS = tuple(field.name for field in fields(MethodMeasurement))
CSV_FIELDS = (
    "run_id",
    "repetition",
    *SETTING_FIELDS,
    *MEASUREMENT_FIELDS,
    "coverage_percent",
)


def run_metadata_path(path: Path) -> Path:
    return path.with_suffix(".runs.jsonl")


@contextmanager
def _locked(file: TextIO):
    """Coordinate an export and its companion with concurrent readers and writers."""
    file.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(file, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file, fcntl.LOCK_UN)


def _read_metadata(file: TextIO) -> dict[str, dict]:
    runs = {}
    for line_number, line in enumerate(file, start=1):
        try:
            raw = json.loads(line)
            if raw.pop("schema_version", None) != SCHEMA_VERSION:
                raise ValueError("Incompatible run metadata schema")
            run_id = raw["run_id"]
            if run_id in runs:
                raise ValueError(f"Duplicate run identifier {run_id}")
            settings = raw["settings"]
            if set(settings) != set(SETTING_FIELDS) or any(
                type(value) is not bool for value in settings.values()
            ):
                raise ValueError("Incompatible component settings schema")
            raw["settings"] = ComponentSettings(**settings)
            raw["expected_methods"] = tuple(raw["expected_methods"])
            runs[run_id] = raw
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"{file.name}, line {line_number}: {error}") from error
    return runs


def _parse_measurement(row: dict[str, str]) -> MethodMeasurement:
    def number(name, parser):
        return parser(row[name]) if row[name] else None

    outcomes = number("observed_outcomes", json.loads)
    if outcomes is not None and not isinstance(outcomes, list):
        raise ValueError("Observed outcomes must be a JSON array")
    result = MethodMeasurement(
        method=row["method"],
        iteration=int(row["iteration"]),
        status=row["status"],
        covered_instructions=number("covered_instructions", int),
        total_instructions=number("total_instructions", int),
        observed_outcomes=outcomes,
        analysis_seconds=number("analysis_seconds", float),
        score=number("score", float),
        jpamb_absolute_ns=number("jpamb_absolute_ns", int),
        jpamb_relative_db=number("jpamb_relative_db", float),
        error=row["error"] or None,
    )
    coverage = number("coverage_percent", float)
    expected = result.coverage_percent
    if not (
        (coverage is None and expected is None)
        or (
            coverage is not None
            and expected is not None
            and math.isclose(coverage, expected, abs_tol=1e-9)
        )
    ):
        raise ValueError("Coverage percentage disagrees with instruction counts")
    return result


def _csv_reader(csv_file: TextIO) -> csv.DictReader:
    reader = csv.DictReader(csv_file)
    if reader.fieldnames is not None and tuple(reader.fieldnames) != CSV_FIELDS:
        raise ValueError(f"{csv_file.name}: incompatible evaluation CSV schema")
    return reader


def _read_runs(
    csv_name: str, reader: csv.DictReader, metadata_file: TextIO
) -> list[EvaluationRun]:
    metadata = _read_metadata(metadata_file)
    if metadata and reader.fieldnames is None:
        raise ValueError(f"{csv_name}: missing evaluation CSV header")
    measurements = defaultdict(list)
    for row in reader:
        try:
            if None in row or None in row.values():
                raise ValueError("Wrong number of CSV columns")
            if row["run_id"] not in metadata:
                raise ValueError(f"Missing companion metadata for run {row['run_id']}")
            run = metadata[row["run_id"]]
            settings = asdict(run["settings"])
            if any(row[key] != str(value).lower() for key, value in settings.items()):
                raise ValueError("Component settings disagree with run metadata")
            if (int(row["repetition"]) if row["repetition"] else None) != run[
                "repetition"
            ]:
                raise ValueError("Repetition disagrees with run metadata")
            measurements[row["run_id"]].append(_parse_measurement(row))
        except (ValueError, KeyError, TypeError) as error:
            raise ValueError(f"{csv_name}, line {reader.line_num}: {error}") from error
    result = []
    for run_id, raw in metadata.items():
        try:
            run = EvaluationRun(**raw, measurements=tuple(measurements[run_id]))
        except (ValueError, TypeError) as error:
            raise ValueError(f"{metadata_file.name}, run {run_id}: {error}") from error
        if run.status == "success" and not run.complete:
            raise ValueError(f"{csv_name}: incomplete successful run {run_id}")
        result.append(run)
    return result


def load_runs(path: Path) -> list[EvaluationRun]:
    """Read the CSV and its run-level metadata and check their association."""
    path = Path(path)
    with path.open(encoding="utf-8", newline="") as csv_file, _locked(csv_file):
        reader = _csv_reader(csv_file)
        companion = run_metadata_path(path)
        try:
            metadata = companion.open(encoding="utf-8")
        except FileNotFoundError:
            metadata = StringIO()
        with metadata:
            return _read_runs(csv_file.name, reader, metadata)


def _metadata(run: EvaluationRun) -> str:
    record = asdict(run)
    del record["measurements"]
    record["schema_version"] = SCHEMA_VERSION
    return json.dumps(record, allow_nan=False, separators=(",", ":"))


def _measurement_row(run: EvaluationRun, row: MethodMeasurement) -> dict:
    record = asdict(row)
    record.update(
        run_id=run.run_id,
        repetition=run.repetition,
        coverage_percent=row.coverage_percent,
    )
    record.update(
        {key: str(value).lower() for key, value in asdict(run.settings).items()}
    )
    if row.observed_outcomes is not None:
        record["observed_outcomes"] = json.dumps(row.observed_outcomes)
    return record


def append_run(path: Path, run: EvaluationRun) -> None:
    """Append one run with a single header and a matching metadata record."""
    if run.status == "success" and not run.complete:
        raise ValueError(f"Cannot save incomplete successful run {run.run_id}")

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = _metadata(run)
    with path.open("a+", encoding="utf-8", newline="") as csv_file, _locked(csv_file):
        reader = _csv_reader(csv_file)
        with run_metadata_path(path).open("a+", encoding="utf-8") as metadata_file:
            metadata_file.seek(0)
            for existing in _read_runs(csv_file.name, reader, metadata_file):
                if existing.run_id == run.run_id:
                    raise ValueError(f"{path}: duplicate run identifier {run.run_id}")

            csv_file.seek(0, os.SEEK_END)
            metadata_file.seek(0, os.SEEK_END)
            csv_end = csv_file.tell()
            metadata_end = metadata_file.tell()
            try:
                writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
                if csv_end == 0:
                    writer.writeheader()
                writer.writerows(_measurement_row(run, row) for row in run.measurements)
                csv_file.flush()
                metadata_file.write(serialized + "\n")
                metadata_file.flush()
            except BaseException:
                csv_file.truncate(csv_end)
                metadata_file.truncate(metadata_end)
                raise


def _mean(values: Iterable[float | None]) -> float | None:
    values = list(values)
    if not values or any(value is None for value in values):
        return None
    return statistics.mean(values)


def _sum(values: Iterable[float | None]) -> float | None:
    values = list(values)
    if not values or any(value is None for value in values):
        return None
    return sum(values)


def _official_metric(official: dict, name: str) -> float | None:
    value = official.get(name)
    return None if value is None else float(value)


def _takes_smith(method: str) -> bool:
    smith = jvm.Object(jvm.ClassName("jpamb.utils.Smith"))
    return smith in jvm.AbsMethodID.decode(method).extension.params


@dataclass
class _MethodStatistics:
    coverage: float | None
    outcomes: float | None
    seconds: float | None
    score: float | None


@dataclass
class _RunStatistics:
    metrics: tuple[float | None, ...]
    methods: dict[str, _MethodStatistics]


def _run_statistics(run: EvaluationRun) -> _RunStatistics:
    """Average iterations within one run before comparing independent runs."""
    official = run.official or {}
    method_scores = official.get("methods", {})
    by_method = defaultdict(list)
    for row in run.measurements:
        by_method[row.method].append(row)
    methods = {
        method: _MethodStatistics(
            _mean(row.coverage_percent for row in rows),
            _mean(
                len(row.observed_outcomes)
                if row.observed_outcomes is not None
                else None
                for row in rows
            ),
            _mean(row.analysis_seconds for row in rows),
            _official_metric(method_scores.get(method, {}), "score"),
        )
        for method, rows in by_method.items()
    }
    absolute_ns = _official_metric(official, "total_abs_time_ns")
    return _RunStatistics(
        (
            _mean(stats.coverage for stats in methods.values()),
            _mean(
                stats.coverage
                for method, stats in methods.items()
                if _takes_smith(method)
            ),
            _sum(stats.outcomes for stats in methods.values()),
            _sum(stats.seconds for stats in methods.values()),
            _official_metric(official, "total_score"),
            run.elapsed_seconds,
            run.evaluation_elapsed_seconds,
            None if absolute_ns is None else absolute_ns / 1e9,
            _official_metric(official, "mean_rel_time_db"),
        ),
        methods,
    )


def _format_samples(values: Iterable[float | None], *, unit: str = "") -> str:
    values = list(values)
    measured = [value for value in values if value is not None]
    if not measured:
        return "—"
    mean = statistics.mean(measured)
    text = f"{mean:.3f}{unit}"
    if len(measured) > 1:
        deviation = (
            f"{statistics.stdev(measured):.3f}"
            if all(map(math.isfinite, measured))
            else "—"
        )
        text += f" ± {deviation}{' pp' if unit == '%' else unit}"
    if len(measured) != len(values):
        text += f" (n={len(measured)})"
    return text


def _markdown_table(headers: list[str], rows: Iterable[Iterable[str]]) -> str:
    def line(cells):
        safe = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells]
        return "| " + " | ".join(safe) + " |"

    return "\n".join(
        [line(headers), line(["---"] * len(headers)), *(line(row) for row in rows)]
    )


def _terminal_table(headers: list[str], rows: list[list[str]]) -> str:
    cells = [headers, *([cell.replace("\n", " ") for cell in row] for row in rows)]
    widths = [max(map(len, column)) for column in zip(*cells, strict=True)]

    def line(row):
        return " | ".join(
            cell.ljust(width) for cell, width in zip(row, widths, strict=True)
        ).rstrip()

    separator = "-+-".join("-" * width for width in widths)
    return "\n".join((line(headers), separator, *(line(row) for row in cells[1:])))


def _html_table(
    headers: Iterable[str], rows: Iterable[Iterable[str]], *, table_id: str
) -> str:
    headings = "".join(f'<th scope="col">{escape(header)}</th>' for header in headers)
    body = []
    for label, *values in rows:
        cells = "".join(f"<td>{escape(value)}</td>" for value in values)
        body.append(f'<tr><th scope="row">{escape(label)}</th>{cells}</tr>')
    return (
        f'<div class="table-scroll" tabindex="0"><table id="{table_id}">'
        f"<thead><tr>{headings}</tr></thead><tbody>{''.join(body)}</tbody>"
        "</table></div>"
    )


def _html_report(content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JPAMB ablation results</title>
<style>
  body {{
    margin: 0; background: #f4f6fa; color: #182538;
    font: 16px/1.5 system-ui, sans-serif;
  }}
  main {{ max-width: 72rem; margin: auto; padding: 2rem clamp(1rem, 4vw, 3rem); }}
  h1 {{ font-size: 2rem; margin: 0 0 1.25rem; }}
  h2 {{ font-size: 1.25rem; margin-top: 2.25rem; }}
  .notes {{ max-width: 72ch; color: #495a6e; }}
  .table-scroll {{
    overflow: auto; max-height: 65vh; background: white;
    border: 1px solid #cdd7e5; border-radius: .5rem;
  }}
  table {{ border-spacing: 0; width: 100%; font-variant-numeric: tabular-nums; }}
  th, td {{ padding: .65rem .9rem; text-align: left; border-bottom: 1px solid #dce4ee; }}
  thead th {{ position: sticky; top: 0; background: #203853; color: white; }}
  tbody th {{ font-weight: 600; overflow-wrap: anywhere; }}
  tbody tr:nth-child(even) {{ background: #f5f8fc; }}
  tbody tr:hover {{ background: #e9f2ff; }}
  tbody tr:last-child > * {{ border-bottom: 0; }}
  #summary th, #summary td, #coverage th, #coverage td, #methods td {{
    white-space: nowrap;
  }}
  #summary td:nth-child(-n+5) {{ text-align: center; }}
  #methods td:first-of-type {{ white-space: normal; overflow-wrap: anywhere; }}
  label {{ display: block; margin: 0 0 .75rem; }}
  input {{
    margin-left: .5rem; padding: .35rem .55rem; width: min(18rem, 50%);
    border: 1px solid #8c9eb4; border-radius: .35rem; font: inherit;
  }}
  @media print {{
    body {{ background: white; }}
    main {{ padding: 0; }}
    .table-scroll {{ max-height: none; overflow: visible; }}
    thead th {{ position: static; color: #182538; background: #e9eef5; }}
    label {{ display: none; }}
  }}
</style>
</head>
<body>
<main>
<h1>JPAMB ablation results</h1>
{content}
</main>
</body>
</html>
"""


def _settings_order(settings: ComponentSettings) -> tuple[bool, ...]:
    return tuple(not getattr(settings, key) for key, _ in ABLATION_COMPONENTS)


def _validate_comparison(runs: Iterable[EvaluationRun]) -> None:
    """Check that repetition estimates refer to the same benchmark methods."""
    method_set = None
    instruction_totals = {}
    for run in runs:
        if not run.complete:
            continue
        methods = set(run.expected_methods)
        if method_set is not None and methods != method_set:
            raise ValueError(f"Run {run.run_id} has a different benchmark method list")
        method_set = methods
        for row in run.measurements:
            if row.total_instructions is None:
                continue
            if (
                instruction_totals.setdefault(row.method, row.total_instructions)
                != row.total_instructions
            ):
                raise ValueError(
                    f"Instruction count changed for {row.method} in run {run.run_id}"
                )


def comparison_report(
    runs: Iterable[EvaluationRun], per_method: bool = False, *, format: str = "markdown"
) -> str:
    """Show means and sample standard deviations across complete benchmark runs."""
    by_id = {}
    for run in runs:
        if run.run_id in by_id:
            # A saved run copied to multiple inputs is still one repetition.
            if by_id[run.run_id] != run:
                raise ValueError(f"Conflicting records for run {run.run_id}")
        else:
            by_id[run.run_id] = run
    _validate_comparison(by_id.values())

    groups = defaultdict(list)
    for run in by_id.values():
        groups[run.settings].append(run)
    if not groups:
        if format == "html":
            return _html_report("<p>No evaluation runs.</p>")
        return "No evaluation runs.\n"

    # Units follow the order of the values in _run_statistics.
    units = ("%", "%", "", " s", "", " s", " s", " s", " Db")
    ablation_rows = []
    coverage_rows = []
    method_rows = []
    failure_rows = []
    ordered_groups = sorted(groups.items(), key=lambda item: _settings_order(item[0]))
    for number, (settings, group) in enumerate(ordered_groups, start=1):
        row_id = str(number)
        counts = Counter(
            run.status if run.complete or run.status != "success" else "incomplete"
            for run in group
        )
        complete = [_run_statistics(run) for run in group if run.complete]
        samples = (
            zip(*(stats.metrics for stats in complete))
            if complete
            else [()] * len(units)
        )
        (
            coverage,
            smith_coverage,
            outcomes,
            analysis,
            score,
            wall,
            cli,
            absolute,
            relative,
        ) = (
            _format_samples(values, unit=unit)
            for values, unit in zip(samples, units, strict=True)
        )
        ablation_rows.append(
            [
                row_id,
                *(
                    "ON" if getattr(settings, key) else "OFF"
                    for key, _ in ABLATION_COMPONENTS
                ),
                score,
                wall,
                absolute,
                relative,
            ]
        )
        coverage_rows.append(
            [
                row_id,
                str(counts["success"]),
                str(counts["failed"] + counts["incomplete"]),
                str(counts["timeout"]),
                coverage,
                smith_coverage,
                outcomes,
                analysis,
                cli,
            ]
        )
        failure_rows.extend(
            [
                row_id,
                run.run_id,
                str(run.repetition) if run.repetition is not None else "—",
                run.status if run.status != "success" else "incomplete",
                _format_samples([run.elapsed_seconds], unit=" s"),
                run.error or "—",
            ]
            for run in group
            if not run.complete
        )
        if per_method and complete:
            for method in sorted(complete[0].methods):
                stats = [rep.methods[method] for rep in complete]
                method_rows.append(
                    [
                        row_id,
                        method,
                        _format_samples([row.coverage for row in stats], unit="%"),
                        _format_samples([row.outcomes for row in stats]),
                        _format_samples([row.seconds for row in stats], unit=" s"),
                        _format_samples([row.score for row in stats]),
                    ]
                )

    ablation_headers = [
        "#",
        *(label for _, label in ABLATION_COMPONENTS),
        "Score",
        "Wall time",
        "JPAMB abs",
        "Rel time",
    ]
    coverage_headers = [
        "#",
        "Complete",
        "Failed / incomplete",
        "Timed out",
        "Coverage",
        "Smith coverage",
        "Outcome pairs",
        "Analysis time",
        "CLI elapsed",
    ]
    failure_headers = ["#", "Run ID", "Repetition", "Status", "Wall time", "Details"]
    method_headers = [
        "#",
        "Method",
        "Coverage",
        "Observed outcomes",
        "Analysis time",
        "JPAMB score",
    ]
    notes = (
        "Coverage weights each method equally. Each run averages its internal iterations "
        "for coverage, observed method–outcome pair counts, and summed analysis time. "
        "Values show the mean across complete runs and sample standard deviation when "
        "available. Coverage deviations are in percentage points (pp)."
    )
    if format == "html":
        sections = [
            _html_table(ablation_headers, ablation_rows, table_id="summary"),
            "<h2>Coverage and run status</h2>",
            _html_table(coverage_headers, coverage_rows, table_id="coverage"),
            f'<p class="notes">{escape(notes)}</p>',
        ]
        if failure_rows:
            sections.append(
                "<h2>Failed or incomplete runs</h2>"
                + _html_table(failure_headers, failure_rows, table_id="failures")
            )
        if method_rows:
            if len(groups) == 1:
                method_headers = method_headers[1:]
                method_rows = [row[1:] for row in method_rows]
            sections.append(
                "<h2>Per-method results</h2>"
                '<label>Find a method <input type="search" id="method-filter"></label>'
                + _html_table(method_headers, method_rows, table_id="methods")
                + """
<script>
  const search = document.querySelector("#method-filter");
  const rows = document.querySelectorAll("#methods tbody tr");
  search.addEventListener("input", () => {
    const query = search.value.trim().toLowerCase();
    for (const row of rows) row.hidden = !row.textContent.toLowerCase().includes(query);
  });
</script>
"""
            )
        return _html_report("\n".join(sections))

    terminal = format == "terminal"
    table = _terminal_table if terminal else _markdown_table
    title = "" if terminal else "## "
    subtitle = "" if terminal else "### "
    sections = [
        f"{title}Ablation results",
        table(ablation_headers, ablation_rows),
        f"{subtitle}Coverage and run status",
        table(coverage_headers, coverage_rows),
        notes,
    ]
    if failure_rows:
        sections.extend(
            [
                f"{subtitle}Failed or incomplete runs",
                table(failure_headers, failure_rows),
            ]
        )
    if method_rows:
        sections.extend(
            [f"{subtitle}Per-method results", table(method_headers, method_rows)]
        )
    return "\n\n".join(sections) + "\n"
