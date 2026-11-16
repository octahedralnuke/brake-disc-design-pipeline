"""CalculiX input generation, execution, checked DAT parsing and field export."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import numpy as np
from .mesh import Mesh
from .model import Config


def find_ccx():
    executable = os.environ.get("CCX", "ccx")
    resolved = shutil.which(executable)
    if not resolved:
        raise RuntimeError("CalculiX not found. Install calculix-ccx, or set CCX to its executable.")
    return str(Path(resolved).resolve())


def run_ccx(folder, job, timeout=600):
    # Never accept stale output from a previous run.
    for suffix in ("dat", "frd", "sta", "cvg"):
        (folder / f"{job}.{suffix}").unlink(missing_ok=True)
    env = dict(os.environ, OMP_NUM_THREADS="1", CCX_NPROC_RESULTS="1", LC_ALL="C")
    try:
        result = subprocess.run([find_ccx(), "-i", job], cwd=folder, env=env,
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        (folder / f"{job}.log").write_text(str(exc))
        raise RuntimeError(f"CalculiX timed out: {job}") from exc
    log = result.stdout + result.stderr
    (folder / f"{job}.log").write_text(log)
    if result.returncode != 0 or "Job finished" not in log or "*ERROR" in log.upper():
        raise RuntimeError(f"CalculiX failed: {job}. See {folder / (job+'.log')}")
    if not (folder / f"{job}.dat").exists():
        raise RuntimeError(f"CalculiX produced no DAT results: {job}")


def mesh_deck(mesh: Mesh, thermal=False):
    lines = ["*NODE,NSET=ALLN"]
    lines += [f"{i}, {x:.12g}, {y:.12g}, {z:.12g}"
              for i, (x, y, z) in enumerate(mesh.points, 1)]
    lines += [f"*ELEMENT,TYPE={'DC3D10' if thermal else 'C3D10'},ELSET=DISC"]
    lines += [f"{i}, " + ", ".join(str(n+1) for n in tet)
              for i, tet in enumerate(mesh.tets, 1)]
    lines += ["*NSET,NSET=MOUNT"]
    lines += [", ".join(str(n+1) for n in mesh.mount[i:i+12])
              for i in range(0, len(mesh.mount), 12)]
    lines += ["*SOLID SECTION,ELSET=DISC,MATERIAL=STEEL"]
    return lines


def material_deck(c: Config):
    m = c.material
    return ["*MATERIAL,NAME=STEEL", "*ELASTIC", f"{m.youngs_pa:.12g}, {m.poisson}",
            "*DENSITY", str(m.density_kg_m3), "*CONDUCTIVITY", str(m.conductivity_w_mk),
            "*SPECIFIC HEAT", str(m.specific_heat_j_kgk),
            f"*EXPANSION,ZERO={c.scenario.ambient_c}", str(m.expansion_per_k)]


def thermal(folder: Path, mesh: Mesh, c: Config, req):
    s = c.scenario
    stop = req["stop_time_s"]
    end = stop + s.cooling_s
    flux = req["initial_disc_power_w"] / mesh.friction_weights.sum()
    lines = ["*HEADING", "Brake disc transient heat transfer; m, kg, s, W, degC"]
    lines += mesh_deck(mesh, thermal=True) + material_deck(c)
    lines += ["*INITIAL CONDITIONS,TYPE=TEMPERATURE", f"ALLN, {s.ambient_c}",
              "*AMPLITUDE,NAME=BRAKE,TIME=TOTAL TIME", f"0.,1., {stop:.12g},0., {end:.12g},0."]
    for step, duration in enumerate((stop, s.cooling_s)):
        dt = duration / (80 if step == 0 else 20)
        lines += ["*STEP,INC=10000", "*HEAT TRANSFER,SOLVER=ITERATIVE SCALING", f"{dt:.12g}, {duration:.12g}, 1e-7, {dt:.12g}"]
        if step == 0:
            lines += ["*DFLUX,AMPLITUDE=BRAKE"]
            lines += [f"{mesh.exterior[i][0]}, S{mesh.exterior[i][1]}, {flux:.12g}"
                      for i in mesh.friction]
            lines += ["*FILM"]
            lines += [f"{eid}, F{face}, {s.ambient_c}, {s.convection_w_m2k}"
                      for eid, face in mesh.exterior]
        else:
            lines += ["*DFLUX,OP=NEW"]
        lines += ["*NODE PRINT,NSET=ALLN,FREQUENCY=1", "NT", "*NODE FILE", "NT", "*END STEP"]
    (folder / "thermal.inp").write_text("\n".join(lines)+"\n")
    run_ccx(folder, "thermal")
    data = parse_dat(folder / "thermal.dat")["temperatures"]
    history = []
    snapshots = []
    for time, rows in data:
        temp = nodal(rows, len(mesh.points), 1)[:, 0]
        snapshots.append(temp)
        internal = np.dot(mesh.volume_weights, temp-s.ambient_c) * c.material.density_kg_m3 * c.material.specific_heat_j_kgk
        conv_power = s.convection_w_m2k * np.dot(mesh.area_weights, temp-s.ambient_c)
        history.append([time, float(temp.max()), float(np.dot(mesh.volume_weights, temp)/mesh.volume),
                        float(internal), float(conv_power)])
    h = np.array([[0., s.ambient_c, s.ambient_c, 0., 0.]] + history)
    if abs(h[-1, 0]-end) > max(1e-5, end*1e-5):
        raise RuntimeError("Thermal solver did not reach the requested final time")
    heat_loss = np.r_[0., np.cumsum(np.diff(h[:, 0]) * (h[1:, 4]+h[:-1, 4])/2)]
    t = np.minimum(h[:, 0], stop)
    heat_in = req["initial_disc_power_w"] * (t-t*t/(2*stop))
    residual = h[:, 3] + heat_loss - heat_in
    error = float(np.max(np.abs(residual)) / req["disc_energy_j"])
    history_table = np.column_stack([h[:, :4], h[:, 4], heat_loss, heat_in, residual])
    np.savetxt(folder / "thermal_history.csv", history_table, delimiter=",", comments="",
               header="time_s,peak_c,volume_mean_c,internal_energy_j,convective_power_w,convective_loss_j,heat_input_j,balance_residual_j")
    peak_idx = int(np.argmax(h[1:, 1]))
    return snapshots[peak_idx], h, error, float(h[peak_idx+1, 0])


def structural(folder: Path, mesh: Mesh, c: Config, req, temperatures=None, job="cold"):
    lines = ["*HEADING", "Brake disc linear static envelope; SI units"]
    lines += mesh_deck(mesh) + material_deck(c)
    lines += ["*INITIAL CONDITIONS,TYPE=TEMPERATURE", f"ALLN, {c.scenario.ambient_c}",
              "*BOUNDARY", "MOUNT,1,3", "*STEP", "*STATIC"]
    if temperatures is not None:
        lines += ["*TEMPERATURE"]
        lines += [f"{i}, {t:.12g}" for i, t in enumerate(temperatures, 1)]
    else:
        lines += ["*TEMPERATURE", f"ALLN, {c.scenario.ambient_c}"]
    loads = mesh.unit_torque_loads * req["disc_torque_nm"]
    lines += ["*CLOAD"]
    lines += [f"{i+1}, {axis+1}, {f:.12g}" for i, row in enumerate(loads)
              for axis, f in enumerate(row) if abs(f) > 1e-14]
    lines += ["*NODE PRINT,NSET=ALLN", "U", "*NODE PRINT,NSET=MOUNT", "RF",
              "*EL PRINT,ELSET=DISC", "S", "*NODE FILE", "U,NT", "*EL FILE", "S", "*END STEP"]
    (folder / f"{job}.inp").write_text("\n".join(lines)+"\n")
    run_ccx(folder, job)
    data = parse_dat(folder / f"{job}.dat")
    u = nodal(data["displacements"][-1][1], len(mesh.points), 3)
    rf = data["forces"][-1][1]
    rf_ids = rf[:, 0].astype(int)-1
    coords = mesh.points[rf_ids]
    reaction = float(np.sum(coords[:, 0]*rf[:, 2] - coords[:, 1]*rf[:, 1]))
    stress = data["stresses"][-1][1]
    if len(stress) != 4*len(mesh.tets):
        raise RuntimeError("Incomplete integration-point stress output")
    expected_ids = np.repeat(np.arange(1, len(mesh.tets)+1), 4)
    expected_ips = np.tile(np.arange(1, 5), len(mesh.tets))
    stress = stress[np.lexsort((stress[:, 1], stress[:, 0]))]
    if not np.array_equal(stress[:, 0], expected_ids) or not np.array_equal(stress[:, 1], expected_ips):
        raise RuntimeError("Missing or duplicate integration-point results")
    vm = von_mises(stress[:, 2:8])
    cell_vm = np.zeros(len(mesh.tets))
    np.maximum.at(cell_vm, stress[:, 0].astype(int)-1, vm)
    if not np.all(np.isfinite(u)) or not np.all(np.isfinite(vm)):
        raise RuntimeError("Nonfinite solver results")
    import meshio
    meshio.write_points_cells(folder / f"{job}.vtu", mesh.points, [("tetra10", mesh.tets)],
                              point_data={"displacement_m": u,
                                          "temperature_c": temperatures if temperatures is not None
                                          else np.full(len(u), c.scenario.ambient_c)},
                              cell_data={"max_integration_point_von_mises_pa": [cell_vm]})
    return {"peak_stress_pa": float(vm.max()), "max_displacement_m": float(np.linalg.norm(u, axis=1).max()),
            "reaction_torque_nm": reaction,
            "reaction_torque_error_fraction": abs(reaction+req["disc_torque_nm"])/req["disc_torque_nm"],
            "cell_stress": cell_vm, "displacements": u}


def von_mises(s):
    s = np.asarray(s)
    return np.sqrt(0.5*((s[:, 0]-s[:, 1])**2 + (s[:, 1]-s[:, 2])**2 +
                        (s[:, 2]-s[:, 0])**2) + 3*np.sum(s[:, 3:6]**2, axis=1))


def parse_dat(path: Path):
    """Parse only explicitly requested, complete numeric DAT blocks; reject corruption."""
    data = {}
    header = re.compile(r"^\s*(temperatures|displacements|forces|stresses)\b.*\btime\s+([\d.Ee+D-]+)", re.I)
    kind, time, rows = None, None, []

    def flush():
        if kind:
            if not rows:
                raise RuntimeError(f"Empty {kind} block in {path}")
            arr = np.array(rows, dtype=float)
            if not np.all(np.isfinite(arr)):
                raise RuntimeError(f"Nonfinite {kind} block in {path}")
            data.setdefault(kind, []).append((time, arr))

    for line in path.read_text().splitlines():
        match = header.match(line)
        if match:
            flush()
            kind, time, rows = match[1].lower(), float(match[2].replace("D", "E")), []
        elif kind and line.strip():
            fields = line.split()
            if fields[0].isdigit():
                try:
                    rows.append([float(v.replace("D", "E")) for v in fields])
                except ValueError as exc:
                    raise RuntimeError(f"Corrupt numeric output in {path}") from exc
            else:
                flush()
                kind, rows = None, []
    flush()
    if not data:
        raise RuntimeError(f"No recognized solver results in {path}")
    return data


def nodal(rows, count, width):
    ids = rows[:, 0].astype(int)-1
    if (rows.shape != (count, width+1) or not np.array_equal(ids+1, rows[:, 0]) or len(np.unique(ids)) != count or
            ids.min() != 0 or ids.max() != count-1):
        raise RuntimeError("Incomplete or duplicate nodal results")
    result = np.empty((count, width))
    result[ids] = rows[:, 1:]
    return result
