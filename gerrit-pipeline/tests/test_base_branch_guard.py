import importlib.util
import contextlib
import io
import unittest
from pathlib import Path


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class BaseBranchGuardTest(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "base_branch_guard.py"
        spec = importlib.util.spec_from_file_location("base_branch_guard_under_test", path)
        self.guard = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(self.guard)
        self.calls = []

    def _patch_git(self, responses):
        def fake_run_git(args, check=True):
            self.calls.append((args, check))
            key = tuple(args)
            response = responses.get(key, FakeProc())
            if check and response.returncode != 0:
                raise RuntimeError(response.stderr or response.stdout or "git command failed")
            return response

        self.guard.run_git = fake_run_git

    def test_guard_fetches_target_and_accepts_current_head(self):
        self._patch_git({
            ("fetch", "--quiet", "autolink", "al_dev"): FakeProc(),
            ("merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD"): FakeProc(returncode=0),
        })

        with contextlib.redirect_stdout(io.StringIO()):
            rc = self.guard.guard_head("autolink", "al_dev")

        self.assertEqual(rc, 0)
        self.assertIn((["fetch", "--quiet", "autolink", "al_dev"], True), self.calls)

    def test_guard_blocks_when_head_is_not_based_on_target(self):
        self._patch_git({
            ("fetch", "--quiet", "autolink", "al_dev"): FakeProc(),
            ("merge-base", "--is-ancestor", "FETCH_HEAD", "HEAD"): FakeProc(returncode=1),
            ("rev-parse", "--short", "FETCH_HEAD"): FakeProc(stdout="aaaa111\n"),
            ("rev-parse", "--short", "HEAD"): FakeProc(stdout="bbbb222\n"),
        })

        with self.assertRaises(RuntimeError) as ctx:
            self.guard.guard_head("autolink", "al_dev")

        self.assertIn("未基于最新 autolink/al_dev", str(ctx.exception))

    def test_no_fetch_uses_local_remote_tracking_ref(self):
        self._patch_git({
            ("merge-base", "--is-ancestor", "autolink/al_dev", "HEAD"): FakeProc(returncode=0),
        })

        with contextlib.redirect_stdout(io.StringIO()):
            rc = self.guard.guard_head("autolink", "al_dev", fetch=False)

        self.assertEqual(rc, 0)
        self.assertNotIn((["fetch", "--quiet", "autolink", "al_dev"], True), self.calls)

    def test_rejects_invalid_branch_name(self):
        with self.assertRaises(RuntimeError):
            self.guard.guard_head("autolink", "../al_dev")


if __name__ == "__main__":
    unittest.main()
