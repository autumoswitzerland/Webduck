"""Tests for webduck.config."""

from pathlib import Path

from webduck.config import AuthConfig, ServerConfig, WebDuckConfig, load_config, save_config


def test_default_config():
    cfg = WebDuckConfig()
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.port == 8998
    assert cfg.auth.jwt_algorithm == "HS256"
    assert cfg.logging.file.enabled is False
    assert cfg.logging.console.enabled is False


def test_load_nonexistent_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "missing.yaml")
    assert cfg.server.port == 8998


def test_save_and_load_roundtrip(tmp_path):
    cfg = WebDuckConfig(
        server=ServerConfig(port=12345, data_dir=Path("mydata")),
        auth=AuthConfig(jwt_secret="supersecret"),
    )
    path = tmp_path / "config.yaml"
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.server.port == 12345
    assert loaded.server.data_dir == Path("mydata")
    assert loaded.auth.jwt_secret == "supersecret"


def test_save_config_serializes_path(tmp_path):
    cfg = WebDuckConfig()
    path = tmp_path / "test.yaml"
    save_config(cfg, path)
    # YAML should contain a string, not a Path object
    content = path.read_text()
    assert "data_dir: data" in content
