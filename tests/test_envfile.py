from cherve import envfile


def test_select_env_template_prefers_prod(tmp_path):
    (tmp_path / ".env.example").write_text("EXAMPLE=1\n")
    (tmp_path / ".env.production").write_text("PROD=1\n")
    (tmp_path / ".env.prod").write_text("PROD=2\n")

    selected = envfile.select_env_template(tmp_path)
    assert selected is not None
    assert selected.name == ".env.prod"

    (tmp_path / ".env.prod").unlink()
    selected = envfile.select_env_template(tmp_path)
    assert selected is not None
    assert selected.name == ".env.production"


def test_update_env_file_preserves_unmanaged(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# comment\n"
        "APP_ENV=local\n"
        "CUSTOM=keep\n"
    )
    envfile.update_env_file(env_path, {"APP_ENV": "production", "DB_HOST": "127.0.0.1"})
    content = env_path.read_text()

    assert "APP_ENV=production" in content
    assert "DB_HOST=127.0.0.1" in content
    assert "CUSTOM=keep" in content


def test_has_env_key(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("APP_KEY=base64:abc\n")
    assert envfile.has_env_key(env_path, "APP_KEY") is True
    env_path.write_text("APP_KEY=\n")
    assert envfile.has_env_key(env_path, "APP_KEY") is False
