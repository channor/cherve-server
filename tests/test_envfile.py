from pathlib import Path

from cherve import envfile


def test_select_template_prefers_prod(tmp_path: Path) -> None:
    (tmp_path / ".env.example").write_text("EXAMPLE=1\n", encoding="utf-8")
    prod = tmp_path / ".env.prod"
    prod.write_text("PROD=1\n", encoding="utf-8")
    assert envfile.select_template(tmp_path) == prod


def test_update_env_file_preserves_comments(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# comment\nAPP_ENV=local\nUNRELATED=keep\n",
        encoding="utf-8",
    )
    envfile.update_env_file(env_path, {"APP_ENV": "production", "APP_DEBUG": "false"})
    text = env_path.read_text(encoding="utf-8")
    assert "# comment" in text
    assert "APP_ENV=production" in text
    assert "APP_DEBUG=false" in text
    assert "UNRELATED=keep" in text
