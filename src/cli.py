import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
from csv import Error as CSVError
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

import click

import jpamb
import jpamb.interpret
import jvm
import sexpr
from jpamb.analysis_evaluation import EvaluationSession, checkpoint_path
from jpamb.evaluation import (
    MEASUREMENT_ENV,
    ComponentSettings,
    EvaluationRun,
    append_run,
    comparison_report,
    run_metadata_path,
)
from jpamb.report import write_report
from jpamb.utils import DockerRunner, Effect


@dataclasses.dataclass
class Context:
    eff: Effect
    docker_image: str
    suite: jpamb.Suite
    started: float = dataclasses.field(default_factory=perf_counter)


def re_parser(ctx_, parms_, expr):
    if expr:
        return re.compile(expr)


@click.group()
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="sets the verbosity of the program, more means more information",
)
@click.option(
    "-D",
    "--docker-image",
    help="the docker container to build with.",
    default="ghcr.io/kalhauge/jvm2json:jdk-latest",
)
@click.option(
    "--workdir",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
        resolve_path=True,
    ),
    default=Path.cwd(),
    show_default=True,
    help="the base of the jpamb folder.",
)
@click.pass_context
def cli(ctx, workdir: Path, verbose, docker_image):
    """This is the jpamb main entry point."""
    started = perf_counter()
    eff = Effect(sys.stderr)
    eff.level = 25 - verbose * 10
    suite = jpamb.Suite.from_workdir(workdir)
    ctx.obj = Context(
        eff=eff,
        docker_image=docker_image,
        suite=suite,
        started=started,
    )
    ctx.obj.eff.info(f"Setup suite in {workdir}")


@cli.command()
@click.option(
    "--docker / --no-docker",
    show_default=True,
    default=False,
    help="test docker container as well",
)
@click.pass_obj
def checkhealth(ctx, docker):
    """Check that the repository is setup correctly"""

    if docker:
        docker = DockerRunner.create(ctx.suite.workdir, ctx.docker_image, eff=ctx.eff)
    else:
        docker = None

    ctx.suite.checkhealth(docker=docker, eff=ctx.eff)


@cli.command()
@click.option(
    "--max-steps",
    show_default=True,
    default=100,
    help="how many steps to execute",
)
@click.option(
    "--step-wise / --no-step-wise",
    default=False,
    help="in case of crash, restart from where we left off",
)
@click.option(
    "--abstract / --no-abstract",
    default=False,
    help="also run the cases with the `all` input",
)
@click.option(
    "--timeout",
    show_default=True,
    default=2.0,
    help="timeout in seconds.",
)
@click.option(
    "--report",
    "-r",
    default=None,
    type=click.File("w"),
    help="write the report here (disables filter)",
)
@click.option(
    "--filter",
    "-f",
    default=".*",
    help="A regular expression which filter the methods to run on.",
    callback=re_parser,
)
@click.argument("PROGRAM", nargs=-1)
@click.pass_obj
def interpret(
    ctx,
    program,
    filter,
    step_wise,
    report,
    abstract,
    **kwargs,
):
    """Use PROGRAM as an interpreter."""

    eff = ctx.eff

    if ctx.suite.workdir != Path.cwd():
        eff.warning(f"Changing to {ctx.suite.workdir}")
        os.chdir(ctx.suite.workdir)

    if step_wise and report:
        raise click.UsageError("Cannot produce report in step wise mode")

    if filter != re.compile(".*") and report:
        raise click.UsageError(f"Cannot produce report in while filtering {filter}")

    benchmark = ctx.suite.benchmark(eff=eff)

    experiments = []
    
    for experiment in sorted(benchmark.experiments):
       
        if not filter.search(str(experiment)):
            eff.debug(f"Skipping {experiment}, excluded by filter")
            continue

        if not abstract and experiment.input is None:
            eff.debug(f"Skipping {experiment}, not included by --abstract")
            continue

        experiments.append(experiment)

    try:
        config = jpamb.interpret.Config.from_cmd(
            program,
            experiments,
            eff=eff,
            abstract=abstract,
            **kwargs,
        )
    except Exception as e:  # ruff: ignore[BLE001]
        eff.error(f"Error: {e}")
        eff.error("Failed to instantiate config")
        sys.exit(1)

    cache = ctx.suite.cache_folder(eff=eff)
    state_file = cache / "interpret-state.sexp"

    with eff.context("Trying to read state from cache"):
        state = None
        if step_wise:
            try:
                code = state_file.read_text()
                state_cc = sexpr.from_string(code)[0]
                state = jpamb.interpret.State.from_sexpr(state_cc)
                if state.config != config:
                    eff.warning("Old state ran with other config, restarting...")
                    state = None
            except FileNotFoundError:
                eff.debug("No analysis cache")
            except sexpr.FromSExprError as e:
                eff.error(f"Malformed state in cache; remove {state_file}")
                sys.exit(1)

    if state is None:
        state = jpamb.interpret.State(config)

    for cont in iter(
        lambda: state.run_next(
            benchmark=benchmark,
            workdir=ctx.suite.workdir,
            eff=eff,
        ),
        None,
    ):
        if step_wise and not cont:
            state.rewind()
            eff.error("Stopping early")
            state_file.write_text(sexpr.pretty(sexpr.sexpr(state), indent=2))
            eff.info(f"Saved state to {state_file!r}")
            return

    try:
        state_file.unlink()
    except FileNotFoundError:
        pass

    summary = state.summary()
    results = summary.score_results(benchmark=benchmark, eff=eff)
    results.display()

    if report:
        if results.invalid is not None:
            eff.error(results.invalid)
            eff.error("No report created")
            sys.exit(1)
        write_report(summary, file=report, eff=eff)


@cli.command()
@click.pass_obj
@click.option(
    "--iterations",
    "-N",
    type=click.IntRange(min=1),
    show_default=True,
    default=3,
    help="number of iterations.",
)
@click.option(
    "--timeout",
    show_default=True,
    default=5.0,
    help="timeout in seconds.",
)
@click.option(
    "--score-limit",
    "-l",
    type=float,
    default=None,
    help="stop if score is below limit",
)
@click.option(
    "--filter",
    "-f",
    default=".*",
    help="A regular expression which filter the methods to run on.",
    callback=re_parser,
)
@click.option(
    "--step-wise / --no-step-wise",
    default=False,
    help="in case of crash, restart from where we left off",
)
@click.option(
    "--report",
    default=None,
    type=click.File("w"),
    help="write the report here (disables filter)",
)
@click.option("--no-static", is_flag=True, help="Disable static Smith guidance.")
@click.option(
    "--no-dictionary",
    is_flag=True,
    help="Disable source dictionary guidance.",
)
@click.option(
    "--no-syntactic-structure",
    is_flag=True,
    help="Disable source-inferred Smith structure.",
)
@click.option(
    "--no-dynamic-structure",
    is_flag=True,
    help="Disable Smith structure learned during execution.",
)
@click.option(
    "--csv",
    type=click.Path(dir_okay=False, path_type=Path, resolve_path=True),
    help="Append evaluation measurements and a companion run summary.",
)
@click.argument("PROGRAM", nargs=-1, required=True)
def analyse(
    ctx,
    program,
    score_limit,
    filter,
    step_wise,
    report,
    no_static,
    no_dictionary,
    no_syntactic_structure,
    no_dynamic_structure,
    csv,
    iterations,
    timeout,
):
    """Evaluate the PROGRAM as an analysis."""

    eff = ctx.eff
    workdir = ctx.suite.workdir

    if step_wise and report:
        raise click.UsageError("Cannot produce report in step wise mode")

    if filter != re.compile(".*") and report:
        raise click.UsageError(f"Cannot produce report in while filtering {filter}")

    if csv is not None and report and Path(report.name).resolve() in {
        csv,
        run_metadata_path(csv).resolve(),
    }:
        raise click.UsageError("--report must use a different path from the CSV and run metadata")

    defaults = ComponentSettings.from_environment()
    settings = ComponentSettings(
        static=defaults.static and not no_static,
        dictionary=defaults.dictionary and not no_dictionary,
        syntactic_structure=defaults.syntactic_structure and not no_syntactic_structure,
        dynamic_structure=defaults.dynamic_structure and not no_dynamic_structure,
    )
    env = {**os.environ, **settings.environment()}
    env.pop(MEASUREMENT_ENV, None)
    benchmark = ctx.suite.benchmark(eff=eff)
    entries = []
    for entry in benchmark.entries():
        if filter.search(str(entry)):
            entries.append(entry)
        else:
            eff.info(f"Skipping {entry}, excluded by filter")

    entries = list(dict.fromkeys(entries))
    run_id = uuid4().hex
    expected_methods = tuple(entry.encode() for entry in entries)

    def record(status, *, rows=(), official=None, error=None):
        run = EvaluationRun(
            run_id=run_id,
            settings=settings,
            iterations=iterations,
            status=status,
            measurements=rows,
            evaluation_elapsed_seconds=perf_counter() - ctx.started,
            error=error,
            official=official,
            expected_methods=expected_methods,
        )
        if csv is not None:
            try:
                append_run(csv, run)
            except (CSVError, OSError, ValueError) as exc:
                raise click.ClickException(f"Could not save evaluation: {exc}") from exc
        return run

    if not entries:
        message = "No benchmark methods match the filter"
        record("failed", error=message)
        raise click.ClickException(message)

    try:
        config = jpamb.analyse.Config.from_cmd(
            program,
            entries,
            eff=eff,
            iterations=iterations,
            timeout=timeout,
            workdir=workdir,
            env=env,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        status = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
        message = f"Could not initialize analyzer: {exc}"
        record(status, error=message)
        raise click.ClickException(message) from exc

    state_file = (
        checkpoint_path(
            ctx.suite.cache_folder(eff=eff), config, settings, benchmark, score_limit
        )
        if step_wise
        else None
    )
    session = EvaluationSession(jpamb.analyse.State(config), settings)
    if state_file is not None:
        try:
            session = EvaluationSession.resume(state_file, config, settings)
        except (OSError, ValueError, KeyError, IndexError, sexpr.ParseError) as exc:
            raise click.ClickException(f"Could not read analysis checkpoint {state_file}: {exc}") from exc

    paused = False
    with TemporaryDirectory(prefix="jpamb-analysis-") as directory:
        for cont in iter(
            lambda: session.run_next(
                benchmark=benchmark,
                score_limit=score_limit,
                workdir=workdir,
                eff=eff,
                measurement_dir=Path(directory),
                env=env,
            ),
            None,
        ):
            if step_wise and not cont:
                paused = True
                failed_measurement = session.measurements.pop()
                session.state.progress -= 1
                session.checkpoint(state_file)
                eff.info(f"Saved state to {state_file}")
                session.measurements.append(failed_measurement)
                break

    summary = session.state.summary()
    results = summary.score_results(benchmark=benchmark, eff=eff)
    rows, official = session.scored(benchmark, results)
    status, error = "success", None
    for row in rows:
        if (row.status != "success" or row.error is not None) and (
            status == "success" or row.status == "timeout"
        ):
            status = "timeout" if row.status == "timeout" else "failed"
            error = row.error
    if paused:
        error = f"Analysis paused at a failed method. {error}"
    run = record(status, rows=rows, official=official, error=error)
    if state_file is not None and not paused:
        state_file.unlink(missing_ok=True)
    results.display(file=sys.stdout)
    if csv is not None or any(row.analysis_seconds is not None for row in rows):
        click.echo(comparison_report([run]))

    if status != "success":
        raise click.ClickException(error or "Analysis did not complete successfully")
    if report:
        if results.invalid is not None:
            eff.error(results.invalid)
            eff.error("No report created")
            sys.exit(1)
        write_report(summary, file=report, eff=eff)


@cli.command()
@click.pass_obj
@click.option(
    "--format",
    default="user",
    type=click.Choice(["user", "autolab"], case_sensitive=True),
)
@click.argument(
    "kind",
    default=None,
    type=click.Choice(
        ["analyse", "interpret", "abstract-interpret"], case_sensitive=True
    ),
)
@click.argument(
    "report",
    default=None,
    type=click.File("r"),
)
def validate(ctx, kind, report, format):
    """Validate the report as a correct report, and score it."""

    expr = sexpr.from_string(report.read())[0]
    match kind:
        case "analyse":
            summary = jpamb.analyse.Summary.from_sexpr(expr)
        case "interpret":
            summary = jpamb.interpret.Summary.from_sexpr(expr)
            if summary.config.abstract:
                return "Evaluated using the --abstract flag"
        case "abstract-interpret":
            summary = jpamb.interpret.Summary.from_sexpr(expr)
            if not summary.config.abstract:
                return "Did not evaluate using the --abstract flag"

    benchmark = ctx.suite.benchmark(eff=ctx.eff)

    result_summary = summary.score_results(
        benchmark=benchmark,
        eff=ctx.eff,
    )

    match format:
        case "user":
            if result_summary.invalid is not None:
                ctx.eff.error(result_summary.invalid)
                sys.exit(1)
            result_summary.display()
        case "autolab":
            result_summary.display_autolab()


@cli.command()
@click.option(
    "--compile / --no-compile",
    help="compile and decompile the java source files.",
    default=None,
)
@click.option(
    "--document / --no-document",
    help="docmument the files",
    default=None,
)
@click.option(
    "--test / --no-test",
    help="test that all cases are correct.",
    default=None,
)
@click.option(
    "--benchmark",
    help="benchmark the application against the executable.",
    default=None,
)
@click.pass_obj
def build(ctx, compile, document, test, benchmark):
    """Rebuild all benchmarks."""

    eff = ctx.eff

    if ctx.suite.workdir != Path.cwd():
        eff.warning(f"Changing to {ctx.suite.workdir}")
        os.chdir(ctx.suite.workdir)

    if not any(s for s in [compile, document, test, benchmark]):
        compile = compile is None
        document = document is None
        test = test is None

    docker = DockerRunner.create(ctx.suite.workdir, ctx.docker_image, eff=ctx.eff)

    if compile:
        ctx.suite.build(docker=docker, eff=ctx.eff)

    if document:
        ctx.suite.document(eff=ctx.eff)

    if test:
        ctx.suite.test(docker=docker, eff=ctx.eff)

    if benchmark:
        tools = ["dynamic-interpreter"]
        tool_configs = []
        for tool in tools:
            tool_bin = shutil.which(tool)
            if not tool_bin:
                ctx.eff.warning(f"did not have {tool} installed...")
                continue

            config = jpamb.interpret.Config.from_cmd(
                (tool_bin,),
                experiments=[],
                max_steps=100,
                timeout=5.0,
                eff=ctx.eff,
                abstract=False,
            )
            tool_configs.append(config)

        if not tool_configs:
            raise click.ClickException(
                "No benchmark interpreter is installed. "
                "Install the dynamic solution and retry."
            )

        ctx.suite.run_benchmark(*tool_configs, eff=ctx.eff)


@cli.command()
@click.option(
    "--format",
    type=click.Choice(["pretty", "real", "repr", "json"], case_sensitive=True),
    default="pretty",
    help="The format to print the instruction in.",
)
@click.argument("METHOD")
@click.pass_obj
def inspect(ctx, method, format):
    method = jvm.AbsMethodID.decode(method)
    for i, res in enumerate(
        ctx.suite.findmethod(method, eff=ctx.eff)["code"]["bytecode"]
    ):
        op = jvm.Opcode.from_json(res)
        match format:
            case "pretty":
                res = str(op)
            case "real":
                res = op.real()
            case "repr":
                res = repr(op)
            case "json":
                res = json.dumps(res)
        sys.stdout.write(f"{i:03d} | {res}\n")


if __name__ == "__main__":
    cli()
