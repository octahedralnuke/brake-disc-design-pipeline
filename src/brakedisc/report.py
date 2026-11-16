"""Headless publication of plots, CSV and an offline HTML report."""

import csv
import html
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": "white", "axes.titleweight": "bold"})


def fields(folder, mesh, temperature, cell_stress, history, name):
    # Draw the actual top surface, preserving all holes; no interpolation across voids.
    tri = mesh.surface
    is_top = np.ptp(mesh.points[tri[:, :3], 2], axis=1) < 1e-9
    is_top &= np.mean(mesh.points[tri[:, :3], 2], axis=1) > mesh.points[:, 2].max()-1e-8
    selected = np.flatnonzero(is_top)
    polygons = mesh.points[tri[selected, :3], :2]*1e3
    cell_index = np.array([mesh.exterior[i][0]-1 for i in selected])
    values = [np.mean(temperature[tri[selected]], axis=1), cell_stress[cell_index]/1e6]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5), constrained_layout=True)
    for ax, v, title, unit, cmap in zip(axes, values,
        ["Temperature at thermal peak", "Hot structural envelope"], ["°C", "von Mises / MPa"], ["inferno", "viridis"]):
        collection = PolyCollection(polygons, array=v, cmap=cmap, edgecolor="none", rasterized=True)
        ax.add_collection(collection)
        ax.autoscale_view()
        ax.set_aspect("equal")
        ax.set(xlabel="x / mm", ylabel="y / mm", title=title)
        fig.colorbar(collection, ax=ax, shrink=0.7, label=unit)
    fig.suptitle(f"{name.title()} · finite element results", fontsize=15, fontweight="bold")
    fig.savefig(folder / "fields.png", dpi=170)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.2), constrained_layout=True)
    ax.plot(history[:, 0], history[:, 1], color="#e56735", lw=2, label="Peak nodal temperature")
    ax.plot(history[:, 0], history[:, 2], color="#176b8f", lw=2, label="Volume mean temperature")
    ax.set(xlabel="Time / s", ylabel="Temperature / °C", title=f"{name.title()} · braking and cooling")
    ax.legend(frameon=False)
    ax.grid(alpha=0.15)
    fig.savefig(folder / "thermal_history.png", dpi=170)
    plt.close(fig)


def study_report(out: Path, study):
    results = study["results"]
    keys = ["name", "mass_kg", "peak_temperature_c", "peak_stress_mpa", "safety_factor",
            "max_displacement_mm", "nodes", "elements", "energy_error_fraction", "passed"]
    with (out / "tradeoff.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    if results:
        fig, ax = plt.subplots(figsize=(9, 5.2), constrained_layout=True)
        masses = [r["mass_kg"] for r in results]
        temps = [r["peak_temperature_c"] for r in results]
        stresses = [r["peak_stress_mpa"] for r in results]
        dots = ax.scatter(masses, temps, c=stresses, cmap="plasma", s=180, edgecolors="#233748", zorder=3)
        for r in results:
            ax.annotate(r["name"], (r["mass_kg"], r["peak_temperature_c"]), xytext=(8, 9), textcoords="offset points")
        ax.margins(0.2)
        ax.set(xlabel="Disc mass / kg", ylabel="Peak temperature / °C",
               title="Brake disc design trade-off",)
        ax.grid(alpha=0.15)
        fig.colorbar(dots, ax=ax, label="Peak envelope von Mises stress / MPa")
        fig.savefig(out / "tradeoff.png", dpi=180)
        fig.savefig(out / "tradeoff.svg")
        plt.close(fig)
    status = "PASS" if study["passed"] else "FAIL"
    rows = []
    cards = []
    for r in results:
        name = html.escape(r["name"])
        rows.append(f'<tr><td>{name}</td><td>{r["mass_kg"]:.3f}</td><td>{r["peak_temperature_c"]:.1f}</td>'
                    f'<td>{r["peak_stress_mpa"]:.1f}</td><td>{r["safety_factor"]:.2f}</td>'
                    f'<td>{"PASS" if r["passed"] else "FAIL"}</td></tr>')
        checks = ", ".join(f'{html.escape(k)}: {"PASS" if v else "FAIL"}' for k, v in r["checks"].items())
        cards.append(f'<section><h2>{name.title()}</h2><p>{checks}</p>'
                     f'<img src="{name}/fields.png" alt="Temperature and stress fields">'
                     f'<img src="{name}/thermal_history.png" alt="Transient temperature history">'
                     f'<p><a href="{name}/disc.step">STEP model</a> · <a href="{name}/drawing.svg">Drawing</a> · '
                     f'<a href="{name}/hot.vtu">ParaView result</a> · <a href="{name}/result.json">Numeric results</a></p></section>')
    errors = "".join(f'<li>{html.escape(e["name"])}: {html.escape(e["error"])}</li>' for e in study["errors"])
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brake disc design study</title><style>
body{{font:16px/1.6 system-ui,sans-serif;color:#153047;background:#edf2f5;margin:0}}
main{{max-width:1120px;margin:auto;padding:40px 24px}}h1{{font-size:38px;line-height:1.15}}h2{{margin-top:0}}
section,header{{background:white;border-radius:12px;padding:28px;margin-bottom:24px}}img{{width:100%;height:auto}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #dde5ea}}
a{{color:#086b99}}.tag{{display:inline-block;background:{"#d5f3e0" if study["passed"] else "#ffded6"};padding:5px 15px;border-radius:5px;font-weight:bold}}
.small{{font-size:13px;color:#526778}}.scroll{{overflow-x:auto}}</style><main>
<header><p class="small">PYTHON / CADQUERY / GMSH / CALCULIX</p><h1>Brake disc design study</h1>
<span class="tag">{status}</span><p>Reproducible sizing, parametric geometry and finite element screening for a single kart stop.</p>
<p class="small">Generated {html.escape(study["created_utc"])} · Mesh target {study["mesh_mm"]:g} mm</p></header>
<section><h2>Design comparison</h2><div class="scroll"><table><thead><tr><th>Variant</th><th>Mass / kg</th><th>Peak / °C</th><th>Stress / MPa</th><th>Safety factor</th><th>Checks</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>
{"<img src='tradeoff.png' alt='Mass temperature stress trade-off'>" if results else ""}
<p><a href="tradeoff.csv">CSV</a> · <a href="summary.json">Full summary</a> · <a href="input.json">Resolved inputs</a> · <a href="manifest.sha256.json">Artifact hashes</a></p><ul>{errors}</ul></section>
{"".join(cards)}<section><h2>Interpretation</h2><p>Temperatures use a transient conduction model with prescribed, circumferentially averaged braking heat and assumed convection. Structural results envelope cold torque loading and the hottest thermal snapshot with full torque. Mounting-hole surfaces are idealized as rigidly fixed. Stress values are maxima at integration points, including the constrained mount region.</p>
<p>Generic constant steel properties and a single stop support comparative educational screening. Fatigue, wear, pad contact, local moving hot spots, fluid flow, bolt flexibility and manufacturing qualification are outside the model. A passing calculation means the specified numerical criteria were met.</p></section></main></html>'''
    (out / "report.html").write_text(page)
