# Verified example artifacts

These are captured outputs from real local CalculiX runs. `study/` combines independently completed variants at the same input configuration and 4 mm mesh target. Source hashes and commit references, where available, are retained per run. `convergence/` compares three mesh targets; `verification/` contains analytical benchmark decks and results; `rejected/` demonstrates a failed thin disc.

`rejected-drilled/` preserves the initial 7 mm drilled disc that failed the stress limit. Comparing it with the final 9 mm drilled disc documents the design revision and demonstrates that the acceptance checks reject an inadequate geometry.

The viewable reports, CAD exports, input decks, logs, VTU fields and numeric summaries are retained. Large native DAT/FRD/MSH files are regenerated with `brakedisc run` and are also available in the Actions artifact. Manifest hashes in each example folder cover the files actually included there.
