import pytest

from cherve import paths


@pytest.fixture
def temp_paths(tmp_path, monkeypatch):
    etc_dir = tmp_path / "etc" / "cherve"
    sites_dir = etc_dir / "sites.d"
    www_root = tmp_path / "var" / "www"
    home_root = tmp_path / "home"
    nginx_av = tmp_path / "nginx" / "sites-available"
    nginx_en = tmp_path / "nginx" / "sites-enabled"

    monkeypatch.setattr(paths, "ETC_DIR", etc_dir)
    monkeypatch.setattr(paths, "SITES_DIR", sites_dir)
    monkeypatch.setattr(paths, "SERVER_CONFIG_PATH", etc_dir / "server.toml")
    monkeypatch.setattr(paths, "WWW_ROOT", www_root)
    monkeypatch.setattr(paths, "HOME_ROOT", home_root)
    monkeypatch.setattr(paths, "NGINX_SITES_AVAILABLE", nginx_av)
    monkeypatch.setattr(paths, "NGINX_SITES_ENABLED", nginx_en)

    etc_dir.mkdir(parents=True, exist_ok=True)
    sites_dir.mkdir(parents=True, exist_ok=True)
    www_root.mkdir(parents=True, exist_ok=True)
    home_root.mkdir(parents=True, exist_ok=True)
    nginx_av.mkdir(parents=True, exist_ok=True)
    nginx_en.mkdir(parents=True, exist_ok=True)

    return {
        "etc_dir": etc_dir,
        "sites_dir": sites_dir,
        "www_root": www_root,
        "home_root": home_root,
        "nginx_av": nginx_av,
        "nginx_en": nginx_en,
    }
