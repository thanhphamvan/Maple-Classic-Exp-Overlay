"""Runs every test script (tests/test_*.py), each on its own, and sums them up. Exits with 1
if any of them failed.

Run from the project folder:  py -3 tests/run_all.py            (-v: show every PASS line too)
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    verbose = "-v" in sys.argv[1:]
    results = []
    for script in sorted(HERE.glob("test_*.py")):
        t0 = time.perf_counter()
        run = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        seconds = time.perf_counter() - t0
        lines = run.stdout.splitlines()
        passed = sum(line.startswith("PASS") for line in lines)
        failed = [line for line in lines if line.startswith("FAIL")]
        ok = run.returncode == 0
        results.append(ok)
        print(f"{'ok  ' if ok else 'FAIL'} {script.name:22} {passed:4} passed, {len(failed)} failed  ({seconds:.1f} s)")
        for line in (lines if verbose else failed):
            print(f"       {line}")
        if not ok and not failed:                  # it stopped with an error: show it
            print("       " + "\n       ".join((run.stderr or run.stdout).strip().splitlines()[-15:]))
    print("\nALL PASSED" if all(results) else f"\n{results.count(False)} of {len(results)} test scripts FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
