import unittest

from agent import Agent, ToolRequestError


class FakeXv6Tools:
    def __init__(self):
        self.calls = []

    def list_files(self):
        self.calls.append(("list_files",))
        return "README\nsched_bench"

    def read_file(self, path):
        self.calls.append(("read_file", path))
        return f"contents of {path}"


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tools = FakeXv6Tools()
        self.agent = Agent(self.tools)

    def test_list_files_request(self):
        result = self.agent.dispatch(
            {"tool": "list_files", "arguments": {}}
        )
        self.assertEqual(result, "README\nsched_bench")
        self.assertEqual(self.tools.calls, [("list_files",)])

    def test_read_file_request(self):
        result = self.agent.dispatch(
            {"tool": "read_file", "arguments": {"path": "README"}}
        )
        self.assertEqual(result, "contents of README")
        self.assertEqual(self.tools.calls, [("read_file", "README")])

    def test_summarize_is_deterministic_and_does_not_call_xv6(self):
        result = self.agent.dispatch(
            {
                "tool": "summarize",
                "arguments": {
                    "text": "First sentence. Second sentence. Third sentence."
                },
            }
        )
        self.assertEqual(result, "First sentence. Second sentence...")
        self.assertEqual(self.tools.calls, [])

    def test_summarize_empty_text(self):
        self.assertEqual(
            self.agent.dispatch(
                {"tool": "summarize", "arguments": {"text": "  \n"}}
            ),
            "No text supplied to summarize.",
        )

    def test_rejects_malformed_requests(self):
        requests = (
            None,
            [],
            {},
            {"tool": "list_files"},
            {"tool": "list_files", "arguments": {}, "extra": True},
            {"tool": 3, "arguments": {}},
            {"tool": "list_files", "arguments": []},
        )
        for request in requests:
            with self.subTest(request=request):
                with self.assertRaises(ToolRequestError):
                    self.agent.dispatch(request)
        self.assertEqual(self.tools.calls, [])

    def test_rejects_unknown_tool(self):
        with self.assertRaisesRegex(ToolRequestError, "Unknown tool"):
            self.agent.dispatch({"tool": "shell", "arguments": {}})
        self.assertEqual(self.tools.calls, [])

    def test_validates_required_arguments_and_types(self):
        requests = (
            {"tool": "list_files", "arguments": {"path": "README"}},
            {"tool": "read_file", "arguments": {}},
            {"tool": "read_file", "arguments": {"path": 10}},
            {"tool": "summarize", "arguments": {}},
            {"tool": "summarize", "arguments": {"text": None}},
            {
                "tool": "summarize",
                "arguments": {"text": "text", "path": "README"},
            },
        )
        for request in requests:
            with self.subTest(request=request):
                with self.assertRaises(ToolRequestError):
                    self.agent.dispatch(request)
        self.assertEqual(self.tools.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
