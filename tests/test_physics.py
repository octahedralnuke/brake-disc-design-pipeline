from dataclasses import replace
import math
import numpy as np
import pytest
from brakedisc.model import requirements
from brakedisc.mesh import surface_integration, tet_shape
from brakedisc.verification import reference_tet
from brakedisc.solver import von_mises


def test_requirements_against_hand_calculation(config):
    r = requirements(config.scenario, config.variants[0], config.material)
    assert r["disc_torque_nm"] == pytest.approx(176.4)
    assert r["stop_time_s"] == pytest.approx(25/9)
    assert r["disc_energy_j"] == pytest.approx(30625.)
    assert r["effective_radius_m"] == pytest.approx(49/600)
    assert r["total_pad_normal_force_n"] == pytest.approx(5400.)
    assert r["normal_force_per_pad_n"] == pytest.approx(2700.)


def test_energy_scales_with_speed_squared(config):
    s, d, m = config.scenario, config.variants[0], config.material
    a, b = requirements(s, d, m), requirements(replace(s, speed_kmh=2*s.speed_kmh), d, m)
    assert b["disc_energy_j"] == pytest.approx(4*a["disc_energy_j"])
    assert b["disc_torque_nm"] == a["disc_torque_nm"]


def test_disc_count_and_heat_partition(config):
    s, d, m = config.scenario, config.variants[0], config.material
    r = requirements(replace(s, disc_count=2, brake_share=0.5, disc_heat_fraction=0.5), d, m)
    assert r["disc_torque_nm"] == pytest.approx(44.1)
    assert r["disc_energy_j"] == pytest.approx(0.5*180*(70/3.6)**2*0.5*0.5/2)


def test_volume_includes_removed_holes(config):
    d = config.variants[2]
    expected = math.pi/4*(200**2-40**2-6*8**2-12*8**2)*9*1e-9
    assert d.analytical_volume_m3 == pytest.approx(expected)


@pytest.mark.parametrize("field,value", [("mass_kg", 0), ("speed_kmh", float("nan")),
    ("brake_share", 1.1), ("disc_count", 1.5), ("pad_friction", -0.1), ("ambient_c", -274)])
def test_invalid_scenario(config, field, value):
    with pytest.raises(ValueError):
        replace(config.scenario, **{field: value})


@pytest.mark.parametrize("changes", [{"name": "../escape"}, {"thickness_mm": 0},
    {"bore_diameter_mm": 80}, {"bolt_count": 2}, {"drill_count": 12, "drill_pcd_mm": 199},
    {"bolt_count": 100}, {"drill_count": -1}, {"drill_diameter_mm": float("nan")},
    {"drill_pcd_mm": -1}])
def test_invalid_geometry(config, changes):
    with pytest.raises(ValueError):
        replace(config.variants[0], **changes)


def test_tet_partition_of_unity_and_volume():
    n, dn = tet_shape(np.array([0.1, 0.2, 0.3, 0.4]))
    assert n.sum() == pytest.approx(1)
    assert dn.sum(axis=0) == pytest.approx(np.zeros(3), abs=1e-14)
    mesh = reference_tet()
    assert mesh.volume == pytest.approx(1/6)
    assert mesh.volume_weights[:4] == pytest.approx(np.full(4, -1/120))
    assert mesh.volume_weights[4:] == pytest.approx(np.full(6, 1/30))


def test_quadratic_surface_weights():
    # Offset triangle avoids the polar origin used by the traction integrator.
    points = np.array([[1., 0., 0.], [2., 0., 0.], [1., 1., 0.],
                       [1.5, 0., 0.], [1.5, 0.5, 0.], [1., 0.5, 0.]])
    weights, _ = surface_integration(points, np.arange(6).reshape(1, 6))
    assert weights.sum() == pytest.approx(0.5)
    assert weights[:3] == pytest.approx(np.zeros(3), abs=1e-14)
    assert weights[3:] == pytest.approx(np.full(3, 1/6))


def test_von_mises_known_states():
    stress = np.array([[100., 0., 0., 0., 0., 0.], [100., 100., 100., 0., 0., 0.],
                       [0., 0., 0., 50., 0., 0.]])
    assert von_mises(stress) == pytest.approx([100., 0., math.sqrt(3)*50])
