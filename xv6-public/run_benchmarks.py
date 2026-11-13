#!/usr/bin/env python3
import argparse
import csv
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = PROJECT_DIR / "results"
QEMU = Path("/home/tejas/Documents/qemu-master/build/qemu-system-i386")
POLICIES = ("RR", "EDF", "EDF_DONATION")
CONFIGURATIONS = (
    ("Low", 2, 100000),
    ("Medium", 4, 500000),
    ("High", 8, 1000000),
)
DEADLINES = (100, 200, 300)
CPUS = 1
DEFAULT_REPETITIONS = 20
START_TIMEOUT_SECONDS = 45
RUN_TIMEOUT_SECONDS = 90
SHUTDOWN_TIMEOUT_SECONDS = 8

RESULT_RE = re.compile(
    rb"^BENCH_RESULT wid=(\d+) stages=(\d+) elapsed=(\d+) "
    rb"deadline=(\d+) miss=([01])\s*$",
    re.MULTILINE,
)
SUMMARY_RE = re.compile(
    rb"^BENCH_SUMMARY workflows=(\d+) completed=(\d+) "
    rb"deadline_misses=(\d+)\s*$",
    re.MULTILINE,
)
SUMMARY_LINE_RE = re.compile(
    rb"BENCH_SUMMARY workflows=\d+ completed=\d+ deadline_misses=\d+\r?\n"
)


def stop_process_group(proc, sig):
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass


def drain_output(proc, selector, output, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            while True:
                events = selector.select(0)
                if not events:
                    return
                chunk = os.read(proc.stdout.fileno(), 65536)
                if not chunk:
                    return
                output.extend(chunk)
        events = selector.select(0.1)
        for key, _ in events:
            chunk = os.read(key.fd, 65536)
            if chunk:
                output.extend(chunk)


def run_policy(
    policy,
    workload,
    stages,
    cpus=CPUS,
    expected_workflows=3,
    deadlines=DEADLINES,
):
    command = [
        "make",
        "-C",
        str(PROJECT_DIR),
        "qemu-nox",
        "SCHED_POLICY=" + policy,
        "QEMU=" + str(QEMU),
        "CPUS=" + str(cpus),
    ]
    output = bytearray()
    errors = []
    summary = None

    if not QEMU.is_file():
        return output, [], None, ["QEMU executable not found: " + str(QEMU)]

    try:
        proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            start_new_session=True,
        )
    except OSError as exc:
        return output, [], None, ["Could not start make/QEMU: " + str(exc)]

    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    started_at = time.monotonic()
    command_sent = False
    quit_sent = False

    try:
        while proc.poll() is None:
            now = time.monotonic()
            timeout = START_TIMEOUT_SECONDS if not command_sent else RUN_TIMEOUT_SECONDS
            if now - started_at > timeout:
                errors.append(
                    "Timed out waiting for xv6 shell"
                    if not command_sent
                    else "Timed out waiting for benchmark summary"
                )
                stop_process_group(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    stop_process_group(proc, signal.SIGKILL)
                    proc.wait()
                break

            for key, _ in selector.select(0.1):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    continue
                output.extend(chunk)

            if not command_sent and b"$ " in output:
                proc.stdin.write((workload + "\n").encode())
                proc.stdin.flush()
                command_sent = True

            summary_match = SUMMARY_RE.search(output)
            if summary_match and SUMMARY_LINE_RE.search(output):
                summary = tuple(int(value) for value in summary_match.groups())
                proc.stdin.write(b"\x01x")
                proc.stdin.flush()
                proc.stdin.close()
                quit_sent = True
                break

        if quit_sent:
            try:
                proc.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                errors.append("QEMU did not exit after Ctrl-A x")
                stop_process_group(proc, signal.SIGTERM)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    stop_process_group(proc, signal.SIGKILL)
                    proc.wait()

        drain_output(proc, selector, output, 2)
    finally:
        selector.close()
        if proc.poll() is None:
            stop_process_group(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                stop_process_group(proc, signal.SIGKILL)
                proc.wait()
        if proc.stdin and not proc.stdin.closed:
            proc.stdin.close()
        if proc.stdout:
            proc.stdout.close()

    if not command_sent:
        errors.append("xv6 shell prompt was not detected")
    if summary is None:
        errors.append("benchmark summary was not received")
    elif summary[0] != expected_workflows or summary[1] != expected_workflows:
        errors.append(
            f"expected {expected_workflows} workflows completed; summary reported "
            f"workflows={summary[0]} completed={summary[1]}"
        )

    results = [
        {
            "wid": int(match[0]),
            "stages": int(match[1]),
            "elapsed_ticks": int(match[2]),
            "deadline_ticks": int(match[3]),
            "deadline_miss": int(match[4]),
        }
        for match in RESULT_RE.findall(output)
    ]
    if len(results) != expected_workflows:
        errors.append(
            f"expected {expected_workflows} BENCH_RESULT lines, "
            f"received {len(results)}"
        )
    else:
        expected_wids = set(range(1, expected_workflows + 1))
        actual_wids = [result["wid"] for result in results]
        if (
            set(actual_wids) != expected_wids
            or len(set(actual_wids)) != expected_workflows
        ):
            errors.append(
                f"expected one result for workflow IDs 1 through "
                f"{expected_workflows}; received "
                + ", ".join(str(wid) for wid in actual_wids)
            )
        for result in results:
            wid = result["wid"]
            if result["stages"] != stages:
                errors.append(
                    f"workflow {wid} reported stages={result['stages']}; "
                    f"expected {stages}"
                )
            if (
                deadlines is not None
                and wid in expected_wids
                and result["deadline_ticks"] != deadlines[wid - 1]
            ):
                errors.append(
                    f"workflow {wid} reported deadline="
                    f"{result['deadline_ticks']}; expected {deadlines[wid - 1]}"
                )

    if summary is not None and len(results) == expected_workflows:
        result_misses = sum(result["deadline_miss"] for result in results)
        if summary[2] != result_misses:
            errors.append(
                f"summary reported {summary[2]} deadline misses but result "
                f"lines reported {result_misses}"
            )

    return output, results, summary, errors


def create_experiment_dir():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    experiment_dir = RESULTS_DIR / timestamp
    experiment_dir.mkdir()
    return experiment_dir


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run repeated xv6 scheduler benchmarks under QEMU."
    )
    parser.add_argument(
        "--cpus",
        type=int,
        choices=(1, 3),
        default=CPUS,
        help="number of QEMU CPUs (default: 1)",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=DEFAULT_REPETITIONS,
        help=f"runs per policy/workload (default: {DEFAULT_REPETITIONS})",
    )
    parser.add_argument(
        "--policies",
        nargs="+",
        choices=POLICIES,
        default=list(POLICIES),
        metavar="POLICY",
        help="scheduler policies to run (default: all three)",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.repetitions < 1:
        parser.error("--repetitions must be at least 1")

    experiment_dir = create_experiment_dir()
    rows = []
    summaries = []

    for policy in args.policies:
        for configuration, stages, cpu_work in CONFIGURATIONS:
            workload = (
                f"sched_bench {stages} {cpu_work} "
                + " ".join(str(deadline) for deadline in DEADLINES)
            )
            for repetition in range(1, args.repetitions + 1):
                run_name = (
                    f"{policy.lower()}_{configuration.lower()}_"
                    f"cpus{args.cpus}_rep{repetition:02d}"
                )
                print(
                    f"[{policy}/{configuration} rep {repetition}/"
                    f"{args.repetitions}] building and running {workload} "
                    f"with CPUS={args.cpus}",
                    flush=True,
                )
                output, results, summary, errors = run_policy(
                    policy, workload, stages, args.cpus
                )
                console_path = experiment_dir / f"{run_name}_console.log"
                console_path.write_bytes(output)

                for result in results:
                    rows.append(
                        {
                            "policy": policy,
                            "workload": configuration,
                            "configuration": configuration,
                            "cpu_count": args.cpus,
                            "repetition": repetition,
                            "stages": result["stages"],
                            "CPU_work": cpu_work,
                            "workflow_id": result["wid"],
                            "elapsed_ticks": result["elapsed_ticks"],
                            "deadline_ticks": result["deadline_ticks"],
                            "deadline_miss": result["deadline_miss"],
                        }
                    )

                completed = summary[1] if summary is not None else None
                misses = summary[2] if summary is not None else None
                success = not errors
                summaries.append(
                    {
                        "policy": policy,
                        "workload": configuration,
                        "cpu_count": args.cpus,
                        "repetition": repetition,
                        "stages": stages,
                        "cpu_work": cpu_work,
                        "completed": completed,
                        "misses": misses,
                        "success": success,
                    }
                )
                if errors:
                    print(
                        f"[{policy}/{configuration} rep {repetition}] FAILED: "
                        f"{'; '.join(errors)}",
                        file=sys.stderr,
                    )
                    print(
                        f"[{policy}/{configuration}] captured output: "
                        f"{console_path}",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"[{policy}/{configuration} rep {repetition}] "
                        f"completed={completed} deadline_misses={misses}"
                    )

    csv_path = experiment_dir / "benchmark_results.csv"
    with csv_path.open("w", newline="") as csv_file:
        fields = (
            "policy",
            "workload",
            "configuration",
            "cpu_count",
            "repetition",
            "stages",
            "CPU_work",
            "workflow_id",
            "elapsed_ticks",
            "deadline_ticks",
            "deadline_miss",
        )
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary_path = experiment_dir / "comparison_summary.txt"
    with summary_path.open("w") as summary_file:
        summary_file.write(
            f"Repeated workload comparison; CPUS={args.cpus}; "
            f"repetitions={args.repetitions}; policies="
            f"{','.join(args.policies)}; deadlines="
            f"{','.join(str(deadline) for deadline in DEADLINES)} ticks\n"
        )
        summary_file.write(
            "CPU count  Policy          Workload  Repetitions  "
            "Completed workflows  Deadline misses  Mean elapsed ticks  Status\n"
        )
        groups = {}
        for item in summaries:
            key = (item["cpu_count"], item["policy"], item["workload"])
            group = groups.setdefault(
                key,
                {
                    "runs": 0,
                    "successful": 0,
                    "completed": 0,
                    "misses": 0,
                    "elapsed": [],
                },
            )
            group["runs"] += 1
            group["successful"] += int(item["success"])
            group["completed"] += item["completed"] or 0
            group["misses"] += item["misses"] or 0
            group["elapsed"].extend(
                row["elapsed_ticks"]
                for row in rows
                if row["cpu_count"] == item["cpu_count"]
                and row["policy"] == item["policy"]
                and row["workload"] == item["workload"]
                and row["repetition"] == item["repetition"]
            )

        for (cpu_count, policy, workload), group in sorted(groups.items()):
            status = (
                "success"
                if group["successful"] == group["runs"]
                else "failed/incomplete"
            )
            mean_elapsed = (
                sum(group["elapsed"]) / len(group["elapsed"])
                if group["elapsed"]
                else 0.0
            )
            summary_file.write(
                f"{cpu_count:<10} {policy:<15} {workload:<9} "
                f"{group['successful']}/{group['runs']:<11} "
                f"{group['completed']:<21} {group['misses']:<16} "
                f"{mean_elapsed:<19.2f} {status}\n"
            )

    print(f"CSV: {csv_path}")
    print(f"Summary: {summary_path}")
    print(f"Raw consoles: {experiment_dir}")
    failed = any(not item["success"] for item in summaries)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
