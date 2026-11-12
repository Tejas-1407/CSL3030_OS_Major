# xv6 Baseline Inspection

This report documents the existing source tree only. No kernel behavior or implementation code was changed.

## Version and architecture

- This is the legacy MIT `xv6-public` for 32-bit x86, not the RISC-V xv6 tree. Its README describes the x86 multiprocessor version; the Makefile builds with `-m32` and boots a PC-style image through QEMU.
- The source README credits code copyright 2006–2018. No upstream tag or revision is pinned in this tree, so a more specific upstream release cannot be established from the inspected files.
- The tree has local `hello` and `add` syscall additions and user programs, so it is not an unmodified upstream checkout.
- `NPROC` is 64 and `NCPU` is 8 in `param.h`.

## Processes and scheduling

`struct proc` in `proc.h` currently contains:

| Field | Role |
|---|---|
| `sz` | Process memory size |
| `pgdir` | User page table |
| `kstack` | Kernel stack |
| `state` | Current process state |
| `pid` | Process ID |
| `parent` | Parent process |
| `tf` | Trap frame |
| `context` | Saved kernel context for `swtch()` |
| `chan` | Sleep channel, or null when not sleeping |
| `killed` | Indicates a pending kill |
| `ofile` | Open-file table |
| `cwd` | Current working directory |
| `name` | Debugging name |

There are no deadline, priority, or pipe-writer/donation fields in this structure.

The `enum procstate` values are `UNUSED`, `EMBRYO`, `SLEEPING`, `RUNNABLE`, `RUNNING`, and `ZOMBIE`.

Each CPU runs `scheduler()` in `proc.c`. Under `ptable.lock`, it scans the process table from beginning to end and runs every process it finds in `RUNNABLE` state, switching to each with `swtch()`. Thus selection is a process-table-order scan, not priority- or deadline-based scheduling. The timer interrupt in `trap.c` calls `yield()` for a running process, allowing it to be scheduled again. The scheduler has no explicit deadline or priority policy.

`sleep(chan, lk)` acquires `ptable.lock` before releasing the caller's lock, records `chan`, changes the process state to `SLEEPING`, and switches to the scheduler. This lock ordering prevents a missed wakeup. On resumption it clears `chan` and reacquires the caller's lock. `wakeup(chan)` scans the process table under `ptable.lock` and changes every sleeping process on the matching channel to `RUNNABLE`.

## Pipes

There is no separate `pipe.h`; `struct pipe` is private to `pipe.c`. It contains a spinlock, a 512-byte data buffer, read/write sequence counters (`nread`, `nwrite`), and open flags (`readopen`, `writeopen`). It does not record a writer PID or associate a blocked reader with a particular writer.

- If a reader finds the pipe empty while the write end is open, `piperead()` calls `sleep(&p->nread, &p->lock)`. `sleep()` atomically releases the pipe lock while blocked and reacquires it on wakeup.
- After writing data, `pipewrite()` wakes processes sleeping on `&p->nread`. It also performs that wakeup before sleeping if the pipe is full.
- If the pipe is full, a writer sleeps on `&p->nwrite`; `piperead()` wakes that channel after consuming data.
- `pipewrite()` can call `myproc()` while executing, but the pipe does not persist that process identity for a reader to use later.

## Syscall infrastructure

The current syscall numbers are in `syscall.h`, sequentially defined from `SYS_fork` = 1 through `SYS_add` = 23. The two local additions are `SYS_hello` = 22 and `SYS_add` = 23.

User stubs in `usys.S` load the syscall number into `%eax` and execute `int $T_SYSCALL`. `trap.c` recognizes that trap and invokes `syscall()`. The dispatcher in `syscall.c` uses `%eax` to index the syscall table and stores the handler's return value back in `%eax`; unknown numbers are logged and return `-1`.

To add a syscall following this tree's pattern:

1. Assign the next unused number in `syscall.h`.
2. Implement the `sys_<name>` handler (the existing custom handlers are in `sysproc.c`) and add its `extern` declaration and dispatch-table entry in `syscall.c`.
3. Declare the user function in `user.h`.
4. Add `SYSCALL(name)` to `usys.S`.
5. Add or update a user program and list its underscore-prefixed executable in `Makefile`'s `UPROGS`.

If a handler calls a new kernel helper across source files, add the helper's declaration to `defs.h` as appropriate.

## Build, boot, and user programs

Run these commands from `xv6-public/`:

```sh
make
make qemu-nox
```

`make` builds the kernel, boot image, file-system image, and user executables. `make qemu-nox` runs the images in QEMU using the terminal. The Makefile can also use `make qemu` for its serial-monitor mode. It detects a native i386-capable toolchain or an `i386-jos-elf-` cross-toolchain and detects QEMU (`qemu`, `qemu-system-i386`, or `qemu-system-x86_64`).

At inspection time, generated build outputs were present and `make -q` returned 0 (Make considered its targets up to date). QEMU executables and the `i386-jos-elf-gcc` cross-compiler were not available in the host `PATH`, so booting was not verified. No build was run during this inspection.

User programs are compiled from `name.c` to `name.o`, then linked as `_name` against `ulib.o`, `usys.o`, `printf.o`, and `umalloc.o`; `fs.img` packages the programs listed in `UPROGS`. Existing project-specific user programs are `mytest.c`, `hello_test.c`, and `add_test.c`. Existing xv6 test programs include `usertests.c` and `forktest.c`; the Makefile also includes standard utilities such as `stressfs`.

## Likely implementation files

The smallest likely core set is:

- `proc.h` — add per-process deadline and effective/donated scheduling metadata, once semantics are settled.
- `proc.c` — initialize/copy/clear that metadata and select the runnable process according to the agreed scheduling policy.
- `pipe.c` — track the relevant writer/dependency and apply or withdraw donation as readers block, wake, or pipe endpoints close.

For user programs to configure scheduling metadata or inspect results, the likely syscall/API files are `syscall.h`, `syscall.c`, `sysproc.c`, `user.h`, and `usys.S`. Add a scheduler/pipe test program or extend an existing test such as `mytest.c`, and register it in `Makefile`. `defs.h` is needed only if new kernel helpers are shared across source files. `trap.c` may need changes only if the final deadline/time-accounting design requires behavior beyond its existing timer ticks and preemption.

The AI-agent layer and controlled QEMU bridge are not present in the inspected xv6 source tree and are outside this kernel-file mapping.

## Recommended implementation order

1. Specify deadline units, tie-breaking, donation semantics, and how donation is cleared on wakeup, close, kill, or process exit.
2. Define the user-facing control/observation API and the tests that will verify scheduling and donation.
3. Add process metadata with correct initialization and lifecycle handling.
4. Implement and test runnable-process selection.
5. Add pipe dependency tracking and donation lifecycle handling; test blocking, wakeup, full/closed pipes, and multiple processes.
6. Run the existing xv6 tests and the new targeted tests under QEMU, then record the baseline and behavior changes separately.
