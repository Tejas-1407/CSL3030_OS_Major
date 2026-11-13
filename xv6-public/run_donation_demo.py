#!/usr/bin/env python3
"""Compare EDF and EDF_DONATION on a four-stage contended pipe workflow."""

import argparse
import csv
import re
import sys
from datetime import datetime

from run_benchmarks import RESULTS_DIR, run_policy


POLICIES = ("EDF", "EDF_DONATION")
DONATION_RE = re.compile(
    rb"^DONATION donor=(\d+) pipe=(\S+) receiver=(\d+) deadline=(\d+)\s*$",
    re.MULTILINE,
)
STAGE_RE = re.compile(
    rb"^PIPELINE_STAGE stage=(\d+) pid=(\d+) deadline=(\d+)\s*$",
    re.MULTILINE,
)
HOG_RE = re.compile(rb"^PIPELINE_HOG pid=(\d+) deadline=(\d+)\s*$", re.MULTILINE)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compare EDF against EDF_DONATION in the focused pipe test."
    )
    parser.add_argument("--cpus", type=int, choices=(1, 3), default=1)
    parser.add_argument("--repetitions", type=int, default=1)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    experiment_dir = RESULTS_DIR / (
        "donation_demo_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    )
    experiment_dir.mkdir()
    rows = []

    for policy in POLICIES:
        for repetition in range(1, args.repetitions + 1):
            output, results, summary, errors = run_policy(
                policy,
                "donation_pipeline_test",
                4,
                args.cpus,
                expected_workflows=1,
                deadlines=None,
            )
            console_path = experiment_dir / (
                f"{policy.lower()}_cpus{args.cpus}_rep{repetition:02d}_console.log"
            )
            console_path.write_bytes(output)
            donation_events = [
                (
                    int(donor),
                    pipe.decode("ascii", errors="replace"),
                    int(receiver),
                    int(deadline),
                )
                for donor, pipe, receiver, deadline in DONATION_RE.findall(output)
            ]
            stage_pids = {
                int(stage): int(pid)
                for stage, pid, _ in STAGE_RE.findall(output)
            }
            hog_match = HOG_RE.search(output)
            if len(stage_pids) != 4:
                errors.append(
                    f"expected PIDs for 4 pipeline stages, received {len(stage_pids)}"
                )
            if hog_match is None:
                errors.append("CPU hog PID/deadline marker was not received")
            elif int(hog_match.group(1)) in set(stage_pids.values()):
                errors.append("CPU hog PID is not independent of the pipeline")
            if len(stage_pids) == 4:
                expected_links = {
                    (stage_pids[2], stage_pids[1]),
                    (stage_pids[3], stage_pids[2]),
                    (stage_pids[4], stage_pids[3]),
                }
                actual_links = {
                    (donor, receiver)
                    for donor, _pipe, receiver, _deadline in donation_events
                }
                pipe_ids = {pipe for _donor, pipe, _receiver, _deadline in donation_events}
                if actual_links != expected_links or len(pipe_ids) != 3:
                    errors.append(
                        "donation events did not show all three downstream "
                        "donor-to-writer pipe dependencies"
                    )

            result = results[0] if len(results) == 1 else {}
            completed = summary[1] if summary is not None else 0
            row = {
                "policy": policy,
                "cpu_count": args.cpus,
                "repetition": repetition,
                "workload": "four_stage_pipe_plus_cpu_hog",
                "completed_workflows": completed,
                "elapsed_ticks": result.get("elapsed_ticks", ""),
                "deadline_ticks": result.get("deadline_ticks", 100),
                "deadline_misses": summary[2] if summary is not None else "",
                "donation_event_count": len(donation_events),
                "donation_events": ";".join(
                    f"donor={donor},pipe={pipe},receiver={receiver},deadline={deadline}"
                    for donor, pipe, receiver, deadline in donation_events
                ),
                "stage_pids": ";".join(
                    f"stage{stage}={stage_pids[stage]}"
                    for stage in sorted(stage_pids)
                ),
                "hog_pid": int(hog_match.group(1)) if hog_match else "",
                "status": "success" if not errors else "failed/incomplete",
                "errors": "; ".join(errors),
            }
            rows.append(row)
            if errors:
                print(
                    f"[{policy} rep {repetition}] FAILED: {'; '.join(errors)} "
                    f"(console: {console_path})",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[{policy} rep {repetition}] completed={completed} "
                    f"elapsed={row['elapsed_ticks']} ticks "
                    f"deadline_misses={row['deadline_misses']} "
                    f"donation_events={len(donation_events)}"
                )

    csv_path = experiment_dir / "donation_demo_results.csv"
    fields = tuple(rows[0]) if rows else ()
    with csv_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary_path = experiment_dir / "comparison_summary.txt"
    with summary_path.open("w") as summary_file:
        summary_file.write(
            f"Four-stage pipe workflow plus unrelated CPU hog; "
            f"CPUS={args.cpus}; repetitions={args.repetitions}\n"
        )
        for row in rows:
            summary_file.write(
                f"{row['policy']}: status={row['status']} "
                f"completed={row['completed_workflows']} "
                f"elapsed_ticks={row['elapsed_ticks']} "
                f"deadline_misses={row['deadline_misses']} "
                f"donation_events={row['donation_event_count']} "
                f"stage_pids={row['stage_pids']} hog_pid={row['hog_pid']}\n"
                f"  {row['donation_events']}\n"
            )
            if row["errors"]:
                summary_file.write(f"  errors={row['errors']}\n")

    print(f"CSV: {csv_path}")
    print(f"Summary: {summary_path}")
    print(f"Raw consoles: {experiment_dir}")
    return 1 if any(row["status"] != "success" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
