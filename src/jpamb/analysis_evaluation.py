"""Associate optional analyzer measurements with the framework's own executions."""

import json
import math
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

import sexpr
from jpamb.analyse import Config, ResultSummary, State
from jpamb.case import Benchmark, Entry, Experiment
from jpamb.evaluation import (
    MEASUREMENT_ENV,
    ComponentSettings,
    MethodMeasurement,
    official_results,
)
from jpamb.utils import Effect


def checkpoint_path(
    cache: Path,
    config: Config,
    settings: ComponentSettings,
    benchmark: Benchmark,
    score_limit: float | None,
) -> Path:
    outcomes = [
        sorted(benchmark.experiments[Experiment(entry, None)].results)
        for entry in config.experiments
    ]
    identity = [
        sexpr.pretty(sexpr.sexpr(config)),
        asdict(settings),
        outcomes,
        score_limit,
    ]
    key = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return cache / f"analysis-evaluation-v1-{key}.json"


@dataclass
class EvaluationSession:
    state: State
    settings: ComponentSettings
    measurements: list[MethodMeasurement] = field(default_factory=list)

    @classmethod
    def resume(cls, path: Path, config: Config, settings: ComponentSettings):
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls(State(config), settings)
        state = State.from_sexpr(sexpr.from_string(saved["state"])[0])
        if state.config != config or saved["settings"] != asdict(settings):
            raise ValueError("Checkpoint has a different analysis configuration")
        rows = []
        for row in saved["measurements"]:
            if row["observed_outcomes"] is not None:
                row["observed_outcomes"] = tuple(row["observed_outcomes"])
            rows.append(MethodMeasurement(**row))
        return cls(state, settings, rows)

    def checkpoint(self, path: Path):
        data = {
            "state": sexpr.pretty(sexpr.sexpr(self.state)),
            "settings": asdict(self.settings),
            "measurements": [asdict(row) for row in self.measurements],
        }
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            temporary = Path(output.name)
            try:
                json.dump(data, output)
                output.close()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)

    def run_next(
        self,
        *,
        benchmark: Benchmark,
        score_limit: float | None,
        workdir: Path,
        eff: Effect,
        measurement_dir: Path,
        env: dict[str, str],
    ) -> bool | None:
        config = self.state.config
        position = self.state.progress

        def execute(entry: Entry):
            path = measurement_dir / f"{position}.json"
            result, status, error = config.run_experiment_with_status(
                entry, workdir=workdir, eff=eff, env={**env, MEASUREMENT_ENV: str(path)}
            )
            method = entry.encode()
            iteration = position // len(config.experiments) + 1
            metrics = {}
            if result is not None:
                try:
                    metrics = read_measurement(path, method, self.settings)
                    if (
                        not metrics
                        and config.analysis.name == "dynamic"
                        and Path(config.cmd[0]).name
                        in (
                            "dynamic-coverage-analysis",
                            "dynamic-coverage-analysis.exe",
                        )
                    ):
                        raise ValueError("The analyzer did not write its measurement")
                except (OSError, TypeError, ValueError, KeyError) as exc:
                    error = f"Invalid analyzer measurement for {method}: {exc}"
                    eff.warning(error)
            path.unlink(missing_ok=True)
            self.measurements.append(
                MethodMeasurement(
                    method=method,
                    iteration=iteration,
                    status=status,
                    error=error,
                    jpamb_absolute_ns=result.duration.absolute if result else None,
                    jpamb_relative_db=result.duration.relative if result else None,
                    **metrics,
                )
            )
            return result

        cont = self.state.run_next(
            benchmark=benchmark,
            score_limit=score_limit,
            workdir=workdir,
            eff=eff,
            execute=execute,
        )
        if cont is False and self.measurements[-1].status == "success":
            self.measurements[-1] = replace(
                self.measurements[-1], status="failed", error="Score limit reached"
            )
        return cont

    def scored(self, benchmark: Benchmark, results: ResultSummary):
        summary = self.state.summary()
        official = official_results(benchmark, summary, results)
        categories = {
            category: tracker.wager()
            for category, tracker in results.categories.items()
        }
        scores = {
            entry.encode(): iter(
                result.response.score(
                    benchmark.experiments[Experiment(entry, None)].results, categories
                )
                for result in entry_results
            )
            for entry, entry_results in summary.results.items()
        }
        rows = tuple(
            replace(row, score=next(scores[row.method]))
            if row.status == "success"
            else row
            for row in self.measurements
        )
        return rows, official


def read_measurement(path: Path, method: str, settings: ComponentSettings) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}  # Other JPAMB analyzers may only implement the prediction protocol.
    if data["method"] != method or data["configuration"] != asdict(settings):
        raise ValueError("Method or settings differ from the invocation")

    covered = data["covered_instructions"]
    total = data["total_instructions"]
    seconds = data["analysis_seconds"]
    outcomes = data["observed_outcomes"]
    if type(covered) is not int or type(total) is not int or not 0 <= covered <= total:
        raise ValueError("Invalid instruction counts")
    if (
        not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or seconds < 0
    ):
        raise ValueError("Invalid analysis duration")
    if not isinstance(outcomes, list) or any(
        not isinstance(value, str) for value in outcomes
    ):
        raise ValueError("Outcomes must be a list of strings")

    return {
        "covered_instructions": covered,
        "total_instructions": total,
        "analysis_seconds": seconds,
        "observed_outcomes": tuple(sorted(set(outcomes))),
    }
