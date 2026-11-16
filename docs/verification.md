# Numerical verification

## Analytical benchmarks

Run `brakedisc verify` to execute the four benchmarks with the installed CalculiX binary. They are also part of the integration tests. Captured benchmark results are in `examples/verification/verification.json`.

| Check | Closed-form target | Relative error in reference run | Acceptance |
|---|---|---:|---:|
| Uniaxial stress patch | `sigma_x = E epsilon`, other stresses zero | 1.40 × 10⁻¹⁶ | < 10⁻⁵ |
| Free thermal expansion | `u = alpha DeltaT x`, negligible stress | 7.31 × 10⁻¹⁵ | < 10⁻⁵; stress < 100 Pa |
| Uniform adiabatic heating | `DeltaT = qv t / (rho cp)` | 2.08 × 10⁻⁶ | < 10⁻⁴ |
| Fourier conduction patch | `q = -k grad(T)` | 0 at printed precision | < 10⁻⁵ |

The stress and conduction patches impose affine fields on a quadratic reference tetrahedron and check integration-point results. The expansion case uses minimal rigid-body restraints. Heating uses consistent volumetric-source nodal integrals, including quadratic corner weights. These checks exercise actual solver decks, element ordering, material cards, units, output parsing and thermal-to-mechanical strain.

These small verification problems do not establish experimental accuracy for a real brake disc.

## Test coverage

The reference test suite has **41 passing tests**. It covers hand-calculated braking loads, energy scaling, heat partition, CAD feature validation, quadratic integration, von Mises stress states, parser corruption, missing/duplicate nodes, unavailable solvers, safe output replacement, failed acceptance criteria, real drilled-disc CAD/mesh selection and the analytical solver benchmarks. Ruff and Python byte-compilation checks also pass.

## Mesh sensitivity

The baseline is analysed at target mesh sizes of 6, 5 and 4 mm. The two finest meshes must differ by less than 2% in peak temperature **rise**, 5% in swept-region hot stress and 5% in maximum displacement. Every mesh must also pass the normal study checks.

Global peak stress is retained in the table and remains the design gate's stress metric. The swept-region metric separately avoids confusing sensitivity of the idealized mount with the friction-ring result. This is a sensitivity study, not a formal error bound or proof of convergence to a physical solution.

<!-- CONVERGENCE_RESULTS_START -->
Detailed numeric results are recorded in `examples/convergence/convergence.json`.
<!-- CONVERGENCE_RESULTS_END -->

## Conservation and completeness

- CAD volume is independently checked against the analytical annulus/hole volume.
- Integrated curved-mesh volume must match CAD within 1%.
- The mount's reaction moment must match applied torque within 1%.
- Maximum thermal energy residual must remain below 2% of analytical continuous-time stop heat.
- All nodes, all stress integration points, positive sampled Jacobians and the thermal final time are checked.
- Solver return status, completion marker and error messages are checked before accepting output.

The source is not renormalized to conceal time-integration error. The energy CSV retains input heat, internal energy, convection and residual terms for independent inspection.

## Rejection evidence

`configs/rejected.json` makes the otherwise identical disc 2 mm thick. This is analysed separately from the normal passing variants. Its committed numeric results show the actual failed criteria. The CI demonstration also checks that an impossible safety-factor requirement returns the documented rejection status.

## Reference environment

Python 3.11.14, CadQuery 2.6.1, Gmsh 4.14.1, CalculiX 2.21, NumPy 2.2.6, Matplotlib 3.10.3 and meshio 5.3.5 on Linux. Exact transitive dependencies are pinned with hashes in `requirements.lock`.
