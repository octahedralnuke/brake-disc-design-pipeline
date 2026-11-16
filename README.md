# Brake Disc Design Pipeline

[![Design verification](https://github.com/octahedralnuke/brake-disc-design-pipeline/actions/workflows/design.yml/badge.svg)](https://github.com/octahedralnuke/brake-disc-design-pipeline/actions/workflows/design.yml)
![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A working engineering automation project that turns kart braking requirements into parameterized disc models, finite element analyses and a checked design comparison.

**Python · CadQuery · Gmsh · CalculiX · GitHub Actions**

![Mass–temperature–stress comparison](docs/assets/tradeoff.png)

Each dot is one analysed disc design. The horizontal axis shows disc mass, the vertical axis shows peak temperature, and colour shows peak von Mises stress: blue is lower stress and yellow is higher stress. The lightweight disc saves mass but reaches a higher temperature. The thicker, 9 mm drilled disc has more thermal mass and a lower peak temperature, while its holes create local stress concentrations. The baseline has the lowest peak stress of these three designs. All three meet the configured screening limits. The plotted values are saved in [the results CSV](examples/study/tradeoff.csv).

## Features

- Checks the requested deceleration against the braked axle's tyre-grip limit, including load transfer.
- Calculates brake torque, pad normal forces, stopping time, braking energy and analytical mean temperature rise.
- Builds solid and drilled disc variants in CadQuery; exports STEP solids, DXF profiles and dimensioned SVG drawings.
- Imports and partitions STEP geometry in Gmsh, selects physical surfaces and creates conforming quadratic tetrahedral meshes.
- Runs real CalculiX analyses: cold static torque, transient braking/cooling, and a hot static thermal-stress envelope.
- Checks yield safety factor, peak temperature, reaction torque, CAD/mesh volume and thermal energy balance.
- Produces an offline HTML report, CSV/JSON results, temperature/stress plots, ParaView VTU fields and complete solver decks/logs.
- Repeats the workflow on pushes and pull requests. Solver failures and failed criteria reject the CI job.

```mermaid
flowchart LR
    A[JSON requirements] --> B[Brake sizing]
    B --> C[CadQuery / STEP]
    C --> D[Gmsh quadratic mesh]
    D --> E[Cold static FEA]
    D --> F[Transient thermal FEA]
    F --> G[Hot static FEA]
    E --> H[Checks and trade-off report]
    G --> H
    H --> I[Actions artifacts]
```

## Quick start

The tested environment uses Linux, Python 3.11 and CalculiX 2.21. Python 3.12 is supported by the package configuration. On Windows, use WSL2/Ubuntu or the container option. Run commands from the repository root.

Install system dependencies on Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y calculix-ccx libglu1-mesa libgl1 libxrender1 libxext6 python3-venv
```

Create an environment with Python 3.11 or 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
brakedisc doctor
brakedisc run
```

Open **`results/report.html`** in a browser; no server is required. Real solver runs take several minutes. Repeat with `brakedisc run --overwrite`; only a marked, previously generated run directory can be replaced.

If your system Python is newer than 3.12, use [uv](https://docs.astral.sh/uv/getting-started/installation/) to obtain an isolated compatible runtime:

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip sync requirements.lock
uv pip install --no-deps -e .
brakedisc run
```

For a custom solver location, set `CCX` to its executable path.

### Container option

```bash
docker build -t brake-disc-design .
mkdir -p results
docker run --rm -v "$PWD/results:/app/results" brake-disc-design
```

The Dockerfile provides an alternative dependency setup. CI validates the native Ubuntu installation path.

## Commands

| Command | Purpose |
|---|---|
| `brakedisc doctor` | Check imports and locate CalculiX |
| `brakedisc size` | Print analytical braking requirements |
| `brakedisc run` | Run all configured variants and enforce limits |
| `brakedisc run --variant baseline --out results-baseline` | Run one variant |
| `brakedisc run --mesh-mm 5 --out results-mesh5` | Change the mesh target |
| `brakedisc verify` | Run four analytical solver benchmarks |
| `brakedisc converge` | Compare the baseline at 6, 5 and 4 mm mesh targets |
| `brakedisc check results/summary.json` | Re-evaluate a saved study |
| `pytest -q` | Run unit and real-solver integration tests |

Exit **0** means success, **2** means a completed study was rejected, and **1** means an input, dependency or execution error. A solver error within a multi-variant study is saved in the summary and rejects that study.

### Demonstrate rejection

Recheck a passing study against an impossible safety requirement:

```bash
python scripts/assert_gate_failure.py results/summary.json
```

Or run the supplied **2 mm disc**, whose geometry is intentionally inadequate for this load case:

```bash
brakedisc run --config configs/rejected.json --out results-rejected
```

The latter runs actual CAD and FEA and is expected to exit with status 2. Its report identifies the failed criteria. This configuration is excluded from the normal passing sweep.

## Default study

The inputs are typical assumed values for a student-built kart with a single rear disc, not measured data from a specific vehicle.

| Input | Value |
|---|---:|
| Kart + driver mass | 180 kg |
| Initial speed | 70 km/h |
| CG height / wheelbase | 0.30 m / 1.05 m |
| Static rear weight | 60% |
| Tyre–road friction coefficient | 1.0 |
| Braked axle | Rear only |
| Design deceleration | 4.5 m/s² (rear-grip limit 4.58 m/s²) |
| Wheel rolling radius | 0.14 m |
| Brake share / discs | 100% / 1 |
| Pad friction coefficient | 0.40 |
| Allocated heat entering disc | 90% |
| Initial / ambient temperature | 25 °C |
| Assumed convection coefficient | 30 W/(m²·K) |
| Cooling after stop | 8 s |

With rear-only braking, load transfer limits deceleration to **4.58 m/s² (0.47 g)**, so the design case uses 4.5 m/s² (98% tyre friction utilisation). Asking this kart for 7 m/s² fails the `tyre_grip` check. These inputs give **113.4 N·m**, **3,471 N total normal force across both pads**, a **4.321 s** stop and **30.625 kJ** of disc heat. Uniform annular pressure gives an effective friction radius of 81.667 mm.

All variants have a 200 mm outside diameter, 40 mm bore, six Ø8 mm bolt holes on a 70 mm PCD and a swept annulus from R60 to R100 mm. Baseline thickness is 7 mm; lightweight thickness is 6 mm; the drilled disc is 9 mm thick with twelve Ø8 mm holes on a 160 mm PCD.

<!-- VERIFIED_RESULTS_START -->
| Variant | Mass / kg | Peak / °C | Stress / MPa | Safety factor | Result |
|---|---:|---:|---:|---:|---|
| baseline | 1.641 | 83.4 | 121.7 | 2.05 | PASS |
| lightweight | 1.406 | 92.7 | 143.6 | 1.74 | PASS |
| drilled | 2.067 | 72.6 | 157.1 | 1.59 | PASS |

These values are captured CalculiX results, not illustrative chart data. Open [the saved report](examples/study/report.html) after downloading the repository, or inspect [the numeric summary](examples/study/summary.json).

![Baseline temperature and stress fields](docs/assets/baseline-fields.png)

The left panel maps temperature across the baseline disc at its thermal peak; the right panel maps von Mises stress in the hot structural case. Each colour bar gives the corresponding values and units. The fields show where heating and stress concentrate within the disc.
<!-- VERIFIED_RESULTS_END -->

### Design decision

Peak stress comes mainly from thermal expansion, not braking torque: the cold torque-only case stays below 10 MPa, and reducing the design deceleration from 7 to 4.5 m/s² changed baseline peak stress by less than 1%. Disc thermal mass therefore drives the design.

For this single-stop load case the **7 mm solid baseline is recommended**. It has the largest margin (SF 2.05) at 1.64 kg.

- The 6 mm lightweight disc saves 0.24 kg (14%) and still passes at SF 1.74, but peaks 9 °C hotter. Repeated stops, which this model does not simulate, would widen that gap, so the extra margin of the baseline is kept.
- Drilling did not pay off. The 7 mm drilled disc fails the stress gate (SF 1.30, [preserved outputs](examples/rejected-drilled/)), and passing required 9 mm, making the drilled disc 26% heavier than the baseline. Because convection is prescribed, the model cannot credit drilling with any airflow cooling benefit.

Material properties are explicitly assumed **generic steel** values, not certified rotor-alloy data. See [configuration](configs/kart.json) and [methodology](docs/methodology.md).

## Verification and interpretation

- Four real-solver benchmarks check uniaxial stress, free thermal expansion, uniform adiabatic heating and Fourier conduction.
- Conservation checks cover reaction torque, integrated thermal energy and CAD/mesh volume.
- A separate three-mesh study compares temperature rise, swept-region stress and displacement. The raw global stress maximum is also reported. [Verification evidence](docs/verification.md)
- Invalid geometry, incomplete output, nonfinite data and solver failures cannot silently pass.

Safety factor is assumed yield strength divided by the maximum integration-point von Mises stress across the cold/hot envelope, including the idealized mount. Default limits are SF ≥ 1.5, temperature ≤ 250 °C and tyre friction utilisation ≤ 1, plus numerical consistency criteria. These are project screening settings.

Heating is averaged around the swept annulus; bolt-hole surfaces form an idealized rigid mount. Local moving pad contact, brake fade, repeated-stop fatigue, wear, fluid flow and bolt flexibility are outside the model. Drawings contain nominal dimensions without assigned manufacturing tolerances. Results support educational design screening.

## Outputs and repository map

```text
configs/                 Requirements, material, variants and limits
src/brakedisc/           Sizing, CAD, mesh, solver, reports and CLI
tests/                   Physics, validation, parser and integration tests
docs/                    Methodology and verification evidence
examples/study/          Committed results from the verified sweep
examples/convergence/    Committed mesh-sensitivity results
.github/workflows/       Continuous engineering verification
results/                Regenerated complete outputs (git-ignored)
```

Each variant produces STEP, DXF and SVG geometry, `.msh`/`.npz` meshes, cold/thermal/hot `.inp` decks and solver outputs, cold/hot `.vtu` fields, plots and `thermal_history.csv`. The study adds `report.html`, JSON/CSV comparisons, trade-off plots, resolved inputs and SHA-256 artifact hashes. Native `.msh` coordinates are in **mm**; solver, NumPy and VTU coordinates are in **m**.

Large regenerated solver outputs are downloadable CI artifacts. From [Actions](https://github.com/octahedralnuke/brake-disc-design-pipeline/actions), download `brake-disc-study`, extract it and open the report.

## References

- [CadQuery CAD export documentation](https://cadquery.readthedocs.io/en/latest/importexport.html)
- [Gmsh manual and API](https://gmsh.info/doc/texinfo/)
- [CalculiX solver and official manuals](https://www.dhondt.de/)
- [GitHub Actions artifacts](https://docs.github.com/en/actions/tutorials/store-and-share-data)

Source is MIT licensed. External tools retain their own licences; see [third-party notices](THIRD_PARTY.md).
