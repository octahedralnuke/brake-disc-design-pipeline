import json
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = ["## Brake disc study", ""]
if path.exists():
    study = json.loads(path.read_text())
    lines += ["| Variant | Mass / kg | Peak / °C | Stress / MPa | SF | Result |",
              "|---|---:|---:|---:|---:|---|"]
    for r in study["results"]:
        lines.append(f'| {r["name"]} | {r["mass_kg"]:.3f} | {r["peak_temperature_c"]:.1f} | '
                     f'{r["peak_stress_mpa"]:.1f} | {r["safety_factor"]:.2f} | {"PASS" if r["passed"] else "FAIL"} |')
    for e in study["errors"]:
        lines.append(f'- {e["name"]}: {e["error"]}')
else:
    lines.append("Study did not produce a summary; inspect the failed step logs.")
text = "\n".join(lines)+"\n"
if "GITHUB_STEP_SUMMARY" in os.environ:
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
        stream.write(text)
else:
    print(text)
