import os
import signal
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import llm_agent
import run_agent
from llm_agent import LLMAgentError
from xv6_bridge import Xv6Bridge, Xv6BridgeError, find_qemu_using_images


PROJECT_ROOT = Path(__file__).resolve().parents[1]
XV6_DIR = Path(__file__).resolve().parent
LAUNCHER = XV6_DIR / "start-agent.sh"


class FakeStream:
    def __init__(self):
        self.data = bytearray()
        self.closed = False

    def write(self, data):
        self.data.extend(data)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class FakeProcess:
    def __init__(self):
        self.pid = 9876
        self.stdin = FakeStream()
        self.stdout = FakeStream()
        self.returncode = None
        self.wait_calls = []

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        self.returncode = 0
        return self.returncode


class StubbornProcess(FakeProcess):
    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if len(self.wait_calls) < 3:
            raise subprocess.TimeoutExpired("qemu", timeout)
        self.returncode = -9
        return self.returncode


class StartupTests(unittest.TestCase):
    def test_missing_api_key_is_reported_without_revealing_value(self):
        with patch.object(llm_agent, "load_project_environment"):
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(LLMAgentError, "NVIDIA_API_KEY"):
                    llm_agent.create_nvidia_client()

    def test_valid_api_configuration(self):
        fake_openai = SimpleNamespace(OpenAI=Mock(return_value="client"))
        with patch.object(llm_agent, "load_project_environment"):
            with patch.dict(os.environ, {"NVIDIA_API_KEY": "test-only-value"}, clear=True):
                with patch.dict("sys.modules", {"openai": fake_openai}):
                    self.assertEqual(llm_agent.create_nvidia_client(), "client")
        fake_openai.OpenAI.assert_called_once_with(
            api_key="test-only-value",
            base_url="https://integrate.api.nvidia.com/v1",
            timeout=30.0,
        )

    def test_exported_environment_variable_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text("NVIDIA_API_KEY=file-value\n", encoding="utf-8")
            with patch.dict(
                os.environ, {"NVIDIA_API_KEY": "exported-value"}, clear=True
            ):
                llm_agent.load_project_environment(env_file)
                self.assertEqual(os.environ["NVIDIA_API_KEY"], "exported-value")

    def test_exported_key_remains_valid_when_project_env_file_is_missing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_env = Path(temporary_directory) / ".env"
            with patch.dict(
                os.environ, {"NVIDIA_API_KEY": "exported-value"}, clear=True
            ):
                llm_agent.load_project_environment(missing_env)
                self.assertEqual(os.environ["NVIDIA_API_KEY"], "exported-value")

    def test_launcher_resolves_project_root_from_its_own_path(self):
        environment = os.environ.copy()
        environment.pop("NVIDIA_API_KEY", None)
        with tempfile.TemporaryDirectory() as elsewhere:
            result = subprocess.run(
                [str(LAUNCHER)],
                cwd=elsewhere,
                env=environment,
                text=True,
                capture_output=True,
                timeout=15,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(PROJECT_ROOT / ".env"), result.stderr)
        self.assertIn("placeholder", result.stderr)
        self.assertNotIn("YOUR_KEY_HERE", result.stderr)
        self.assertNotIn("qemu", result.stdout.lower() + result.stderr.lower())

    def test_project_env_file_is_private_and_ignored(self):
        env_file = PROJECT_ROOT / ".env"
        self.assertTrue(env_file.is_file())
        self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "check-ignore", "-q", str(env_file)],
            check=False,
        )
        self.assertEqual(result.returncode, 0)


class QemuDetectionTests(unittest.TestCase):
    def test_detects_qemu_using_the_project_image(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "xv6-EDF_DONATION.img"
            image.touch()
            proc_root = root / "proc"
            process_dir = proc_root / "4321"
            process_dir.mkdir(parents=True)
            (process_dir / "cwd").symlink_to(root, target_is_directory=True)
            (process_dir / "cmdline").write_bytes(
                b"/usr/bin/qemu-system-i386\0-drive\0file=xv6-EDF_DONATION.img,index=0\0"
            )

            self.assertEqual(
                find_qemu_using_images([image], proc_root),
                [(4321, str(image.resolve()))],
            )

    def test_ignores_unrelated_processes_and_does_not_signal_them(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "xv6-EDF_DONATION.img"
            image.touch()
            proc_root = root / "proc"
            process_dir = proc_root / "4322"
            process_dir.mkdir(parents=True)
            (process_dir / "cwd").symlink_to(root, target_is_directory=True)
            (process_dir / "cmdline").write_bytes(
                b"/usr/bin/python\0-drive\0file=xv6-EDF_DONATION.img\0"
            )

            with patch("xv6_bridge.os.killpg") as kill_group:
                self.assertEqual(find_qemu_using_images([image], proc_root), [])
            kill_group.assert_not_called()

    def test_start_reports_existing_qemu_without_starting_or_killing_it(self):
        bridge = Xv6Bridge()
        with patch("xv6_bridge.QEMU", Path(__file__)):
            with patch(
                "xv6_bridge.find_qemu_using_images",
                return_value=[(4323, "fs.img"), (4323, "xv6.img")],
            ):
                with patch("xv6_bridge.subprocess.Popen") as popen:
                    with patch("xv6_bridge.os.killpg") as kill_group:
                        with self.assertRaisesRegex(Xv6BridgeError, "PID 4323"):
                            bridge.start()
        popen.assert_not_called()
        kill_group.assert_not_called()

    def test_context_manager_does_not_start_qemu_until_tool_command(self):
        bridge = Xv6Bridge()
        with patch.object(bridge, "start") as start:
            with bridge:
                pass
        start.assert_not_called()

    def test_qemu_cleanup_on_normal_exit_and_exception(self):
        for error in (None, RuntimeError("test exception")):
            with self.subTest(error=error):
                bridge = Xv6Bridge()
                process = FakeProcess()
                bridge._process = process
                with patch("xv6_bridge.os.killpg") as kill_group:
                    if error is None:
                        with bridge:
                            pass
                    else:
                        with self.assertRaisesRegex(RuntimeError, "test exception"):
                            with bridge:
                                raise error
                self.assertEqual(process.stdin.data, b"\x01x")
                self.assertEqual(process.returncode, 0)
                self.assertIsNone(bridge._process)
                kill_group.assert_not_called()

    def test_stuck_qemu_cleanup_signals_only_its_process_group(self):
        bridge = Xv6Bridge()
        process = StubbornProcess()
        bridge._process = process
        with patch("xv6_bridge.os.killpg") as kill_group:
            bridge.close()
        self.assertEqual(
            kill_group.call_args_list,
            [
                call(process.pid, signal.SIGTERM),
                call(process.pid, signal.SIGKILL),
            ],
        )
        self.assertIsNone(bridge._process)


class InteractiveLifecycleTests(unittest.TestCase):
    def test_general_conversation_does_not_start_qemu_and_exit_closes_bridge(self):
        bridge = Mock()
        fake_agent = Mock()
        fake_agent.run.return_value = "Hello."
        with patch.object(run_agent, "Xv6Bridge", return_value=bridge):
            with patch.object(run_agent, "create_nvidia_client", return_value=object()):
                with patch.object(run_agent, "create_agent", return_value=object()):
                    with patch.object(run_agent, "LLMAgent", return_value=fake_agent):
                        with patch("builtins.input", side_effect=["Hello", "exit"]):
                            self.assertEqual(run_agent.main(), 0)
        bridge.start.assert_not_called()
        bridge.close.assert_called_once()

    def test_api_error_closes_qemu_and_session_can_exit(self):
        bridge = Mock()
        fake_agent = Mock()
        fake_agent.run.side_effect = [LLMAgentError("API request failed")]
        with patch.object(run_agent, "Xv6Bridge", return_value=bridge):
            with patch.object(run_agent, "create_nvidia_client", return_value=object()):
                with patch.object(run_agent, "create_agent", return_value=object()):
                    with patch.object(run_agent, "LLMAgent", return_value=fake_agent):
                        with patch("builtins.input", side_effect=["Question", "exit"]):
                            self.assertEqual(run_agent.main(), 0)
        self.assertEqual(bridge.close.call_count, 2)

    def test_unexpected_exception_closes_bridge(self):
        bridge = Mock()
        fake_agent = Mock()
        fake_agent.run.side_effect = RuntimeError("unexpected failure")
        with patch.object(run_agent, "Xv6Bridge", return_value=bridge):
            with patch.object(run_agent, "create_nvidia_client", return_value=object()):
                with patch.object(run_agent, "create_agent", return_value=object()):
                    with patch.object(run_agent, "LLMAgent", return_value=fake_agent):
                        with patch("builtins.input", return_value="Question"):
                            with self.assertRaisesRegex(
                                RuntimeError, "unexpected failure"
                            ):
                                run_agent.main()
        bridge.close.assert_called_once()

    def test_ctrl_c_closes_bridge(self):
        bridge = Mock()
        with patch.object(run_agent, "Xv6Bridge", return_value=bridge):
            with patch.object(run_agent, "create_nvidia_client", return_value=object()):
                with patch("builtins.input", side_effect=KeyboardInterrupt):
                    self.assertEqual(run_agent.main(), 0)
        bridge.close.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
