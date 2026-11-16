"""Validated configuration and first-principles braking calculations."""

from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re

GRAVITY_M_S2 = 9.80665


def positive(**values):
    for key, value in values.items():
        if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{key} must be finite and positive")


@dataclass(frozen=True)
class Scenario:
    mass_kg: float
    speed_kmh: float
    deceleration_m_s2: float
    wheel_radius_m: float
    brake_share: float
    disc_count: int
    pad_friction: float
    disc_heat_fraction: float
    ambient_c: float
    cooling_s: float
    convection_w_m2k: float
    cg_height_m: float
    wheelbase_m: float
    rear_weight_fraction: float
    tyre_friction: float
    braked_axle: str

    def __post_init__(self):
        positive(**{k: v for k, v in asdict(self).items() if k not in {"ambient_c", "braked_axle"}})
        if self.braked_axle not in {"rear", "all"}:
            raise ValueError("braked_axle must be 'rear' or 'all'")
        if not 0 < self.rear_weight_fraction < 1:
            raise ValueError("rear_weight_fraction must be in (0, 1)")
        if not 0 < self.brake_share <= 1 or not 0 < self.disc_heat_fraction <= 1:
            raise ValueError("brake_share and disc_heat_fraction must be in (0, 1]")
        if type(self.disc_count) is not int or not math.isfinite(self.ambient_c):
            raise ValueError("disc_count must be an integer and ambient_c finite")
        if self.ambient_c <= -273.15:
            raise ValueError("ambient_c must exceed absolute zero")


@dataclass(frozen=True)
class Material:
    name: str
    density_kg_m3: float
    youngs_pa: float
    poisson: float
    yield_pa: float
    conductivity_w_mk: float
    specific_heat_j_kgk: float
    expansion_per_k: float

    def __post_init__(self):
        positive(**{k: v for k, v in asdict(self).items() if k not in {"name", "poisson"}})
        if not -1 < self.poisson < 0.5:
            raise ValueError("Poisson ratio must be in (-1, 0.5)")


@dataclass(frozen=True)
class Design:
    name: str
    outer_diameter_mm: float
    thickness_mm: float
    bore_diameter_mm: float
    bolt_pcd_mm: float
    bolt_count: int
    bolt_diameter_mm: float
    sweep_inner_radius_mm: float
    drill_count: int
    drill_diameter_mm: float
    drill_pcd_mm: float

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", self.name):
            raise ValueError("Design name must be a safe lowercase identifier")
        positive(**{k: getattr(self, k) for k in (
            "outer_diameter_mm", "thickness_mm", "bore_diameter_mm", "bolt_pcd_mm",
            "bolt_diameter_mm", "sweep_inner_radius_mm")})
        if type(self.bolt_count) is not int or self.bolt_count < 3:
            raise ValueError("At least three bolt holes are required")
        if type(self.drill_count) is not int or self.drill_count < 0:
            raise ValueError("drill_count must be a nonnegative integer")
        for key in ("drill_diameter_mm", "drill_pcd_mm"):
            value = getattr(self, key)
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
        ri, rb, rh = self.bore_diameter_mm / 2, self.bolt_pcd_mm / 2, self.bolt_diameter_mm / 2
        if not ri < rb - rh < rb + rh < self.sweep_inner_radius_mm < self.outer_diameter_mm / 2:
            raise ValueError("Bore, bolt holes and swept annulus overlap or are out of order")
        if self.bolt_diameter_mm >= self.bolt_pcd_mm * math.sin(math.pi / self.bolt_count):
            raise ValueError("Adjacent bolt holes overlap")
        if self.drill_count:
            positive(drill_diameter_mm=self.drill_diameter_mm, drill_pcd_mm=self.drill_pcd_mm)
            rd, hd = self.drill_pcd_mm / 2, self.drill_diameter_mm / 2
            if not self.sweep_inner_radius_mm < rd - hd < rd + hd < self.outer_diameter_mm / 2:
                raise ValueError("Drilled holes must lie wholly inside the swept annulus")
            if self.drill_count > 1 and self.drill_diameter_mm >= self.drill_pcd_mm * math.sin(
                math.pi / self.drill_count
            ):
                raise ValueError("Adjacent drilled holes overlap")

    @property
    def effective_radius_m(self):
        """Uniform-pressure effective radius; holes are ignored in this sizing estimate."""
        ro, ri = self.outer_diameter_mm / 2000, self.sweep_inner_radius_mm / 1000
        return 2 / 3 * (ro**3 - ri**3) / (ro**2 - ri**2)

    @property
    def analytical_volume_m3(self):
        area = math.pi / 4 * (
            self.outer_diameter_mm**2 - self.bore_diameter_mm**2
            - self.bolt_count * self.bolt_diameter_mm**2
            - self.drill_count * self.drill_diameter_mm**2
        )
        return area * self.thickness_mm * 1e-9


@dataclass(frozen=True)
class Limits:
    min_safety_factor: float
    max_temperature_c: float
    max_volume_error_fraction: float
    max_energy_error_fraction: float
    max_reaction_torque_error_fraction: float

    def __post_init__(self):
        positive(**asdict(self))


@dataclass(frozen=True)
class Config:
    scenario: Scenario
    material: Material
    limits: Limits
    mesh_mm: float
    variants: tuple[Design, ...]

    def __post_init__(self):
        positive(mesh_mm=self.mesh_mm)
        if not self.variants or len({v.name for v in self.variants}) != len(self.variants):
            raise ValueError("Provide at least one variant with unique names")

    @classmethod
    def load(cls, path: Path):
        d = json.loads(path.read_text())
        return cls(Scenario(**d["scenario"]), Material(**d["material"]), Limits(**d["limits"]),
                   d["mesh_mm"], tuple(Design(**v) for v in d["variants"]))


def grip(s: Scenario):
    """Tyre-grip limit of the braked axle with quasi-static longitudinal load transfer."""
    g, a = GRAVITY_M_S2, s.deceleration_m_s2
    if s.braked_axle == "all":
        load = s.mass_kg * g
        limit = s.tyre_friction * g
    else:
        # Braking moves load forward by M a h / L, unloading the rear axle.
        load = s.mass_kg * (g * s.rear_weight_fraction - a * s.cg_height_m / s.wheelbase_m)
        limit = s.tyre_friction * g * s.rear_weight_fraction / (
            1 + s.tyre_friction * s.cg_height_m / s.wheelbase_m)
    utilisation = s.mass_kg * a / (s.tyre_friction * load) if load > 0 else None
    return {"braked_axle_load_n": load, "grip_limit_deceleration_m_s2": limit,
            "tyre_friction_utilisation": utilisation}


def requirements(s: Scenario, d: Design, m: Material):
    v = s.speed_kmh / 3.6
    torque = s.mass_kg * s.deceleration_m_s2 * s.wheel_radius_m * s.brake_share / s.disc_count
    energy = 0.5 * s.mass_kg * v**2 * s.brake_share * s.disc_heat_fraction / s.disc_count
    mass = d.analytical_volume_m3 * m.density_kg_m3
    return {
        "speed_m_s": v, "stop_time_s": v / s.deceleration_m_s2,
        "stop_distance_m": v**2 / (2 * s.deceleration_m_s2),
        "disc_torque_nm": torque, "effective_radius_m": d.effective_radius_m,
        "total_pad_normal_force_n": torque / (s.pad_friction * d.effective_radius_m),
        "normal_force_per_pad_n": torque / (2 * s.pad_friction * d.effective_radius_m),
        "disc_energy_j": energy, "initial_disc_power_w": 2 * energy / (v / s.deceleration_m_s2),
        "analytical_mass_kg": mass, "adiabatic_mean_rise_k": energy / (mass * m.specific_heat_j_kgk),
        **grip(s),
    }
