#!/usr/bin/env python3
"""Interactive terminal for the Nemotron-enabled xv6 agent."""

import sys

from agent import create_agent
from llm_agent import (
    LLMAgent,
    LLMAgentError,
    create_nvidia_client,
)
from xv6_bridge import Xv6Bridge, Xv6BridgeError


def main():
    bridge = Xv6Bridge()
    try:
        client = create_nvidia_client()
        agent = LLMAgent(create_agent(bridge), client=client)
        print("Nemotron xv6 agent ready. Type 'exit' to quit.")
        while True:
            try:
                instruction = input("\nUser: ").strip()
            except EOFError:
                print()
                break
            if instruction.lower() == "exit":
                break
            if not instruction:
                continue
            try:
                response = agent.run(instruction, on_event=show_event)
            except LLMAgentError as exc:
                bridge.close()
                print(f"Agent error: {exc}")
                continue
            print(f"\nAgent: {response}")
    except (LLMAgentError, Xv6BridgeError) as exc:
        print(f"Could not start the agent: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExiting.")
    finally:
        bridge.close()
    return 0


def show_event(event, details):
    if event == "assistant_message":
        print(f"\nAgent: {details['text']}")
    elif event == "tool_call":
        print(f"\nTool: {details['tool']}")
    elif event == "observation":
        if details["ok"]:
            print(f"Observation: {details['observation']}")
        else:
            print(f"Observation: rejected - {details['error']}")

if __name__ == "__main__":
    raise SystemExit(main())
