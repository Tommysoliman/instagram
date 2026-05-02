"""
Run a single meme generation cycle:
  1. Scout trends
  2. Generate ideas
  3. (Pause) you review and approve
  4. Write captions for approved ideas
  5. (Optional) Post to Instagram

Usage:
    python main.py
    python main.py --count 8
"""
from __future__ import annotations

import argparse

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import load_config
from memory import MemeMemory
from graph import build_graph
from agents import image_generator

console = Console()


def review_ideas(ideas) -> list[int]:
    """
    Show ideas in a table, ask user which to approve.
    Returns the list of approved indices.
    """
    if not ideas:
        console.print("[yellow]No ideas to review.[/yellow]")
        return []

    table = Table(title="🎨 Generated Meme Ideas", show_lines=True)
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Concept", style="white")
    table.add_column("Format", style="magenta")
    table.add_column("Why it works", style="dim")
    table.add_column("⚠️", style="yellow")

    for i, idea in enumerate(ideas, 1):
        flags = ", ".join(idea.risk_flags) if idea.risk_flags else "—"
        table.add_row(str(i), idea.concept, idea.format, idea.why_it_works, flags)

    console.print(table)
    console.print(
        "\n[bold]Which ideas do you want to keep?[/bold] "
        "Enter numbers (e.g. [cyan]1,3,5[/cyan]), [cyan]all[/cyan], or [cyan]none[/cyan]: ",
        end="",
    )
    raw = input().strip().lower()

    if raw in ("none", "n", ""):
        return []
    if raw in ("all", "a"):
        return list(range(len(ideas)))

    keep = []
    for token in raw.replace(" ", "").split(","):
        if token.isdigit():
            idx = int(token) - 1
            if 0 <= idx < len(ideas):
                keep.append(idx)
    return keep


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=5, help="how many ideas to generate")
    args = parser.parse_args()

    cfg = load_config()
    mem = MemeMemory(cfg)
    graph = build_graph(cfg, mem, n_ideas=args.count)

    config = {"configurable": {"thread_id": "single-run"}}

    console.print(Panel.fit(
        f"[bold]Niche:[/bold] {cfg.niche}\n[bold]Voice:[/bold] {cfg.voice}",
        title="Meme Agent",
        border_style="cyan",
    ))

    # ---- Run until interruption (human approval) ----
    state = graph.invoke({}, config=config)

    ideas = state.get("ideas", [])
    keep_idxs = review_ideas(ideas)
    approved = [ideas[i] for i in keep_idxs]

    if not approved:
        console.print("\n[yellow]No ideas approved. Exiting.[/yellow]")
        return

    # Mark approved in memory (status update for analytics later)
    # Note: we'd need to track idea IDs back to memory; left as exercise.

    # ---- Resume the graph with approved ideas ----
    state = graph.invoke({"approved_ideas": approved}, config=config)

    # ---- Render captions ----
    captions = state.get("captions", [])
    console.print(f"\n[bold green]✅ {len(captions)} ready-to-post package(s):[/bold green]\n")

    for i, (idea, cap) in enumerate(captions, 1):
        body = (
            f"[bold]{idea.concept}[/bold]\n"
            f"[dim]Format: {idea.format}[/dim]\n\n"
            f"[bold cyan]Caption:[/bold cyan]\n{cap.caption}\n\n"
            f"[bold cyan]Hashtags:[/bold cyan]\n{' '.join('#' + h for h in cap.hashtags)}\n\n"
            f"[bold cyan]First comment:[/bold cyan]\n{cap.first_comment}"
        )
        console.print(Panel(body, title=f"Post #{i}", border_style="green"))

    # ---- Generate images with DALL-E ----
    console.print("\n[bold]Generating images with DALL-E 3...[/bold]")
    image_paths: list[str] = []
    for i, (idea, _) in enumerate(captions, 1):
        console.print(f"  🎨 Image {i}/{len(captions)}: {idea.concept[:50]}...")
        try:
            path = image_generator(cfg, idea)
            image_paths.append(path)
            console.print(f"  ✅ Saved → {path}")
        except Exception as e:
            console.print(f"  [red]Failed: {e}[/red]")
            image_paths.append("")

    # ---- Post to Instagram ----
    if not (cfg.instagram_username and cfg.instagram_password):
        console.print("\n[dim]No Instagram credentials set. Skipping posting.[/dim]")
        return

    from poster import login, post_photo

    console.print("\n[dim]Logging into Instagram...[/dim]")
    try:
        cl = login(cfg.instagram_username, cfg.instagram_password)
        console.print("[green]Logged in.[/green]\n")
    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        return

    for i, ((idea, cap), img_path) in enumerate(zip(captions, image_paths), 1):
        if not img_path:
            console.print(f"[yellow]Post #{i} skipped (no image).[/yellow]")
            continue
        full_caption = cap.caption + "\n\n" + " ".join(f"#{h}" for h in cap.hashtags)
        try:
            media_id = post_photo(cl, img_path, full_caption, cap.first_comment)
            console.print(f"[green]✅ Post #{i} live! Media ID: {media_id}[/green]")
        except Exception as e:
            console.print(f"[red]Post #{i} failed: {e}[/red]")


if __name__ == "__main__":
    main()
