import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
QEMU = Path("/home/tejas/Documents/qemu-master/build/qemu-system-i386")
POLICY = "EDF_DONATION"
CPUS = 1
SHELL_PROMPT = b"$ "
START_TIMEOUT_SECONDS = 60
COMMAND_TIMEOUT_SECONDS = 15
SHUTDOWN_TIMEOUT_SECONDS = 8
SAFE_XV6_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class Xv6BridgeError(RuntimeError):
    pass


class Xv6Bridge:
    def __init__(self):
        self._process = None
        self._selector = None
        self._buffer = bytearray()

    def start(self):
        if self._process is not None:
            raise Xv6BridgeError("The xv6 bridge has already been started")
        if not QEMU.is_file():
            raise Xv6BridgeError(f"QEMU executable not found: {QEMU}")

        command = [
            "make",
            "-C",
            str(PROJECT_DIR),
            "qemu-nox",
            f"SCHED_POLICY={POLICY}",
            f"QEMU={QEMU}",
            f"CPUS={CPUS}",
        ]
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                start_new_session=True,
            )
        except OSError as exc:
            raise Xv6BridgeError(f"Could not start make/QEMU: {exc}") from exc

        self._selector = selectors.DefaultSelector()
        self._selector.register(self._process.stdout, selectors.EVENT_READ)
        try:
            self._read_until_prompt(START_TIMEOUT_SECONDS, "xv6 shell prompt")
        except Xv6BridgeError:
            self.close()
            raise
        return self

    def run_command(self, command):
        if command == "ls":
            expected_echo = "ls\n"
        elif (
            isinstance(command, str)
            and command.startswith("cat ")
            and SAFE_XV6_FILENAME.fullmatch(command[4:])
            and command[4:] not in (".", "..")
        ):
            expected_echo = command + "\n"
        else:
            raise ValueError(
                "Only 'ls' and 'cat <single xv6 filename>' are allowed"
            )
        if self._process is None or self._process.poll() is not None:
            raise Xv6BridgeError("xv6 is not running; call start() first")

        try:
            self._process.stdin.write(expected_echo.encode())
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise Xv6BridgeError("Could not send command to xv6") from exc

        output = self._read_until_prompt(
            COMMAND_TIMEOUT_SECONDS, "the xv6 command output"
        )
        output = output.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        command_echo = expected_echo.encode()
        if output.startswith(command_echo):
            output = output[len(command_echo) :]
        result = output.decode("utf-8", errors="replace").strip()
        if not result and command == "ls":
            raise Xv6BridgeError("xv6 returned no output for the 'ls' command")
        return result

    def _read_until_prompt(self, timeout, description):
        deadline = time.monotonic() + timeout
        while True:
            prompt_index = self._buffer.find(SHELL_PROMPT)
            if prompt_index >= 0:
                output = bytes(self._buffer[:prompt_index])
                del self._buffer[: prompt_index + len(SHELL_PROMPT)]
                return output

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Xv6BridgeError(
                    f"Timed out waiting for {description}. "
                    f"Recent output: {self._output_tail()}"
                )

            if self._process.poll() is not None and not self._selector.select(0):
                raise Xv6BridgeError(
                    f"QEMU exited unexpectedly while waiting for {description}. "
                    f"Recent output: {self._output_tail()}"
                )
            events = self._selector.select(min(remaining, 0.1))
            for key, _ in events:
                try:
                    chunk = os.read(key.fd, 65536)
                except OSError as exc:
                    raise Xv6BridgeError(
                        f"Could not read xv6 output: {exc}"
                    ) from exc
                if not chunk:
                    raise Xv6BridgeError(
                        f"QEMU closed its output while waiting for {description}. "
                        f"Recent output: {self._output_tail()}"
                    )
                self._buffer.extend(chunk)

    def _output_tail(self):
        tail = bytes(self._buffer[-400:]).decode("utf-8", errors="replace").strip()
        return tail if tail else "(none)"

    def close(self):
        process = self._process
        if process is None:
            return

        if process.poll() is None:
            try:
                process.stdin.write(b"\x01x")
                process.stdin.flush()
                process.stdin.close()
            except (BrokenPipeError, OSError):
                self._stop_process_group(process, signal.SIGTERM)
            try:
                process.wait(timeout=SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self._stop_process_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._stop_process_group(process, signal.SIGKILL)
                    process.wait()

        if self._selector is not None:
            self._selector.close()
            self._selector = None
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        if process.stdout:
            process.stdout.close()
        self._process = None

    @staticmethod
    def _stop_process_group(process, sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
