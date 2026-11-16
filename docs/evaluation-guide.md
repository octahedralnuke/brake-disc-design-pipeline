# Evaluation and demonstration guide

## Before the evaluation

Install dependencies using the README, then run `brakedisc doctor` and `pytest -q`. Generate a fresh study with `brakedisc run`. Keep the report open and download a successful GitHub Actions artifact as a second reproducibility example. Precomputed examples are supplied so a discussion does not depend on waiting for FEA.

## Five-minute demonstration

1. **Inputs and sizing:** show `configs/kart.json`, then run `brakedisc size`. Explain why wheel radius, brake share and pad friction are needed beyond mass, speed and deceleration. Identify the 176.4 N·m torque and 30.625 kJ heat input.
2. **Geometry:** show a generated `drawing.svg` and open `disc.step` in a CAD viewer. Compare the baseline, lightweight and drilled parameters.
3. **Analysis:** open the HTML report and explain the two structural cases and transient temperature history. Show the mass–temperature–stress chart.
4. **Verification:** show `docs/verification.md`, the analytical benchmark output and convergence plot. Explain reaction-torque and energy checks.
5. **Automation:** show a successful GitHub Actions run and its artifact. Run `python scripts/assert_gate_failure.py results/summary.json` to demonstrate rejection. Show the supplied thin-disc example to connect failure to an actual geometry change.

## Useful answers to technical questions

**Why is the thermal peak above the analytical temperature estimate?**

The energy balance predicts the mean rise of the whole disc. Heat initially enters the swept faces, so the distribution is nonuniform and its local peak exceeds the volume mean.

**Why run both cold and hot structural cases?**

Braking torque and differential expansion produce different stress contributions. The reported screening result envelopes cold torque and the hottest thermal snapshot with full torque.

**How is the pad force defined?**

The output reports both per-pad normal force and the sum across both faces. Torque equals pad friction times the summed normal force times effective radius.

**What exactly fails the build?**

An exceeded stress/temperature criterion, a numerical consistency failure, invalid geometry, unavailable solver, timeout, missing output or incomplete solver result produces a nonzero status. The workflow uploads available diagnostic outputs even after failure.

**Does drilling necessarily improve cooling?**

No. Drilling reduces thermal mass and changes the heated and exposed areas. This model uses prescribed convection, so it cannot claim an aerodynamic cooling improvement from hole-induced flow.

The initial 7 mm drilled disc was rejected at 198.2 MPa (SF 1.26). Its outputs are preserved in `examples/rejected-drilled/`. The revised thickness is 9 mm, with the same loads, material and limits. To reproduce the original rejected design, run:

```bash
brakedisc run --config examples/rejected-drilled/input.json --variant drilled --out results-original-drilled
```

**Why are the bolt holes fixed?**

It is an explicit rigid-mount idealization for comparing geometries. Real bolt/hub compliance can change local stresses. Raw mount-region stress remains reported and conservatively controls the gate.

**What was verified versus validated?**

Analytical patches, conservation and mesh sensitivity provide numerical verification. There is no claimed correlation to physical dynamometer or track testing.

**What would come next?**

Measured temperature-dependent material properties; measured/calibrated heat partition and convection; hub/bolt compliance; moving pad contact; repeated-stop fatigue; and physical temperature/strain measurements.
