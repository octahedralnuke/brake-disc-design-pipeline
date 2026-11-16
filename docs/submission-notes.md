# Submission map

| Project requirement | Implementation | Evidence |
|---|---|---|
| Requirements to torque, force and heat | `src/brakedisc/model.py` | `brakedisc size`; physics tests |
| Parameterized disc variants | `src/brakedisc/geometry.py` | STEP, DXF and dimensioned SVG for each variant |
| Automated volume meshing | `src/brakedisc/mesh.py` | Gmsh mesh, positive sampled Jacobians, volume comparison |
| Structural FEA | `src/brakedisc/solver.py` | Cold/hot `.inp`, `.dat`, `.frd`, logs and VTU files |
| Transient thermal FEA | `src/brakedisc/solver.py` | Thermal deck, temperature history and energy balance |
| Fail CI on exceeded limits | `src/brakedisc/pipeline.py`, workflow | Failed-gate demonstration; inadequate thin-disc study |
| Engineering outputs | `src/brakedisc/report.py`, geometry module | HTML report, CSV, charts, CAD and drawings |
| Reproducibility | `requirements.lock`, Dockerfile, workflow | Version metadata, input hashes, artifact manifest |
| Verification | `src/brakedisc/verification.py`, tests | Four analytical benchmarks and three-mesh sensitivity study |

## Suggested submission contents

- GitHub repository URL and README.
- Generated or committed example HTML report and plots.
- The three STEP models and SVG drawings.
- Verification results and convergence plot.
- Link to a successful Actions run and its downloadable artifact.

Complete solver files are generated on demand and uploaded as artifacts. The committed examples keep the repository manageable while retaining the numeric evidence and viewable results.

The implementation performs sequential thermal-to-structural screening using averaged heating and an idealized mount. It does not claim physical testing or a production-qualified brake design.
