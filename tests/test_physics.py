from dataclasses import replace
import math
import numpy as np
import pytest
from brakedisc.model import GRAVITY_M_S2, grip, requirements
from brakedisc.pipeline import evaluate
from brakedisc.mesh import surface_integration, tet_shape
from brakedisc.verification import reference_tet
from brakedisc.solver import von_mises


def test_requirements_against_hand_calculation(config):
    r = requirements(config.scenario, config.variants[0], config.material)
    assert r["disc_torque_nm"] == pytest.approx(113.4)
    assert r["stop_time_s"] == pytest.approx(350/81)
    assert r["disc_energy_j"] == pytest.approx(30625.)
    assert r["effective_radius_m"] == pytest.approx(49/600)
    assert r["total_pad_normal_force_n"] == pytest.approx(24300/7)
    assert r["normal_force_per_pad_n"] == pytest.approx(12150/7)


def test_energy_scales_with_speed_squared(config):
    s, d, m = config.scenario, config.variants[0], config.material
    a, b = requirements(s, d, m), requirements(replace(s, speed_kmh=2*s.speed_kmh), d, m)
    assert b["disc_energy_j"] == pytest.approx(4*a["disc_energy_j"])
    assert b["disc_torque_nm"] == a["disc_torque_nm"]


def test_disc_count_and_heat_partition(config):
    s, d, m = config.scenario, config.variants[0], config.material
    r = requirements(replace(s, disc_count=2, brake_share=0.5, disc_heat_fraction=0.5), d, m)
    assert r["disc_torque_nm"] == pytest.approx(28.35)
    assert r["disc_energy_j"] == pytest.approx(0.5*180*(70/3.6)**2*0.5*0.5/2)


def test_rear_grip_limit_against_hand_calculation(config):
    g = grip(config.scenario)
    # a_max = mu g f / (1 + mu h / L) = 0.6 g / (1 + 0.3/1.05)
    assert g["grip_limit_deceleration_m_s2"] == pytest.approx(0.6*GRAVITY_M_S2*1.05/1.35)
    assert g["braked_axle_load_n"] == pytest.approx(180*(0.6*GRAVITY_M_S2 - 4.5*0.3/1.05))
    assert g["tyre_friction_utilisation"] == pytest.approx(180*4.5/g["braked_axle_load_n"])
    assert g["tyre_friction_utilisation"] < 1


def test_utilisation_reaches_one_at_grip_limit(config):
    s = config.scenario
    limit = grip(s)["grip_limit_deceleration_m_s2"]
    assert grip(replace(s, deceleration_m_s2=limit))["tyre_friction_utilisation"] == pytest.approx(1)


def gate(scenario, config):
    result = {"requirements": requirements(scenario, config.variants[0], config.material),
              "safety_factor": 3., "peak_temperature_c": 100., "volume_error_fraction": 0.,
              "energy_error_fraction": 0., "reaction_torque_error_fraction": 0., "solver_completed": True}
    return evaluate(result, {"min_safety_factor": 1.5, "max_temperature_c": 250.,
                             "max_volume_error_fraction": .01, "max_energy_error_fraction": .02,
                             "max_reaction_torque_error_fraction": .01})["tyre_grip"]


def test_rear_braked_kart_cannot_stop_at_7_m_s2(config):
    s = config.scenario
    assert gate(s, config)
    assert not gate(replace(s, deceleration_m_s2=7.0), config)
    # The same request is within grip when all four wheels brake.
    assert gate(replace(s, deceleration_m_s2=7.0, braked_axle="all"), config)


def test_lifted_rear_axle_is_rejected(config):
    s = replace(config.scenario, deceleration_m_s2=30.0)
    assert grip(s)["tyre_friction_utilisation"] is None
    assert not gate(s, config)


def test_volume_includes_removed_holes(config):
    d = config.variants[2]
    expected = math.pi/4*(200**2-40**2-6*8**2-12*8**2)*9*1e-9
    assert d.analytical_volume_m3 == pytest.approx(expected)


@pytest.mark.parametrize("field,value", [("mass_kg", 0), ("speed_kmh", float("nan")),
    ("brake_share", 1.1), ("disc_count", 1.5), ("pad_friction", -0.1), ("ambient_c", -274),
    ("braked_axle", "front"), ("rear_weight_fraction", 1.2), ("cg_height_m", 0), ("tyre_friction", float("inf"))])
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
