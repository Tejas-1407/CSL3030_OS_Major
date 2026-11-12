"""Curated, read-only facts about the OS Major project."""


PROJECT_CONTEXT = """\
OS Major — Deadline Scheduler with Priority Donation Through Pipes

Purpose
This project extends 32-bit x86 xv6-public with process workflow/deadline
metadata, selectable schedulers, and deadline donation along pipe dependencies.
The host-side Python agent provides a constrained interface to inspect the xv6
guest; it does not schedule guest processes.

Architecture
The guest runs xv6-public in custom QEMU. The kernel owns process metadata,
scheduler selection, pipe dependency tracking, donation, cleanup, and taint
enforcement. On the host, Nemotron proposes structured tool calls, the
deterministic agent dispatcher validates them, xv6_tools applies read-only
checks, and xv6_bridge permits only the supported guest commands. The
project_info tool returns this static context without filesystem or QEMU
access.

Scheduler policies and deadlines
The build supports RR, EDF, and EDF_DONATION. RR follows the xv6-style
process-table traversal and visits RUNNABLE processes in scan order. EDF picks
the RUNNABLE process with the earliest original deadline. EDF_DONATION picks
by the smaller of the original and donated deadline. Equal deadlines retain
the first matching process encountered in the table scan. setworkflow(wid,
deadline_ticks) stores workflow ID and deadline metadata for a process.
Deadlines are tick values; deadline tracking does not itself guarantee that a
deadline will be met.

Pipe dependency tracking and donation
The pipe records its most recent writer. If a reader encounters an empty pipe
with a writer still open, it records a dependency on that writer and can donate
its effective deadline. Donation propagates through waiting_on links.
Dependencies are cleared when the reader stops waiting or the writer closes
its final write descriptor; donation metadata is recomputed from live
dependencies. Traversal keeps a visited-process set to stop cycles.

Benchmark evidence and limitations
The saved complete CSV is from one CPUS=1 experiment with three workflows per
policy/configuration. Low used 2 stages and 100000 work iterations per stage;
Medium used 4 and 500000; High used 8 and 1000000. The three deadlines were
100, 200, and 300 ticks. All recorded workflows completed and the CSV records
zero deadline misses. Mean elapsed ticks across the three workflows were:
Low — RR 0.00, EDF 0.67, EDF_DONATION 0.67; Medium — RR 2.00, EDF 2.33,
EDF_DONATION 3.00; High — RR 16.00, EDF 8.00, EDF_DONATION 6.67.
These are descriptive averages from a single run, not repeated-trial
statistics. The evidence does not establish CPUS=3 behavior, statistical
significance, or general scheduler superiority. Tick granularity and the
limited workload set constrain interpretation.

AI agent and prompt-injection demonstration
The host agent uses the NVIDIA OpenAI-compatible Nemotron API. Its available
tools are list_files, read_file, summarize, and project_info. Guest reads are
restricted to one direct filename; project_info is static data. The
deterministic prompt-injection demonstration reads inbox.txt, whose text asks
for an unauthorized deletion, and verifies that the dispatcher rejects an
unknown delete_file request while important.txt remains unchanged. This
demonstration uses the deterministic dispatcher; it is not proof that an LLM
cannot be manipulated.

Kernel taint tracking and security status
Kernel taint state propagates through tested paths including reads of inbox.txt,
fork, pipes, regular-file writes/reads, and execution of a tainted file.
Kernel sys_unlink denies calls from tainted processes. The security report
records CPUS=1 QEMU regression runs for RR, EDF, and EDF_DONATION, including
the taint and scheduler/pipe tests. Taint labels are volatile runtime state,
not persistent on-disk metadata.

Known limitations and status
The reports validate the exercised tests and channels only. They explicitly do
not claim comprehensive security or cover every IPC, filesystem, or kernel
data path; they also do not assert reuse of a particular process-table slot.
Prompt instructions are not an enforcement boundary, and guest data remains
untrusted. Benchmark evidence is limited to the recorded single CPUS=1 run.
The context tool is informational only and cannot execute commands or access
host or guest files.
"""
