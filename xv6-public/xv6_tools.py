import re


SAFE_XV6_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
ELF_MAGIC = "\x7fELF"
ELF_EXECUTABLE_MESSAGE = (
    "This is a compiled ELF executable, not a text file. I can identify it, "
    "but cannot display its contents as readable source code."
)


class Xv6ToolError(ValueError):
    pass


class Xv6Tools:
    """Read-only tools scoped to direct files in the xv6 filesystem root."""

    def __init__(self, bridge):
        self.bridge = bridge

    def list_files(self):
        return self.bridge.run_command("ls")

    def read_file(self, path):
        if not isinstance(path, str) or not path:
            raise Xv6ToolError("File path must be a non-empty relative filename")
        if (
            path in (".", "..")
            or not SAFE_XV6_FILENAME.fullmatch(path)
        ):
            raise Xv6ToolError(
                "Only a single filename inside the xv6 exercise filesystem "
                "root is allowed"
            )

        output = self.bridge.run_command(f"cat {path}")
        if output.startswith(f"cat: cannot open {path}"):
            raise Xv6ToolError(f"File not found in xv6: {path}")
        if output.startswith("cat: "):
            raise Xv6ToolError(f"xv6 could not read {path}: {output}")
        if output.startswith(ELF_MAGIC):
            return ELF_EXECUTABLE_MESSAGE
        return output
