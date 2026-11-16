"""Three-mesh sensitivity study with explicit acceptance and raw stress reporting."""

import csv
import json
from pathlib import Path
import numpy as np
from .model import Config
from .pipeline import run


def converge(config, output, sizes):
    sizes = list(sizes)
    if any(not np.isfinite(x) or x <= 0 for x in sizes) or not sizes[0] > sizes[1] > sizes[2]:
        raise ValueError("Provide three positive, strictly decreasing mesh sizes")
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Convergence output must be a new directory")
    output.mkdir(parents=True, exist_ok=True)
    baseline = Config.load(config).variants[0].name
    rows, studies = [], []
    for size in sizes:
        study = run(config, output/f"mesh-{size:g}", [baseline], size)
        studies.append(study)
        if study["errors"] or len(study["results"]) != 1:
            raise RuntimeError("Convergence run failed; inspect per-mesh summaries")
        r = study["results"][0]
        rows.append({k: r[k] for k in ("nodes", "elements", "peak_temperature_c", "peak_stress_mpa",
                                      "hot_swept_stress_mpa", "max_displacement_mm")})
        rows[-1]["mesh_mm"] = size
    def change(key):
        return abs(rows[-1][key]-rows[-2][key])/abs(rows[-1][key])
    # Temperature change uses temperature rise, avoiding a Celsius-dependent denominator.
    ambient = Config.load(config).scenario.ambient_c
    temperature_change = abs(rows[-1]["peak_temperature_c"]-rows[-2]["peak_temperature_c"])/abs(
        rows[-1]["peak_temperature_c"]-ambient)
    report = {"rows": rows, "swept_stress_change_fraction": change("hot_swept_stress_mpa"),
              "temperature_rise_change_fraction": temperature_change,
              "displacement_change_fraction": change("max_displacement_mm"),
              "raw_peak_stress_change_fraction": change("peak_stress_mpa"),
              "criteria": {"swept_stress": 0.05, "temperature_rise": 0.02, "displacement": 0.05},
              "note": "Compare the two finest meshes. Swept-region stress excludes the idealized mount. Raw global peak remains reported and controls each design safety check."}
    report["passed"] = (report["swept_stress_change_fraction"] < 0.05 and
                        temperature_change < 0.02 and report["displacement_change_fraction"] < 0.05
                        and all(s["passed"] for s in studies))
    (output / "convergence.json").write_text(json.dumps(report, indent=2)+"\n")
    with (output / "convergence.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for ax, key, label in zip(axes, ["hot_swept_stress_mpa", "peak_temperature_c", "max_displacement_mm"],
                              ["Swept-region stress / MPa", "Peak temperature / °C", "Max displacement / mm"]):
        ax.plot([r["elements"] for r in rows], [r[key] for r in rows], "o-", color="#176b8f")
        ax.set(xlabel="Quadratic tetrahedra", ylabel=label)
        ax.grid(alpha=0.2)
    fig.suptitle("Baseline mesh sensitivity")
    fig.savefig(output / "convergence.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))
    return report
