# OS Major — Deadline Scheduler with Priority Donation Through Pipes

**Course:** CSL3030 — Operating Systems  
**Group:** 4  
**Platform:** xv6 on QEMU  
**Development:** VS Code + Git + GitHub Copilot

## 1. Project Overview

This project extends xv6 with a deadline-aware scheduling mechanism and priority/deadline donation through process dependencies connected by pipes.

The project also includes an AI-agent layer running on the host. The agent interacts with xv6 through controlled, structured tools and a QEMU bridge. The AI layer assists with workflow-level actions and observations; the xv6 kernel remains responsible for enforcing scheduling and OS policy.

### High-level architecture

```text
                         HOST
                          |
                    +-------------+
                    | AI Agent    |
                    | (Python)    |
                    +------+------+ 
                           |
                    structured tools
                           |
                    +------v------+
                    | Validator   |
                    +------+------+
                           |
                    +------v------+
                    | QEMU Bridge |
                    +------+------+
                           |
===========================|========================
                           |
                          xv6
                           |
                    +------v------+
                    | User        |
                    | Processes   |
                    +------+------+
                           |
                    +------v------+
                    | xv6 Kernel  |
                    |             |
                    | EDF         |
                    | Donation    |
                    | Pipes       |
                    +-------------+
```

## 2. Core OS Concepts

The main OS-side concepts are:

- **Pipeline:** multiple processing stages connected sequentially.
- **Pipe:** an inter-process communication channel.
- **Blocking / sleeping:** a process waits because it cannot currently proceed.
- **RUNNABLE:** a process is ready to run but waiting for CPU time.
- **RUNNING:** a process currently has the CPU.
- **EDF (Earliest Deadline First):** among runnable processes, prefer the earliest effective deadline.
- **Deadline / priority donation:** urgency can propagate backward through process dependencies.

## 3. AI Agent Layer

The agent layer follows this general flow:

```text
User request
    |
    v
Agent / Planner
    |
    v
Structured tool call
    |
    v
Tool validation
    |
    v
QEMU bridge
    |
    v
xv6
    |
    v
Observation
    |
    +------> Agent
```

The intended trust boundary is:

> The AI proposes. The tool layer validates. The kernel enforces.

The AI agent is **not** intended to replace the xv6 scheduler.

## 4. Development Plan

### Track A — xv6 / Kernel

- [ ] Understand xv6 process states
- [ ] Understand the existing xv6 scheduler
- [ ] Understand xv6 pipes and blocking
- [ ] Define deadline representation
- [ ] Implement EDF scheduling
- [ ] Implement deadline/priority donation
- [ ] Handle donation through dependency chains
- [ ] Build kernel/user-space tests
- [ ] Measure and document scheduler behavior

### Track B — AI Agent

- [ ] Define the agent loop
- [ ] Build a deterministic Python agent
- [ ] Define structured tools
- [ ] Implement tool validation
- [ ] Implement the host-to-QEMU bridge
- [ ] Connect the agent to xv6
- [ ] Add the LLM/Copilot-assisted development workflow
- [ ] Add observation and logging
- [ ] Test security and invalid tool requests

### Final Integration

- [ ] Connect agent tools to xv6
- [ ] Demonstrate workflow execution
- [ ] Demonstrate deadline-aware scheduling
- [ ] Demonstrate donation through pipes
- [ ] Demonstrate agent observation of xv6 behavior
- [ ] Collect repeatable test results
- [ ] Prepare final documentation and presentation

## 5. Repository Structure

The structure will evolve as implementation progresses. A planned organization is:

```text
.
├── xv6/                  # xv6 source and kernel modifications
├── agent/                # Python AI-agent layer
├── tools/                # Structured tools and validation
├── bridge/               # Host <-> QEMU communication
├── tests/                # Integration and experiment tests
├── docs/                 # Design notes and project documentation
├── README.md
└── .gitignore
```

Do not create all directories just for the sake of structure. Add them when the corresponding component is actually started.

## 6. Copilot Development Policy

GitHub Copilot will be used throughout development as a coding assistant.

For important kernel changes:

1. Understand the existing xv6 code first.
2. Ask Copilot for explanations or small implementation suggestions.
3. Review generated code manually.
4. Keep changes small and testable.
5. Verify scheduler and synchronization behavior ourselves.
6. Record significant design decisions in `docs/`.
7. Do not treat Copilot output as authoritative.

The final implementation should be understandable by the project team, not merely generated code.

## 7. Git Workflow

Keep commits small and meaningful.

Example:

```text
main
 |
 +-- baseline xv6
 +-- scheduler exploration
 +-- deadline representation
 +-- EDF scheduler
 +-- pipe donation
 +-- agent skeleton
 +-- tool validation
 +-- QEMU bridge
 +-- integration
```

Prefer commit messages such as:

```text
feat: add deadline field to process
feat: implement earliest deadline selection
feat: add deadline donation through pipe dependency
feat: add agent tool dispatcher
fix: prevent invalid scheduler state transition
docs: update architecture
```

## 8. Current Status

**Phase:** Project setup / architecture

Current priorities:

1. Establish a clean Git repository.
2. Preserve a known-good xv6 baseline.
3. Understand the existing scheduler before modifying it.
4. Set up the development workflow with Copilot.
5. Build the OS and agent layers separately before integration.

---

## 9. Nemotron Agent

The host-side interactive agent uses NVIDIA's OpenAI-compatible Nemotron API
to choose among the `list_files`, `read_file`, `summarize`, and `project_info`
tools. `project_info` returns curated project facts without accessing files.
Every proposed call goes through `agent.py`'s deterministic dispatcher and then
the read-only `xv6_tools.py` interface. The model cannot invoke shell commands
or host processes.

### Setup and launch

From `xv6-public/`, create and activate a virtual environment and install the
Python dependencies (the project-level `.venv` is normally reused):

```sh
"$PWD/../.venv/bin/python" -m pip install -r requirements.txt
./start-agent.sh
```

The project-root `.env` file is loaded automatically. Replace its placeholder
with the NVIDIA key locally, or export `NVIDIA_API_KEY` before launch; an
exported value takes precedence. Do not commit `.env` files. The client uses
`https://integrate.api.nvidia.com/v1` and model
`nvidia/nemotron-3.5-lightning-30b-a3b`, with Nemotron thinking disabled.
Enter `exit` to leave the terminal session.

The model may list files, read one allowed file in the xv6 guest filesystem
root, summarize supplied text, or request curated OS Major project information
through `project_info`. Project questions should use `project_info`; guest
filesystem questions use the xv6 tools. When a filename is explicit, the agent
reads it directly rather than listing first. ELF executables are identified as
compiled binaries and are not displayed as source text. Each user request is
limited to five tool calls. The bridge boots the existing `EDF_DONATION`,
`CPUS=1` QEMU image only when a guest filesystem tool is requested.

### Trust boundaries and limitations

Nemotron output is untrusted: the model's structured requests are validated by
the existing dispatcher, and the bridge independently permits only `ls` and
`cat <single filename>`. xv6 kernel taint checks are a separate enforcement
layer; a system prompt is not a security boundary. File content can influence
the model's response or cause it to propose rejected actions, so prompt
injection resistance is not guaranteed. The service requires network access
and is subject to NVIDIA API availability, rate limits, and account quotas.
Automated LLM tests use mocked responses and do not call the service.

## Team Notes

Add important decisions, experiments, assumptions, and test results to `docs/` as the project develops.
