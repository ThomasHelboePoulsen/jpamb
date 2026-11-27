#!/usr/bin/env python3
"""Run repeated dynamic coverage evaluations or compare saved measurements."""

import argparse
import csv
import itertools
import math
import os
import signal
import subprocess
import sys
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

from jpamb.evaluation import (
    ABLATION_COMPONENTS,
    ComponentSettings,
    EvaluationRun,
    append_run,
    comparison_report,
    load_runs,
    run_metadata_path,
)

COMPONENT_FLAGS = {
    "static": "no-static",
    "dictionary": "no-dictionary",
    "syntactic_structure": "no-syntactic-structure",
    "dynamic_structure": "no-dynamic-structure",
}


def parse_configuration(text: str) -> ComponentSettings:
    flags = {flag.strip() for flag in text.split(",")}
    if flags == {"all-enabled"}:
        return ComponentSettings()
    if flags == {"all-disabled"}:
        flags = set(COMPONENT_FLAGS.values())
    unknown = flags.difference(COMPONENT_FLAGS.values())
    if unknown:
        raise argparse.ArgumentTypeError(f"Unknown component toggles in {text!r}")
    return ComponentSettings(
        **{component: flag not in flags for component, flag in COMPONENT_FLAGS.items()}
    )


def disabled_flags(settings: ComponentSettings) -> list[str]:
    return [
        flag
        for component, flag in COMPONENT_FLAGS.items()
        if not getattr(settings, component)
    ]


def execute_analysis(
    command: list[str], env: dict[str, str], timeout: float | None
) -> tuple[int, str]:
    separate_process_group = os.name == "posix"
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        env=env,
        start_new_session=separate_process_group,
    ) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            # Cancel the analyzer subprocess too, so it cannot overlap the next run.
            with suppress(ProcessLookupError):
                if separate_process_group:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            raise
        return process.returncode, output


def run_single(
    analysis: str,
    settings: ComponentSettings,
    *,
    iterations: int,
    repetition: int,
    filter_pattern: str | None = None,
    timeout: float | None = None,
    method_timeout: float | None = None,
) -> EvaluationRun:
    env = os.environ.copy()
    for variable in settings.environment():
        env.pop(variable, None)
    # Make the analyzer installed alongside the runner available when invoked
    # with a virtual environment's Python directly.
    env["PATH"] = os.pathsep.join(
        (str(Path(sys.executable).parent), env.get("PATH", ""))
    )

    with TemporaryDirectory(prefix="jpamb-evaluation-") as directory:
        raw = Path(directory) / "measurements.csv"
        command = [
            sys.executable,
            "-m",
            "cli",
            "analyse",
            "--iterations",
            str(iterations),
            "--csv",
            str(raw),
            *(f"--{flag}" for flag in disabled_flags(settings)),
        ]
        if method_timeout is not None:
            command.extend(("--timeout", str(method_timeout)))
        if filter_pattern is not None:
            command.extend(("--filter", filter_pattern))
        command.extend(("--", analysis))

        start = perf_counter()
        status = "success"
        error = None
        try:
            return_code, output = execute_analysis(command, env, timeout)
            if return_code:
                status = "failed"
                error = f"JPAMB exited with status {return_code}"
                if output.strip():
                    error += f". {output.strip().splitlines()[-1]}"
        except subprocess.TimeoutExpired:
            status = "timeout"
            error = f"JPAMB command exceeded {timeout:g} seconds"
        except OSError as exc:
            status = "failed"
            error = str(exc)
        elapsed = perf_counter() - start

        try:
            (run,) = load_runs(raw)
            if run.settings != settings or run.iterations != iterations:
                raise ValueError("JPAMB recorded a different evaluation configuration")
        except (OSError, ValueError, csv.Error) as exc:
            return EvaluationRun(
                run_id=uuid4().hex,
                settings=settings,
                iterations=iterations,
                status=status if error else "failed",
                elapsed_seconds=elapsed,
                repetition=repetition,
                error=error or f"Could not read the JPAMB evaluation: {exc}",
            )

    if status == "failed" and run.status == "timeout":
        status = "timeout"
    return replace(
        run,
        elapsed_seconds=elapsed,
        repetition=repetition,
        status=run.status if error is None else status,
        error=". ".join(filter(None, (error, run.error))) or None,
    )


def positive_integer(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def positive_seconds(text: str) -> float:
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("must be a positive finite number")
    return value


def raw_paths(path: Path) -> set[Path]:
    return {path.resolve(), run_metadata_path(path).resolve()}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-n",
        "--repetitions",
        "--iterations",
        type=positive_integer,
        default=3,
        help="Complete JPAMB invocations per configuration (default: 3)",
    )
    parser.add_argument(
        "--jpamb-iterations",
        type=positive_integer,
        default=3,
        help="Internal method iterations per JPAMB invocation (default: 3)",
    )
    parser.add_argument(
        "--config",
        action="append",
        type=parse_configuration,
        help=(
            "Select all-enabled, all-disabled, or a comma-separated list of "
            "no-static,no-dictionary,no-syntactic-structure,no-dynamic-structure. "
            "Repeat to select multiple configurations (default: all 16)."
        ),
    )
    parser.add_argument("--filter", help="Method regex passed to jpamb analyse")
    parser.add_argument(
        "--analysis",
        default="dynamic-coverage-analysis",
        help="Analysis executable (default: dynamic-coverage-analysis)",
    )
    parser.add_argument(
        "--timeout", type=positive_seconds, help="Whole-command timeout in seconds"
    )
    parser.add_argument(
        "--method-timeout",
        type=positive_seconds,
        help="Per-method timeout passed to jpamb analyse in seconds (JPAMB default: 5)",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--csv", type=Path, help="Append raw evaluations to this CSV")
    source.add_argument(
        "--from-saved",
        type=Path,
        action="append",
        help="Rebuild from this CSV and its run metadata without invoking JPAMB",
    )
    parser.add_argument(
        "--output", type=Path, help="Save the comparison as Markdown or an .html table"
    )
    parser.add_argument(
        "--all-methods", action="store_true", help="Include per-method measurements"
    )
    args = parser.parse_args(argv)

    inputs = args.from_saved or ([args.csv] if args.csv else [])
    if args.output and any(args.output.resolve() in raw_paths(path) for path in inputs):
        parser.error("--output must be different from the raw CSV and run metadata")

    try:
        if args.from_saved:
            runs = [run for path in args.from_saved for run in load_runs(path)]
        else:
            components = tuple(key for key, _ in ABLATION_COMPONENTS)
            configurations = (
                list(dict.fromkeys(args.config))
                if args.config
                else [
                    ComponentSettings(**dict(zip(components, values, strict=True)))
                    for values in itertools.product(
                        (True, False), repeat=len(components)
                    )
                ]
            )
            if args.csv and any(path.exists() for path in raw_paths(args.csv)):
                load_runs(
                    args.csv
                )  # Validate the destination before starting analysis.
            runs = []
            for index, settings in enumerate(configurations, 1):
                label = ",".join(disabled_flags(settings)) or "all-enabled"
                print(f"[{index}/{len(configurations)}] {label}", flush=True)
                for repetition in range(1, args.repetitions + 1):
                    run = run_single(
                        args.analysis,
                        settings,
                        iterations=args.jpamb_iterations,
                        repetition=repetition,
                        filter_pattern=args.filter,
                        timeout=args.timeout,
                        method_timeout=args.method_timeout,
                    )
                    if args.csv:
                        append_run(args.csv, run)
                    runs.append(run)
                    print(
                        f"  Repetition {repetition}/{args.repetitions}: "
                        f"{run.status}, {run.elapsed_seconds:.2f} s elapsed",
                        flush=True,
                    )
                    if run.error:
                        print(f"  {run.error}", flush=True)

        html = args.output is not None and args.output.suffix.lower() == ".html"
        report_format = "terminal"
        if args.output:
            report_format = "html" if html else "markdown"
        report = comparison_report(
            runs, per_method=args.all_methods, format=report_format
        )
        if not html:
            print(report, end="")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(report, encoding="utf-8")
            if html:
                print(f"Saved comparison table to {args.output}")
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
