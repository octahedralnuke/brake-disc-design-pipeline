"""Show that a deliberately impossible criterion is rejected, without changing results."""
import subprocess
import sys

result = subprocess.run([sys.executable, "-m", "brakedisc", "check", sys.argv[1],
                         "--min-safety-factor", "1000000"])
if result.returncode != 2:
    raise SystemExit(f"Expected design rejection (2), received {result.returncode}")
print("Expected rejection confirmed: the acceptance gate is active.")
