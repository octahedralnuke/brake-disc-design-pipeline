"""End-to-end study orchestration and fail-closed acceptance criteria."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import numpy as np
from .geometry import build
from .mesh import generate
from .model import Config, requirements
from .solver import find_ccx, structural, thermal


def evaluate(result, limits):
    tests = {
        "safety_factor": result["safety_factor"] >= limits["min_safety_factor"],
        "temperature": result["peak_temperature_c"] <= limits["max_temperature_c"],
        "cad_mesh_volume": result["volume_error_fraction"] <= limits["max_volume_error_fraction"],
        "thermal_energy_balance": result["energy_error_fraction"] <= limits["max_energy_error_fraction"],
        "reaction_torque": result["reaction_torque_error_fraction"] <= limits["max_reaction_torque_error_fraction"],
        "solver_completed": result["solver_completed"] is True,
    }
    return {key: bool(value) for key, value in tests.items()}


def output_directory(output, overwrite):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        if not overwrite or not (output / ".brakedisc-run").is_file():
            raise ValueError(f"Output is not empty: {output}. Choose a new directory, or use --overwrite on a previous pipeline run.")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / ".brakedisc-run").write_text("Generated run directory\n")
    return output


def run(config_path, output, names=None, mesh_mm=None, overwrite=False):
    c = Config.load(Path(config_path))
    designs = [d for d in c.variants if names is None or d.name in names]
    if not designs or (names is not None and set(names)-{d.name for d in designs}):
        raise ValueError("Unknown or empty variant selection")
    size = c.mesh_mm if mesh_mm is None else mesh_mm
    if not np.isfinite(size) or size <= 0:
        raise ValueError("Mesh size must be finite and positive")
    find_ccx()
    out = output_directory(output, overwrite)
    (out / "input.json").write_text(json.dumps(asdict(c), indent=2)+"\n")
    study = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
             "config_sha256": hashlib.sha256(Path(config_path).read_bytes()).hexdigest(),
             "mesh_mm": size, "limits": asdict(c.limits), "scenario": asdict(c.scenario),
             "material": asdict(c.material), "results": [], "errors": [], "passed": False}
    study["software"] = {p: importlib.metadata.version(p) for p in
                         ("cadquery", "gmsh", "numpy", "matplotlib", "meshio")}
    study["software"]["python"] = platform.python_version()
    study["source_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(Path(__file__).parent.glob("*.py"))}
    study["software"]["calculix"] = subprocess.run([find_ccx(), "-v"], capture_output=True,
                                                    text=True).stdout.strip()
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    study["git_commit"] = git.stdout.strip() if git.returncode == 0 else None
    from .report import fields, study_report
    for d in designs:
        folder = out / d.name
        folder.mkdir()
        print(f"[{d.name}] CAD → mesh → cold FEA → transient thermal FEA → hot FEA", flush=True)
        try:
            cad_volume = build(d, folder)
            mesh = generate(folder / "disc.step", d, size, folder)
            req = requirements(c.scenario, d, c.material)
            cold = structural(folder, mesh, c, req)
            temp, history, energy_error, peak_time = thermal(folder, mesh, c, req)
            hot = structural(folder, mesh, c, req, temp, "hot")
            peak_stress = max(cold["peak_stress_pa"], hot["peak_stress_pa"])
            result = {"name": d.name, "design": asdict(d), "requirements": req,
                      "mass_kg": cad_volume*c.material.density_kg_m3,
                      "nodes": len(mesh.points), "elements": len(mesh.tets),
                      "minimum_sampled_jacobian_m3": mesh.min_jacobian,
                      "volume_error_fraction": abs(mesh.volume/cad_volume-1),
                      "peak_temperature_c": float(history[:, 1].max()),
                      "peak_temperature_time_s": peak_time,
                      "energy_error_fraction": energy_error,
                      "cold_stress_mpa": cold["peak_stress_pa"]/1e6,
                      "hot_stress_mpa": hot["peak_stress_pa"]/1e6,
                      "hot_swept_stress_mpa": float(hot["cell_stress"][
                          np.linalg.norm(mesh.points[mesh.tets[:, :4]].mean(axis=1)[:, :2], axis=1)
                          >= d.sweep_inner_radius_mm*1e-3].max())/1e6,
                      "peak_stress_mpa": peak_stress/1e6,
                      "safety_factor": c.material.yield_pa/peak_stress,
                      "max_displacement_mm": max(cold["max_displacement_m"], hot["max_displacement_m"])*1e3,
                      "reaction_torque_error_fraction": max(cold["reaction_torque_error_fraction"], hot["reaction_torque_error_fraction"]),
                      "cold_reaction_torque_nm": cold["reaction_torque_nm"],
                      "hot_reaction_torque_nm": hot["reaction_torque_nm"],
                      "solver_completed": True}
            result["checks"] = evaluate(result, study["limits"])
            result["passed"] = all(result["checks"].values())
            fields(folder, mesh, temp, hot["cell_stress"], history, d.name)
            (folder / "result.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
            study["results"].append(result)
            print(f"[{d.name}] {result['mass_kg']:.3f} kg | {result['peak_temperature_c']:.1f} °C | "
                  f"{result['peak_stress_mpa']:.1f} MPa | SF {result['safety_factor']:.2f} | "
                  f"{'PASS' if result['passed'] else 'FAIL'}", flush=True)
        except Exception as exc:
            study["errors"].append({"name": d.name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{d.name}] ERROR: {exc}", flush=True)
    study["passed"] = not study["errors"] and len(study["results"]) == len(designs) and all(
        r["passed"] for r in study["results"])
    (out / "summary.json").write_text(json.dumps(study, indent=2, allow_nan=False)+"\n")
    study_report(out, study)
    manifest = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.rglob("*")) if p.is_file() and p.name != "manifest.sha256.json"}
    (out / "manifest.sha256.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return study
