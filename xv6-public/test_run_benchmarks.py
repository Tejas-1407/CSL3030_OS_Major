import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_benchmarks


class BenchmarkHarnessTests(unittest.TestCase):
    def test_parser_defaults_and_choices(self):
        args = run_benchmarks.build_parser().parse_args([])
        self.assertEqual(args.cpus, 1)
        self.assertEqual(args.repetitions, 20)
        self.assertEqual(args.policies, list(run_benchmarks.POLICIES))
        with self.assertRaises(SystemExit):
            run_benchmarks.build_parser().parse_args(["--cpus", "2"])

    def test_help_exits_before_experiment_creation(self):
        with patch.object(run_benchmarks, "create_experiment_dir") as create_dir:
            with self.assertRaises(SystemExit) as raised:
                run_benchmarks.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        create_dir.assert_not_called()

    def test_records_cpu_and_repetition_for_each_result(self):
        def fake_run(policy, workload, stages, cpus):
            results = [
                {
                    "wid": workflow_id,
                    "stages": stages,
                    "elapsed_ticks": workflow_id,
                    "deadline_ticks": workflow_id * 100,
                    "deadline_miss": 0,
                }
                for workflow_id in (1, 2, 3)
            ]
            return b"raw QEMU output", results, (3, 3, 0), []

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                run_benchmarks, "RESULTS_DIR", Path(temp_dir)
            ), patch.object(run_benchmarks, "run_policy", side_effect=fake_run):
                result = run_benchmarks.main(
                    ["--cpus", "3", "--repetitions", "2", "--policies", "RR"]
                )

            self.assertEqual(result, 0)
            experiments = list(Path(temp_dir).iterdir())
            self.assertEqual(len(experiments), 1)
            experiment = experiments[0]
            with (experiment / "benchmark_results.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 18)
            self.assertEqual({row["cpu_count"] for row in rows}, {"3"})
            self.assertEqual({row["repetition"] for row in rows}, {"1", "2"})
            self.assertEqual(
                {row["workload"] for row in rows}, {"Low", "Medium", "High"}
            )
            self.assertTrue(
                all(path.read_bytes() == b"raw QEMU output"
                    for path in experiment.glob("*_console.log"))
            )
            summary = (experiment / "comparison_summary.txt").read_text()
            self.assertIn("CPUS=3; repetitions=2", summary)
            self.assertIn("RR", summary)


if __name__ == "__main__":
    unittest.main(verbosity=2)
