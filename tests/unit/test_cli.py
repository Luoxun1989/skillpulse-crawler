from click.testing import CliRunner
from skillpulse_crawler.cli import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "validate-config" in result.output
    assert "dry-run" in result.output
    assert "run" in result.output