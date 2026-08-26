from typer.testing import CliRunner
from shruti.cli import app

runner = CliRunner()


def test_cli_exposes_migrate_and_provenance_check_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "migrate" in result.output
    assert "provenance-check" in result.output
