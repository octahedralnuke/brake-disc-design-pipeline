# Engineering methodology

## Scope and units

This workflow compares flat steel kart discs under a prescribed single-stop requirement. Geometry parameters and CadQuery/Gmsh CAD models use mm. Coordinates are explicitly multiplied by `1e-3` before generating CalculiX decks. Analysis uses m, kg, s, N, Pa, W and J. Temperatures use °C consistently, with thermal strain referenced to initial temperature. Radiation is omitted.

The selected deceleration is an input requirement, checked against the tyre-grip limit of the braked axle (below). Hydraulic pedal effort and service life are not predicted.

## Tyre-grip limit

A disc only sees as much torque as the tyres can transmit, so the requested deceleration is checked before the disc is sized. Let `g` be standard gravity, `h` CG height, `L` wheelbase, `f` static rear weight fraction and `mu_t` tyre-road friction. Braking transfers load `M a h / L` from the rear to the front axle:

```text
N_rear = M (g f - a h / L)
a_max  = mu_t g f / (1 + mu_t h / L)     rear-axle braking
a_max  = mu_t g                          all-wheel braking
u      = M a / (mu_t N_braked)           tyre friction utilisation
```

The `tyre_grip` criterion requires `u <= 1`; a requested deceleration that unloads the braked axle completely is rejected. The default kart brakes the rear axle only, so `a_max` is 4.58 m/s² (0.47 g) and the design deceleration is set just below it at 4.5 m/s². A 7 m/s² request on the same kart fails this check, although it would be achievable with all-wheel braking. The quasi-static model ignores suspension and tyre dynamics, and tyre friction is an assumed value.

## Braking calculations

Let `M` be total mass, `v` initial speed, `a` deceleration, `Rw` wheel radius, `b` brake share, `n` number of discs, `mu` pad friction and `eta` heat fraction entering the disc.

```text
F_vehicle = M a
T_disc = M a Rw b / n
t_stop = v / a
s_stop = v² / (2a)
Q_disc = (1/2) M v² b eta / n
P_disc(t) = (2 Q_disc / t_stop) (1 - t/t_stop), 0 <= t <= t_stop
```

Aerodynamic drag, rolling resistance, gradient and rotational kinetic energy are neglected. For uniform pressure on a continuous annulus:

```text
r_eff = (2/3) (ro³ - ri³) / (ro² - ri²)
N_total = T_disc / (mu r_eff)
N_per_pad = N_total / 2
Delta_T_mean = Q_disc / (m_disc cp)
```

`N_total` is the sum of normal-force magnitudes on both faces, avoiding an ambiguous factor of two in "clamping force". Drilled holes are ignored in the effective-radius sizing estimate; actual structural loads integrate the surviving meshed faces and are normalized to the required torque. The temperature estimate is the adiabatic **whole-disc mean rise**, not a surface peak.

## Parametric CAD and mesh

CadQuery extrudes the annular disc and cuts mounting/drilled holes. Validation rejects overlapping features, invalid solids and multiple solids. CAD volume is checked against the exact annulus-minus-holes formula. The same dimensions generate STEP, DXF and dimensioned SVG outputs.

Gmsh partitions the STEP disc at the swept annulus's inner radius. Boolean-fragment mappings retain only fragments of the original disc, and shared interfaces mesh conformingly. Surfaces are selected by geometry rather than fixed STEP face indices. Selection must find two swept faces and the configured bolt-wall count.

Quadratic tetrahedra use Gmsh type 11, reordered to CalculiX C3D10/DC3D10 and VTK tetra10. The final two Gmsh midside-node positions are exchanged. Shared internal faces are cancelled; exterior triangles map to CalculiX tetrahedral face labels.

Curved surface integration uses 4×4 Duffy quadrature; curved volume/nodal integration uses 4×4×4 quadrature. Nonpositive sampled Jacobians reject the mesh. CAD/mesh volume must agree within 1%.

## Structural model

- Linear isotropic elasticity, small displacement.
- All three displacements fixed on bolt-hole cylindrical surfaces: an idealized rigid mount.
- Tangential traction on both swept faces, averaged around the circumference.
- Consistent quadratic nodal integration and exact normalization to the required z torque.
- A cold full-torque solve and a full-torque solve with the hottest sampled thermal field.
- Yield screening from the maximum integration-point von Mises stress across these solves.

The hot case is a screening envelope, not a continuous stress history or two-way contact simulation. Balanced axial pad pressure, local pad bending, bolt flexibility and rotational body loading are omitted. Pad forces are sizing outputs, not local contact loads.

Mount nodes receive no braking traction, so their printed forces represent reactions. Their moment must oppose and match applied torque within 1%. Ideal mounting constraints can produce local concentrations: raw global peak stress remains reported and controls the design gate. Mesh sensitivity additionally tracks swept-region stress to distinguish disc behavior from mount idealization.

## Transient heat transfer

The disc starts uniformly at ambient. Prescribed heat flux acts on the actual surviving swept-face area, on both sides, and decays linearly with speed. Its continuous-time integral is `Q_disc`. Each geometry therefore receives the same braking energy, even when holes reduce its friction area.

All exterior faces exchange heat with ambient through an assumed uniform convection coefficient. Conductivity and heat capacity are constant. Hub conduction and pads are not modeled; the heat fraction represents the assumed disc/pad energy partition. Circumferential averaging omits local moving-pad hot spots.

The linear thermal systems use CalculiX's built-in `ITERATIVE SCALING` solver. Its temperatures are checked against the direct SPOOLES reference for the revised drilled disc. Structural cases retain the installed default direct solver. This changes the linear-system solution method, not the mesh, loads, time increments or acceptance limits.

Maximum time increments are `t_stop/80` while braking and `t_cooling/20` afterward. Time discretization introduces a small source-energy error, measured against continuous-time input rather than hidden by rescaling the source. The maximum energy residual must remain below 2% of stop heat.

```text
U(t) = integral_V rho cp [T(t) - T_ambient] dV
Q_loss(t) = integral_0^t integral_A h [T - T_ambient] dA dt
residual(t) = U(t) + Q_loss(t) - Q_input(t)
```

Curved-mesh nodal weights integrate mean temperature and internal energy. Surface weights integrate convective power; its time integral uses the trapezoidal rule. CSV output exposes every term. Results must include every node and reach the requested final time.

## Materials and limits

| Assumed generic-steel property | Value |
|---|---:|
| Density | 7,850 kg/m³ |
| Young's modulus | 200 GPa |
| Poisson ratio | 0.30 |
| Yield strength | 250 MPa |
| Thermal conductivity | 45 W/(m·K) |
| Specific heat | 470 J/(kg·K) |
| Expansion coefficient | 12 × 10⁻⁶ /K |

These are illustrative constant inputs, not certified or measured data for a rotor alloy. Temperature dependence, plasticity, fatigue and oxidation are omitted. SF 1.5 and 250 °C are screening settings, not regulatory or pad-fade criteria. Drawings contain nominal dimensions without manufacturing tolerances.

## Reproducibility

Runs save resolved inputs, configuration hash, package/solver versions, available Git commit, results and SHA-256 artifact hashes. Meshing and solving use one thread. Cross-platform element numbering and peaks can vary slightly, so verification uses engineering tolerances rather than byte-identical outputs.

Four solver patches check stress, expansion, heat capacity and Fourier flux. Three meshes check sensitivity. No physical test correlation is claimed: evidence is analytical and numerical verification.
