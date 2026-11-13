import re

from xv6_tools import Xv6Tools


class ToolRequestError(ValueError):
    """Raised when a structured tool request is invalid."""


class Agent:
    """Deterministic tool dispatcher; this class does not call an AI service."""

    def __init__(self, xv6_tools):
        self.xv6_tools = xv6_tools

    def dispatch(self, request):
        """Validate and run a request shaped as {tool: str, arguments: dict}."""
        if not isinstance(request, dict) or set(request) != {"tool", "arguments"}:
            raise ToolRequestError(
                "A request must contain exactly 'tool' and 'arguments'"
            )

        tool = request["tool"]
        arguments = request["arguments"]
        if not isinstance(tool, str):
            raise ToolRequestError("'tool' must be a string")
        if not isinstance(arguments, dict):
            raise ToolRequestError("'arguments' must be an object")

        if tool == "list_files":
            self._validate_arguments(tool, arguments, {})
            return self.xv6_tools.list_files()
        if tool == "read_file":
            self._validate_arguments(tool, arguments, {"path": str})
            return self.xv6_tools.read_file(arguments["path"])
        if tool == "summarize":
            self._validate_arguments(tool, arguments, {"text": str})
            return self._summarize(arguments["text"])
        raise ToolRequestError(f"Unknown tool: {tool}")

    @staticmethod
    def _validate_arguments(tool, arguments, required):
        if set(arguments) != set(required):
            expected = ", ".join(required) if required else "no arguments"
            raise ToolRequestError(
                f"Tool '{tool}' requires exactly: {expected}"
            )
        for name, expected_type in required.items():
            if not isinstance(arguments[name], expected_type):
                raise ToolRequestError(
                    f"Argument '{name}' for tool '{tool}' "
                    f"must be a {expected_type.__name__}"
                )

    @staticmethod
    def _summarize(text):
        """Return at most the first two sentences, capped at 40 words."""
        normalized = " ".join(text.split())
        if not normalized:
            return "No text supplied to summarize."

        sentences = re.split(r"(?<=[.!?])\s+", normalized)
        summary = " ".join(sentences[:2])
        words = summary.split()
        if len(words) > 40:
            summary = " ".join(words[:40])
            if len(sentences) > 2 or len(" ".join(sentences[:2]).split()) > 40:
                summary = summary.rstrip(".!?") + "..."
        elif len(sentences) > 2:
            summary = summary.rstrip(".!?") + "..."
        return summary


def create_agent(bridge):
    """Build an agent wired to the existing xv6 bridge."""
    return Agent(Xv6Tools(bridge))
