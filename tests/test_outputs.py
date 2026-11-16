from dataclasses import asdict
import json
import numpy as np
import pytest
from brakedisc.cli import main
from brakedisc.pipeline import evaluate, output_directory
from brakedisc.solver import nodal, parse_dat


def sample(config):
    return {"schema_version": 1, "limits": asdict(config.limits), "errors": [], "results": [
        {"name": "example", "safety_factor": 3., "peak_temperature_c": 100.,
         "volume_error_fraction": 0.001, "energy_error_fraction": 0.01,
         "reaction_torque_error_fraction": 0.0001, "solver_completed": True}]}


def test_gate_pass_fail_and_override(tmp_path, config):
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(sample(config)))
    assert main(["check", str(path)]) == 0
    assert main(["check", str(path), "--min-safety-factor", "4"]) == 2
    assert main(["check", str(path), "--max-temperature", "50"]) == 2


@pytest.mark.parametrize("change", ["empty", "error", "nan", "missing", "negative"])
def test_gate_rejects_incomplete_or_invalid_data(tmp_path, config, change):
    study = sample(config)
    if change == "empty":
        study["results"] = []
    elif change == "error":
        study["errors"] = ["solver crashed"]
    elif change == "nan":
        study["results"][0]["safety_factor"] = float("nan")
    elif change == "missing":
        del study["results"][0]["energy_error_fraction"]
    else:
        study["results"][0]["volume_error_fraction"] = -0.1
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(study))
    assert main(["check", str(path)]) == 1


def test_solver_completion_is_mandatory(config):
    r = sample(config)["results"][0]
    r["solver_completed"] = False
    assert not all(evaluate(r, asdict(config.limits)).values())


def test_dat_parser_and_node_reordering(tmp_path):
    path = tmp_path / "job.dat"
    path.write_text("\n temperatures for set ALLN and time  1.0000000E+00\n\n 2 3.0D+01\n 1 2.5E+01\n")
    data = parse_dat(path)
    assert data["temperatures"][0][0] == 1
    assert nodal(data["temperatures"][0][1], 2, 1)[:, 0] == pytest.approx([25, 30])


@pytest.mark.parametrize("text", ["", " temperatures for set ALLN and time 1.0\n\n",
    " temperatures for set ALLN and time 1.0\n 1 ***********\n"])
def test_dat_parser_rejects_missing_results(tmp_path, text):
    path = tmp_path / "bad.dat"
    path.write_text(text)
    with pytest.raises(RuntimeError):
        parse_dat(path)


def test_missing_and_duplicate_nodes_rejected():
    for rows in (np.array([[1., 25.]]), np.array([[1., 25.], [1., 30.]]),
                 np.array([[1.5, 25.], [2.5, 30.]])):
        with pytest.raises(RuntimeError):
            nodal(rows, 2, 1)


def test_overwrite_cannot_delete_unrelated_directory(tmp_path):
    out = tmp_path / "unrelated"
    out.mkdir()
    (out / "keep.txt").write_text("keep me")
    with pytest.raises(ValueError):
        output_directory(out, True)
    assert (out / "keep.txt").read_text() == "keep me"


def test_missing_solver_fails(monkeypatch):
    from brakedisc.solver import find_ccx
    monkeypatch.setenv("CCX", "definitely-no-such-solver")
    with pytest.raises(RuntimeError):
        find_ccx()


@pytest.mark.parametrize("code,stdout,expected", [(201, "This is Version 2.21", 0),
    (0, "unexpected output", 1), (127, "", 1)])
def test_doctor_calculix_version_exit_convention(monkeypatch, code, stdout, expected):
    from types import SimpleNamespace
    import subprocess
    import brakedisc.cli
    import brakedisc.solver
    monkeypatch.setattr(brakedisc.cli.importlib, "import_module", lambda _: SimpleNamespace(__version__="test"))
    monkeypatch.setattr(brakedisc.solver, "find_ccx", lambda: "/fake/ccx")
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=code, stdout=stdout, stderr=""))
    assert main(["doctor"]) == expected
