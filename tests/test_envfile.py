from pathlib import Path

from cherve import envfile


def test_select_env_template_order(tmp_path: Path) -> None:
    prod = tmp_path / ".env.prod"
    production = tmp_path / ".env.production"
    example = tmp_path / ".env.example"
    example.write_text("EXAMPLE=1\n")
    production.write_text("PRODUCTION=1\n")
    prod.write_text("PROD=1\n")

    selected = envfile.select_env_template(tmp_path)
    assert selected == prod


def test_update_env_contents_preserves_and_appends() -> None:
    contents = "# Comment\nFOO=bar\nexport APP_ENV=local\n"
    updates = {"APP_ENV": "production", "APP_DEBUG": "false"}
    updated = envfile.update_env_contents(contents, updates)

    assert "# Comment" in updated
    assert "FOO=bar" in updated
    assert "export APP_ENV=production" in updated
    assert "APP_DEBUG=false" in updated
    assert updated.endswith("\n")
