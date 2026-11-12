#!/usr/bin/env python3
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


def run_policy(policy, workload, stages):
    command = [
        "make",
        "-C",
        str(PROJECT_DIR),
        "qemu-nox",
        "SCHED_POLICY=" + policy,
        "QEMU=" + str(QEMU),
        "CPUS=" + str(CPUS),
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
    elif summary[0] != 3 or summary[1] != 3:
        errors.append(
            "expected 3 workflows completed; summary reported "
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
    if len(results) != 3:
        errors.append(f"expected 3 BENCH_RESULT lines, received {len(results)}")
    else:
        expected_wids = {1, 2, 3}
        actual_wids = [result["wid"] for result in results]
        if set(actual_wids) != expected_wids or len(set(actual_wids)) != 3:
            errors.append(
                "expected one result for workflow IDs 1, 2, and 3; received "
                + ", ".join(str(wid) for wid in actual_wids)
            )
        for result in results:
            wid = result["wid"]
            if result["stages"] != stages:
                errors.append(
                    f"workflow {wid} reported stages={result['stages']}; "
                    f"expected {stages}"
                )
            if wid in expected_wids and result["deadline_ticks"] != DEADLINES[wid - 1]:
                errors.append(
                    f"workflow {wid} reported deadline="
                    f"{result['deadline_ticks']}; expected {DEADLINES[wid - 1]}"
                )

    if summary is not None and len(results) == 3:
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


def main():
    experiment_dir = create_experiment_dir()
    rows = []
    summaries = []

    for policy in POLICIES:
        for configuration, stages, cpu_work in CONFIGURATIONS:
            workload = (
                f"sched_bench {stages} {cpu_work} "
                + " ".join(str(deadline) for deadline in DEADLINES)
            )
            run_name = f"{policy.lower()}_{configuration.lower()}"
            print(
                f"[{policy}/{configuration}] building and running "
                f"{workload} with CPUS={CPUS}",
                flush=True,
            )
            output, results, summary, errors = run_policy(
                policy, workload, stages
            )
            console_path = experiment_dir / f"{run_name}_console.log"
            console_path.write_bytes(output)

            for result in results:
                rows.append(
                    {
                        "policy": policy,
                        "configuration": configuration,
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
                (policy, configuration, stages, cpu_work, completed, misses, success)
            )
            if errors:
                print(
                    f"[{policy}/{configuration}] FAILED: {'; '.join(errors)}",
                    file=sys.stderr,
                )
                print(
                    f"[{policy}/{configuration}] captured output: {console_path}",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[{policy}/{configuration}] completed={completed} "
                    f"deadline_misses={misses}"
                )

    csv_path = experiment_dir / "benchmark_results.csv"
    with csv_path.open("w", newline="") as csv_file:
        fields = (
            "policy",
            "configuration",
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
            f"Workload comparison; CPUS={CPUS}; deadlines="
            f"{','.join(str(deadline) for deadline in DEADLINES)} ticks\n"
        )
        summary_file.write(
            "Policy          Configuration    Stages    CPU work    "
            "Completed workflows    Deadline misses    Status\n"
        )
        for (
            policy,
            configuration,
            stages,
            cpu_work,
            completed,
            misses,
            success,
        ) in summaries:
            status = "success" if success else "failed/incomplete"
            summary_file.write(
                f"{policy:<15} {configuration:<16} {stages:<8} "
                f"{cpu_work:<11} {completed if completed is not None else '-':<22} "
                f"{misses if misses is not None else '-':<18} {status}\n"
            )

    print(f"CSV: {csv_path}")
    print(f"Summary: {summary_path}")
    print(f"Raw consoles: {experiment_dir}")
    failed = any(not item[6] for item in summaries)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
