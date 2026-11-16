"""Independent closed-form checks using real CalculiX solves."""

import json
from pathlib import Path
import numpy as np
from .mesh import Mesh, volume_integration
from .model import Config
from .solver import material_deck, mesh_deck, nodal, parse_dat, run_ccx


def reference_tet():
    vertices = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    edges = [(0, 1), (1, 2), (2, 0), (0, 3), (1, 3), (2, 3)]
    points = np.vstack([vertices, [(vertices[a]+vertices[b])/2 for a, b in edges]])
    tets = np.arange(10).reshape(1, 10)
    weights, minimum = volume_integration(points, tets)
    return Mesh(points, tets, np.empty((0, 6), int), [], np.array([], int),
                np.array([0], int), weights, np.zeros(10), np.zeros(10),
                np.zeros((10, 3)), minimum)


def verify(config: Path, out: Path):
    c = Config.load(config)
    out.mkdir(parents=True, exist_ok=True)
    mesh = reference_tet()
    mat = material_deck(c)
    initial = ["*INITIAL CONDITIONS,TYPE=TEMPERATURE", f"ALLN,{c.scenario.ambient_c}"]
    checks = []
    # Affine uniaxial-strain patch, with Poisson contractions: sigma_x = E epsilon.
    strain = 1e-4
    u = mesh.points * np.array([strain, -c.material.poisson*strain, -c.material.poisson*strain])
    lines = mesh_deck(mesh) + mat + initial + ["*BOUNDARY"]
    lines += [f"{i+1},{axis+1},{axis+1},{value:.12g}" for i, row in enumerate(u)
              for axis, value in enumerate(row)]
    lines += ["*STEP", "*STATIC", "*TEMPERATURE", f"ALLN,{c.scenario.ambient_c}",
              "*EL PRINT,ELSET=DISC", "S", "*END STEP"]
    (out / "patch.inp").write_text("\n".join(lines)+"\n")
    run_ccx(out, "patch")
    stress = parse_dat(out / "patch.dat")["stresses"][-1][1][:, 2:8]
    target = np.array([c.material.youngs_pa*strain, 0., 0., 0., 0., 0.])
    error = float(np.max(np.abs(stress-target)) / target[0])
    checks.append({"name": "uniaxial_stress_patch", "relative_error": error, "tolerance": 1e-5,
                   "passed": error < 1e-5})
    # A minimally restrained, uniformly heated tetrahedron must expand with negligible stress.
    delta = 100.
    lines = mesh_deck(mesh) + mat + initial + ["*BOUNDARY", "1,1,3", "2,2,3", "3,3,3",
             "*STEP", "*STATIC", "*TEMPERATURE", f"ALLN,{c.scenario.ambient_c+delta}",
             "*NODE PRINT,NSET=ALLN", "U", "*EL PRINT,ELSET=DISC", "S", "*END STEP"]
    (out / "expansion.inp").write_text("\n".join(lines)+"\n")
    run_ccx(out, "expansion")
    data = parse_dat(out / "expansion.dat")
    actual = nodal(data["displacements"][-1][1], 10, 3)
    expected = mesh.points*c.material.expansion_per_k*delta
    error = float(np.max(np.abs(actual-expected)) / expected.max())
    stress = float(np.max(np.abs(data["stresses"][-1][1][:, 2:8])))
    checks.append({"name": "free_thermal_expansion", "relative_error": error,
                   "max_stress_pa": stress, "tolerance": 1e-5,
                   "passed": error < 1e-5 and stress < 100})
    # Uniform volumetric heating, represented by consistent nodal integrals.
    # Exact T(t)=T0+qv*t/(rho*cp), no surface losses and no gradients.
    qv, duration = 1e6, 2.
    lines = mesh_deck(mesh, thermal=True) + mat + initial + ["*STEP", "*HEAT TRANSFER,DIRECT,SOLVER=ITERATIVE SCALING", "0.1,2.", "*CFLUX"]
    lines += [f"{i+1},11,{qv*weight:.12g}" for i, weight in enumerate(mesh.volume_weights)]
    lines += ["*NODE PRINT,NSET=ALLN", "NT", "*END STEP"]
    (out / "heating.inp").write_text("\n".join(lines)+"\n")
    run_ccx(out, "heating")
    actual = nodal(parse_dat(out / "heating.dat")["temperatures"][-1][1], 10, 1)[:, 0]
    rise = qv*duration/(c.material.density_kg_m3*c.material.specific_heat_j_kgk)
    error = float(np.max(np.abs(actual-(c.scenario.ambient_c+rise))) / rise)
    checks.append({"name": "uniform_adiabatic_heating", "relative_error": error,
                   "expected_rise_k": rise, "tolerance": 1e-4, "passed": error < 1e-4})
    # Fourier-law patch: prescribed affine T gives exact uniform q = -k grad(T).
    gradient = np.array([10., 20., -5.])
    temperatures = c.scenario.ambient_c + mesh.points @ gradient
    lines = mesh_deck(mesh, thermal=True) + mat + initial + ["*BOUNDARY"]
    lines += [f"{i+1},11,11,{value:.12g}" for i, value in enumerate(temperatures)]
    lines += ["*STEP", "*HEAT TRANSFER,STEADY STATE,SOLVER=ITERATIVE SCALING", "*EL PRINT,ELSET=DISC", "HFL", "*END STEP"]
    (out / "conduction.inp").write_text("\n".join(lines)+"\n")
    run_ccx(out, "conduction")
    # Heat flux has its own DAT header; parse the four integration-point rows explicitly.
    text = (out / "conduction.dat").read_text()
    import re
    rows = [list(map(float, line.split())) for line in text.splitlines()
            if re.match(r"^\s+1\s+[1-4]\s+[-+0-9.]", line)]
    if len(rows) != 4:
        raise RuntimeError("Incomplete conduction patch output")
    flux = np.array(rows)[:, 2:5]
    expected = -c.material.conductivity_w_mk * gradient
    error = float(np.max(np.abs(flux-expected))/np.max(np.abs(expected)))
    checks.append({"name": "fourier_conduction_patch", "relative_error": error,
                   "tolerance": 1e-5, "passed": error < 1e-5})
    report = {"passed": all(x["passed"] for x in checks), "checks": checks}
    (out / "verification.json").write_text(json.dumps(report, indent=2)+"\n")
    return report
