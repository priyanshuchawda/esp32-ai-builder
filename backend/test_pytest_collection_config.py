from pathlib import Path


def _config_value(lines, key):
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key} ="):
            return stripped.split("=", 1)[1].strip()
    return ""


def test_root_pytest_config_scopes_collection_to_active_backend():
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "pytest.ini"

    assert config_path.exists()

    lines = config_path.read_text(encoding="utf-8").splitlines()
    testpaths = _config_value(lines, "testpaths")
    norecursedirs = _config_value(lines, "norecursedirs")

    assert testpaths == "backend"
    for ignored_tree in (
        "RuView",
        "esp32-csi-gemma-filter",
        "wifi-densepose-pretrained",
        ".pio",
    ):
        assert ignored_tree in norecursedirs
