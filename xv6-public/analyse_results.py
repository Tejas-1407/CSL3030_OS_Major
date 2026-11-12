#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


POLICIES = ("RR", "EDF", "EDF_DONATION")
CONFIGURATIONS = ("Low", "Medium", "High")
DEFAULT_CSV = (
    Path(__file__).resolve().parent
    / "results"
    / "20261112_224846_031022"
    / "benchmark_results.csv"
)
REQUIRED_FIELDS = {
    "policy",
    "configuration",
    "workflow_id",
    "elapsed_ticks",
    "deadline_miss",
}


def load_results(csv_path):
    with csv_path.open(newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing_fields = REQUIRED_FIELDS - set(reader.fieldnames or ())
        if missing_fields:
            raise ValueError(
                "CSV is missing required columns: "
                + ", ".join(sorted(missing_fields))
            )

        rows = []
        seen = set()
        for line_number, row in enumerate(reader, start=2):
            policy = row["policy"]
            configuration = row["configuration"]
            if policy not in POLICIES or configuration not in CONFIGURATIONS:
                raise ValueError(
                    f"Unexpected policy or configuration on CSV line {line_number}"
                )
            try:
                workflow_id = int(row["workflow_id"])
                elapsed_ticks = int(row["elapsed_ticks"])
                deadline_miss = int(row["deadline_miss"])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid numeric measurement on CSV line {line_number}"
                ) from exc
            if elapsed_ticks < 0 or deadline_miss not in (0, 1):
                raise ValueError(f"Invalid measurement on CSV line {line_number}")

            key = (policy, configuration, workflow_id)
            if key in seen:
                raise ValueError(f"Duplicate workflow result on CSV line {line_number}")
            seen.add(key)
            rows.append(
                {
                    "policy": policy,
                    "configuration": configuration,
                    "workflow_id": workflow_id,
                    "elapsed_ticks": elapsed_ticks,
                    "deadline_miss": deadline_miss,
                }
            )

    expected = {
        (policy, configuration, workflow_id)
        for policy in POLICIES
        for configuration in CONFIGURATIONS
        for workflow_id in (1, 2, 3)
    }
    if seen != expected:
        missing = expected - seen
        extra = seen - expected
        raise ValueError(
            f"CSV does not contain the complete experiment "
            f"(missing={len(missing)}, unexpected={len(extra)})"
        )
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Summarize and graph an xv6 scheduler benchmark CSV."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        type=Path,
        default=DEFAULT_CSV,
        help=f"benchmark CSV (default: {DEFAULT_CSV})",
    )
    args = parser.parse_args()
    rows = load_results(args.csv_path)
    analysis_dir = args.csv_path.resolve().parent / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    grouped = defaultdict(list)
    misses = defaultdict(int)
    for row in rows:
        grouped[(row["policy"], row["configuration"])].append(
            row["elapsed_ticks"]
        )
        misses[row["policy"]] += row["deadline_miss"]

    averages = {
        key: sum(times) / len(times)
        for key, times in grouped.items()
    }
    overall_averages = {
        policy: sum(
            row["elapsed_ticks"] for row in rows if row["policy"] == policy
        )
        / sum(1 for row in rows if row["policy"] == policy)
        for policy in POLICIES
    }

    print("Average workflow completion time (ticks) and deadline misses")
    print(f"{'Configuration':<14} {'Policy':<15} {'Average ticks':>13} {'Misses':>8}")
    for configuration in CONFIGURATIONS:
        for policy in POLICIES:
            config_misses = sum(
                row["deadline_miss"]
                for row in rows
                if row["policy"] == policy
                and row["configuration"] == configuration
            )
            print(
                f"{configuration:<14} {policy:<15} "
                f"{averages[(policy, configuration)]:>13.2f} "
                f"{config_misses:>8}"
            )

    print("\nBest measured scheduler by workload (lowest average elapsed ticks)")
    for configuration in CONFIGURATIONS:
        best_time = min(averages[(policy, configuration)] for policy in POLICIES)
        winners = [
            policy
            for policy in POLICIES
            if averages[(policy, configuration)] == best_time
        ]
        print(
            f"{configuration}: {', '.join(winners)} "
            f"({best_time:.2f} ticks average)"
        )

    print("\nOverall average workflow completion time (ticks)")
    for policy in POLICIES:
        print(f"{policy}: {overall_averages[policy]:.2f}")

    figure, axis = plt.subplots()
    axis.bar(POLICIES, [overall_averages[policy] for policy in POLICIES])
    axis.set(title="Average Workflow Completion Time by Scheduler", ylabel="Ticks")
    axis.grid(axis="y", alpha=0.3)
    figure.tight_layout()
    figure.savefig(analysis_dir / "average_completion_by_scheduler.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots()
    for policy in POLICIES:
        axis.plot(
            CONFIGURATIONS,
            [averages[(policy, configuration)] for configuration in CONFIGURATIONS],
            marker="o",
            label=policy,
        )
    axis.set(
        title="Average Completion Time Across Workloads",
        xlabel="Workload configuration",
        ylabel="Average elapsed ticks",
    )
    axis.grid(alpha=0.3)
    axis.legend()
    figure.tight_layout()
    figure.savefig(analysis_dir / "completion_time_by_workload.png", dpi=150)
    plt.close(figure)

    figure, axis = plt.subplots()
    axis.bar(POLICIES, [misses[policy] for policy in POLICIES])
    axis.set(title="Deadline Misses by Scheduler", ylabel="Workflow deadline misses")
    axis.grid(axis="y", alpha=0.3)
    figure.tight_layout()
    figure.savefig(analysis_dir / "deadline_misses_by_scheduler.png", dpi=150)
    plt.close(figure)

    print(f"\nGraphs saved to {analysis_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
