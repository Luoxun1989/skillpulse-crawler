import click


@click.group()
@click.option("--sources-dir", default="./skillpulse_crawler/sources", type=click.Path(exists=False))
@click.pass_context
def cli(ctx, sources_dir):
    """skillpulse-crawler: weekly digest content harvester"""
    ctx.ensure_object(dict)
    ctx.obj["sources_dir"] = sources_dir


@cli.command("validate-config")
@click.pass_context
def validate_config(ctx):
    """Validate all YAML configs in sources dir"""
    from pathlib import Path
    from .config import load_all_sources
    sources_dir = Path(ctx.obj["sources_dir"])
    if not sources_dir.exists():
        click.echo(f"sources dir not found: {sources_dir}")
        raise SystemExit(1)
    sources = load_all_sources(sources_dir)
    click.echo(f"Loaded {len(sources)} sources:")
    for s in sources:
        click.echo(f"  - {s.id} [{s.section}]")


@cli.command("dry-run")
@click.option("--source", required=True)
@click.pass_context
def dry_run(ctx, source):
    """Run pipeline without persisting"""
    click.echo(f"[dry-run] would process {source} (not implemented yet)")


@cli.command("run")
@click.pass_context
def run(ctx):
    """Run full pipeline and persist"""
    click.echo("[run] not implemented yet")