"""The PASS / FAIL lines the test scripts print, with a section heading for each group.

    checks = Checks()
    checks.section("reading the EXP bar")
    checks.check("reads it at 7 px", got == expected)
    checks.done()          # prints ALL PASSED (or how many failed) and exits with 0 or 1
"""
import sys
import traceback


class Checks:
    def __init__(self):
        self.failures = self.passed = 0

    def section(self, title):
        print(f"\n---- {title}")

    def check(self, name, ok):
        print(("PASS " if ok else "FAIL ") + name)
        self.passed += bool(ok)
        self.failures += not ok
        return bool(ok)

    def runs(self, name, fn):
        """A check that fn() runs without raising; returns what it returned (or None)."""
        try:
            result = fn()
        except Exception:
            self.check(f"{name} (raised: {traceback.format_exc().strip().splitlines()[-1]})", False)
            return None
        self.check(name, True)
        return result

    def done(self):
        print("\nALL PASSED" if not self.failures else f"\n{self.failures} FAILED")
        sys.exit(1 if self.failures else 0)
