import numpy as np
import pytest
from brakedisc.geometry import build
from brakedisc.mesh import generate
from brakedisc.verification import verify

pytestmark = pytest.mark.integration


def test_calculix_analytical_benchmarks(tmp_path, config_path):
    assert verify(config_path, tmp_path)["passed"]


def test_cad_mesh_and_torque_conservation(tmp_path, config):
    d = config.variants[2]
    cad_volume = build(d, tmp_path)
    mesh = generate(tmp_path / "disc.step", d, 6., tmp_path)
    assert abs(mesh.volume/cad_volume-1) < 0.005
    assert mesh.min_jacobian > 0
    torque = np.sum(mesh.points[:, 0]*mesh.unit_torque_loads[:, 1] -
                    mesh.points[:, 1]*mesh.unit_torque_loads[:, 0])
    assert torque == pytest.approx(1., abs=1e-12)
    assert np.linalg.norm(mesh.unit_torque_loads.sum(axis=0)) < 1e-7
    # Every mount node lies on one of the actual bolt cylinders (all quantities in m).
    from brakedisc.geometry import hole_centers
    centers = np.array(hole_centers(d.bolt_pcd_mm, d.bolt_count))*1e-3
    distance = np.linalg.norm(mesh.points[mesh.mount, None, :2]-centers[None, :, :], axis=2)
    assert np.min(abs(distance-d.bolt_diameter_mm/2000), axis=1).max() < 1e-8
