import asyncio
import os
import subprocess
import uuid
from pathlib import Path

import typer
from shruti.db import get_pool, apply_migrations
from shruti.vault.atlas_store import check_provenance_invariant
from shruti.vault import mirror

app = typer.Typer()


def _download_youtube(url: str, out_dir: str = ".local/videos") -> str:
    """Download via the yt-dlp CLI binary (installed separately, e.g.
    `uv tool install yt-dlp` — not a project dependency) into out_dir,
    merged to mp4 at up to 720p. Returns the local file path."""
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    video_id = uuid.uuid4().hex[:10]
    out_template = str(Path(out_dir) / f"{video_id}.%(ext)s")
    result = subprocess.run(
        ["yt-dlp", "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
         "--merge-output-format", "mp4", "-o", out_template, url],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        typer.echo(result.stderr[-2000:])
        raise typer.Exit(code=1)
    matches = sorted(Path(out_dir).glob(f"{video_id}.*"))
    if not matches:
        typer.echo("yt-dlp reported success but no output file was found")
        raise typer.Exit(code=1)
    return str(matches[0])


@app.command()
def ingest(
    url: str = typer.Option(None, "--url", help="YouTube URL (skips the interactive prompt if given)"),
    subject: str = typer.Option(None, "--subject"),
    grade: int = typer.Option(None, "--grade"),
    chapter: str = typer.Option(None, "--chapter"),
):
    """Prompt for a YouTube URL, download it, and run the full Shruti
    pipeline against it — the whole thing, start to finish, from the
    terminal. See run_ingest's own output for per-stage progress; a full
    artifact trace is written to .local/runs/<run_id>/ and a cross-modal
    sync view is available afterward via `shruti timeline <recording_id>`.
    """
    if not url:
        url = typer.prompt("YouTube URL")

    typer.echo(f"Downloading {url} ...")
    video_path = _download_youtube(url)
    typer.echo(f"Downloaded to {video_path}")

    from google import genai
    vertex_key = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN")
    if not vertex_key and not os.environ.get("GOOGLE_API_KEY"):
        typer.echo("Neither GOOGLE_OAUTH_ACCESS_TOKEN nor GOOGLE_API_KEY is set — "
                   "add one to .env and run with `uv run --env-file .env shruti ingest`.")
        raise typer.Exit(code=1)
    client = genai.Client(vertexai=True, api_key=vertex_key) if vertex_key else genai.Client()

    from shruti.ingest import run_ingest
    asyncio.run(run_ingest(video_path, client, subject=subject, grade=grade, chapter=chapter))


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


@app.command()
def timeline(recording_id: str):
    """The v_timeline debug view for one recording — read it end to end,
    it should read like lecture notes. [board] = a board state was live,
    [gesture] = a deixis event fired in that beat's span."""
    con = mirror.connect()
    rows = con.execute(
        "SELECT tc, kind, signals, said, concepts FROM v_timeline WHERE recording_id=?",
        [recording_id],
    ).fetchall()
    if not rows:
        typer.echo(f"no beats found for recording_id={recording_id!r}")
        raise typer.Exit(code=1)
    for tc, kind, signals, said, concepts in rows:
        line = f"{tc}  {kind:8s} {signals:10s} {said}"
        if concepts:
            line += f"   [{concepts}]"
        typer.echo(line)


@app.command()
def boards(recording_id: str):
    """The v_board_states debug view — one row per recovered board state,
    with region/unreadable counts so you can see SLATE+GLYPH quality at a
    glance without opening every image."""
    con = mirror.connect()
    rows = con.execute(
        "SELECT idx, from_tc, to_tc, ended_by, ink_coverage, region_count, "
        "unreadable_count, composited_uri FROM v_board_states WHERE recording_id=?",
        [recording_id],
    ).fetchall()
    if not rows:
        typer.echo(f"no board states found for recording_id={recording_id!r}")
        raise typer.Exit(code=1)
    for idx, from_tc, to_tc, ended_by, ink, regions, unreadable, uri in rows:
        typer.echo(f"[{idx}] {from_tc}-{to_tc}  ended_by={ended_by}  ink={ink}  "
                   f"regions={regions} (unreadable={unreadable})  {uri}")


@app.command()
def concepts(recording_id: str):
    """The v_concepts debug view — every concept mined, in teaching order,
    with a misconception count."""
    con = mirror.connect()
    rows = con.execute(
        "SELECT canonical_name, first_taught_at_s, misconception_count "
        "FROM v_concepts c JOIN pg.public.beat_ref r ON r.subject_id = c.id "
        "JOIN pg.public.beat b ON b.id = r.beat_id WHERE b.recording_id=? "
        "GROUP BY canonical_name, first_taught_at_s, misconception_count",
        [recording_id],
    ).fetchall()
    if not rows:
        typer.echo(f"no concepts found for recording_id={recording_id!r}")
        raise typer.Exit(code=1)
    for name, at_s, misconceptions in sorted(rows, key=lambda r: r[1] or 0):
        tag = f" ({misconceptions} misconception(s))" if misconceptions else ""
        typer.echo(f"[{at_s:6.1f}s] {name}{tag}")


if __name__ == "__main__":
    app()
