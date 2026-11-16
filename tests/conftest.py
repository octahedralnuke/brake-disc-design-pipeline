from pathlib import Path
import pytest
from brakedisc.model import Config


@pytest.fixture
def config_path():
    return Path(__file__).resolve().parents[1] / "configs/kart.json"


@pytest.fixture
def config(config_path):
    return Config.load(config_path)
