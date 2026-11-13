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
        cpus = set()
        policies = set()
        workloads = set()
        repetitions = set()
        for line_number, row in enumerate(reader, start=2):
            policy = row["policy"]
            configuration = row.get("workload") or row["configuration"]
            if policy not in POLICIES or configuration not in CONFIGURATIONS:
                raise ValueError(
                    f"Unexpected policy or configuration on CSV line {line_number}"
                )
            try:
                cpu_count = int(row.get("cpu_count") or 1)
                repetition = int(row.get("repetition") or 1)
                workflow_id = int(row["workflow_id"])
                elapsed_ticks = int(row["elapsed_ticks"])
                deadline_miss = int(row["deadline_miss"])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid numeric measurement on CSV line {line_number}"
                ) from exc
            if (
                cpu_count not in (1, 3)
                or repetition < 1
                or elapsed_ticks < 0
                or deadline_miss not in (0, 1)
            ):
                raise ValueError(f"Invalid measurement on CSV line {line_number}")

            key = (cpu_count, policy, configuration, repetition, workflow_id)
            if key in seen:
                raise ValueError(f"Duplicate workflow result on CSV line {line_number}")
            seen.add(key)
            cpus.add(cpu_count)
            policies.add(policy)
            workloads.add(configuration)
            repetitions.add(repetition)
            rows.append(
                {
                    "cpu_count": cpu_count,
                    "repetition": repetition,
                    "policy": policy,
                    "configuration": configuration,
                    "workflow_id": workflow_id,
                    "elapsed_ticks": elapsed_ticks,
                    "deadline_miss": deadline_miss,
                }
            )

    if not rows:
        raise ValueError("CSV contains no workflow measurements")
    expected = {
        (cpu_count, policy, configuration, repetition, workflow_id)
        for cpu_count in cpus
        for policy in policies
        for configuration in workloads
        for repetition in range(1, max(repetitions) + 1)
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
        grouped[
            (row["cpu_count"], row["policy"], row["configuration"])
        ].append(
            row["elapsed_ticks"]
        )
        misses[
            (row["cpu_count"], row["policy"], row["configuration"])
        ] += row["deadline_miss"]

    averages = {
        key: sum(times) / len(times)
        for key, times in grouped.items()
    }
    selected_policies = [
        policy
        for policy in POLICIES
        if policy in {row["policy"] for row in rows}
    ]
    selected_workloads = [
        workload
        for workload in CONFIGURATIONS
        if workload in {row["configuration"] for row in rows}
    ]

    for cpu_count in sorted({row["cpu_count"] for row in rows}):
        cpu_rows = [row for row in rows if row["cpu_count"] == cpu_count]
        overall_averages = {
            policy: sum(
                row["elapsed_ticks"]
                for row in cpu_rows
                if row["policy"] == policy
            )
            / sum(1 for row in cpu_rows if row["policy"] == policy)
            for policy in selected_policies
        }

        print(
            f"CPUS={cpu_count}: average workflow completion time (ticks) "
            "and deadline misses"
        )
        print(
            f"{'Workload':<14} {'Policy':<15} "
            f"{'Average ticks':>13} {'Misses':>8}"
        )
        for configuration in selected_workloads:
            for policy in selected_policies:
                print(
                    f"{configuration:<14} {policy:<15} "
                    f"{averages[(cpu_count, policy, configuration)]:>13.2f} "
                    f"{misses[(cpu_count, policy, configuration)]:>8}"
                )

        print("\nBest measured scheduler by workload (lowest average elapsed ticks)")
        for configuration in selected_workloads:
            best_time = min(
                averages[(cpu_count, policy, configuration)]
                for policy in selected_policies
            )
            winners = [
                policy
                for policy in selected_policies
                if averages[(cpu_count, policy, configuration)] == best_time
            ]
            print(
                f"{configuration}: {', '.join(winners)} "
                f"({best_time:.2f} ticks average)"
            )

        print("\nOverall average workflow completion time (ticks)")
        for policy in selected_policies:
            print(f"{policy}: {overall_averages[policy]:.2f}")

        suffix = f"_cpus{cpu_count}"
        figure, axis = plt.subplots()
        axis.bar(
            selected_policies,
            [overall_averages[policy] for policy in selected_policies],
        )
        axis.set(
            title=f"Average Workflow Completion Time by Scheduler (CPUS={cpu_count})",
            ylabel="Ticks",
        )
        axis.grid(axis="y", alpha=0.3)
        figure.tight_layout()
        figure.savefig(
            analysis_dir / f"average_completion_by_scheduler{suffix}.png",
            dpi=150,
        )
        plt.close(figure)

        figure, axis = plt.subplots()
        for policy in selected_policies:
            axis.plot(
                selected_workloads,
                [
                    averages[(cpu_count, policy, configuration)]
                    for configuration in selected_workloads
                ],
                marker="o",
                label=policy,
            )
        axis.set(
            title=f"Average Completion Time Across Workloads (CPUS={cpu_count})",
            xlabel="Workload configuration",
            ylabel="Average elapsed ticks",
        )
        axis.grid(alpha=0.3)
        axis.legend()
        figure.tight_layout()
        figure.savefig(
            analysis_dir / f"completion_time_by_workload{suffix}.png", dpi=150
        )
        plt.close(figure)

        figure, axis = plt.subplots()
        axis.bar(
            selected_policies,
            [
                sum(
                    misses[(cpu_count, policy, workload)]
                    for workload in selected_workloads
                )
                for policy in selected_policies
            ],
        )
        axis.set(
            title=f"Deadline Misses by Scheduler (CPUS={cpu_count})",
            ylabel="Workflow deadline misses",
        )
        axis.grid(axis="y", alpha=0.3)
        figure.tight_layout()
        figure.savefig(
            analysis_dir / f"deadline_misses_by_scheduler{suffix}.png", dpi=150
        )
        plt.close(figure)

    print(f"\nGraphs saved to {analysis_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
