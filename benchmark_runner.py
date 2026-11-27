#!/usr/bin/env python3
"""Ablation matrix runner for dynamic coverage analysis.

Runs all combinations of component toggles, prints a comparison table,
and explicitly identifies the Pareto-optimal configuration (best score & speed).
"""

import argparse
import itertools
import os
import re
import statistics
import subprocess
import time

TOTAL_ROW_RE = re.compile(
    r"Total\s+([0-9.]+)\s+([0-9.]+)\s*Db\s+([0-9.]+)\s*s"
)
TOTAL_SCORE_FALLBACK = re.compile(r"Total\s+([0-9.]+)")


def run_single(cmd: list[str], env: dict[str, str]) -> tuple[float, float | None, float | None, float | None]:
    """Runs a single analysis invocation.

    Returns:
        (wall_time_s, score, jpamb_time_rel_db, jpamb_time_abs_s)
    """
    start = time.perf_counter()
    full_env = os.environ.copy()
    # Strip any leaked DISABLE_* flags from the parent environment
    for k in list(full_env.keys()):
        if k.startswith("DISABLE_"):
            del full_env[k]
    full_env.update(env)

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=full_env)
    wall_time = time.perf_counter() - start

    score = None
    time_rel = None
    time_abs = None

    match = TOTAL_ROW_RE.search(res.stdout)
    if match:
        score = float(match.group(1))
        time_rel = float(match.group(2))
        time_abs = float(match.group(3))
    else:
        fallback = TOTAL_SCORE_FALLBACK.search(res.stdout)
        if fallback:
            score = float(fallback.group(1))

    return wall_time, score, time_rel, time_abs


def main():
    parser = argparse.ArgumentParser(description="Run full ablation matrix across all component toggles")
    parser.add_argument(
        "-n", "--iterations", type=int, default=3, help="Number of iterations per combination (default: 3)"
    )
    parser.add_argument(
        "--filter", default=None, help="Suite filter flag for jpamb (e.g. Randomness, or None for entire suite)"
    )
    parser.add_argument(
        "--analysis", default="dynamic-coverage-analysis", help="Analysis tool (default: dynamic-coverage-analysis)"
    )
    args = parser.parse_args()

    cmd = ["jpamb", "-vv", "analyse"]
    if args.filter:
        cmd.extend(["--filter", args.filter])
    cmd.append(args.analysis)

    # 4 factors: Static Seeds, Dictionary, Dynamic Struct, Syntactic Struct
    factors = [
        ("StaticSeeds", "DISABLE_STATIC_SEEDS"),
        ("Dict", "DISABLE_DICTIONARY"),
        ("DynamicStruct", "DISABLE_DYNAMIC_STRUCTURE"),
        ("Syntactic", "DISABLE_SYNTACTIC_STRUCTURE"),
    ]

    # Generate all 2^4 = 16 combinations (or True/False for each)
    combinations = list(itertools.product([True, False], repeat=len(factors)))

    print("=" * 85)
    print(f"       DYNAMIC COVERAGE ABLATION MATRIX ({len(combinations)} configurations, {args.iterations} runs each)")
    print(f"Command: {' '.join(cmd)}")
    print("=" * 85 + "\n")

    results = []

    for idx, combo in enumerate(combinations, 1):
        env_vars = {
            "DISABLE_STATIC_SEEDS": "0",
            "DISABLE_DICTIONARY": "0",
            "DISABLE_SYNTACTIC_STRUCTURE": "0",
            "DISABLE_DYNAMIC_STRUCTURE": "0",
        }
        config_name_parts = []
        for (name, var), is_enabled in zip(factors, combo):
            if is_enabled:
                config_name_parts.append(f"+{name}")
                env_vars[var] = "0"
            else:
                config_name_parts.append(f"-{name}")
                env_vars[var] = "1"

        config_label = " ".join(config_name_parts)
        print(f"[{idx}/{len(combinations)}] Testing config: {config_label}")

        walls = []
        scores = []
        cpu_times = []
        rel_times = []

        for i in range(1, args.iterations + 1):
            wall, score, rel, abs_t = run_single(cmd, env_vars)
            walls.append(wall)
            if score is not None:
                scores.append(score)
            if abs_t is not None:
                cpu_times.append(abs_t)
            if rel is not None:
                rel_times.append(rel)

            s_str = f"{score:.2f}" if score is not None else "N/A"
            w_str = f"{wall:.2f}s"
            cpu_str = f"{abs_t:.2f}s" if abs_t is not None else "N/A"
            print(f"    Run {i}/{args.iterations}: Wall={w_str} | CPU={cpu_str} | Score={s_str}")

        mean_score = statistics.mean(scores) if scores else 0.0
        mean_wall = statistics.mean(walls)
        mean_cpu = statistics.mean(cpu_times) if cpu_times else 0.0
        mean_rel = statistics.mean(rel_times) if rel_times else 0.0

        results.append({
            "idx": idx,
            "combo": combo,
            "label": config_label,
            "score": mean_score,
            "wall": mean_wall,
            "cpu": mean_cpu,
            "rel": mean_rel,
        })
        print()

    # Print final Markdown / Ascii Summary Table
    print("\n" + "=" * 92)
    print("                                  ABLATION RESULTS TABLE")
    print("=" * 92)
    header = (
        f"{'#':<3} | {'Static':^7} | {'Dict':^5} | {'DynStruct':^9} | {'Syntactic':^9} | "
        f"{'Score':>7} | {'Wall Time':>10} | {'CPU Time':>9} | {'Rel Time':>8}"
    )
    print(header)
    print("-" * 92)

    for r in results:
        s_seed = "ON" if r["combo"][0] else "OFF"
        s_dict = "ON" if r["combo"][1] else "OFF"
        s_dyn = "ON" if r["combo"][2] else "OFF"
        s_synt = "ON" if r["combo"][3] else "OFF"

        line = (
            f"{r['idx']:<3} | {s_seed:^7} | {s_dict:^5} | {s_dyn:^9} | {s_synt:^9} | "
            f"{r['score']:>7.2f} | {r['wall']:>9.2f}s | {r['cpu']:>8.2f}s | {r['rel']:>6.2f}Db"
        )
        print(line)

    print("=" * 92)

    # Automatically identify optimal configurations
    max_score = max(r["score"] for r in results)
    best_score_configs = [r for r in results if r["score"] >= max_score - 0.05]
    fastest_best = min(best_score_configs, key=lambda r: r["wall"])
    fastest_overall = min(results, key=lambda r: r["wall"])

    def fmt_cfg(r):
        return (
            f"Config #{r['idx']} ({r['label']}): "
            f"Score = {r['score']:.2f}, Wall Time = {r['wall']:.2f}s, CPU Time = {r['cpu']:.2f}s"
        )

    print("\n" + "=" * 80)
    print("                             OPTIMAL CONFIGURATION")
    print("=" * 80)
    print(f"[*] Highest Score Observed:      {max_score:.2f}")
    print(f"[*] Fastest Configuration:       {fmt_cfg(fastest_overall)}")
    print(f"[*] Optimal (Top Score + Fast):  {fmt_cfg(fastest_best)}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
