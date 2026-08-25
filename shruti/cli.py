import asyncio
import typer
from shruti.db import get_pool, apply_migrations
from shruti.vault.atlas_store import check_provenance_invariant

app = typer.Typer()


@app.command()
def migrate():
    """Apply all pending SQL migrations in infra/migrations/."""
    async def _run():
        pool = await get_pool()
        await apply_migrations(pool)
        await pool.close()
    asyncio.run(_run())
    typer.echo("migrations applied")


@app.command(name="provenance-check")
def provenance_check():
    """Run the E4 provenance invariant against the live database and exit
    non-zero if any Concept/Edge/Misconception row lacks a BeatRef."""
    async def _run():
        pool = await get_pool()
        violations = await check_provenance_invariant(pool)
        await pool.close()
        return violations
    violations = asyncio.run(_run())
    if violations:
        typer.echo(f"{len(violations)} violation(s): {violations}")
        raise typer.Exit(code=1)
    typer.echo("provenance invariant holds")


if __name__ == "__main__":
    app()
