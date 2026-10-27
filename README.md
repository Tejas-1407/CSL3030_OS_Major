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

## Team Notes

Add important decisions, experiments, assumptions, and test results to `docs/` as the project develops.
