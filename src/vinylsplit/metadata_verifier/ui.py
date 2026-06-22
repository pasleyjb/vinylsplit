"""Rich UI components for metadata verification results."""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from vinylsplit.metadata_verifier.models import (
    MetadataConflict,
    MetadataEvidence,
    ReleaseEvidenceSet,
    VerificationReport,
)
from vinylsplit.ui.console import console
from vinylsplit.ui.theme import VINYLSPLIT_THEME


def display_verification_report(report: VerificationReport) -> None:
    """Display a verification report in Rich UI."""
    if report.release is None:
        console.print(
            Panel(
                "[warning]No metadata found[/warning]\n\n"
                "All evidence sources failed or returned no results.",
                title="Metadata Verification",
                style=THEME["warning_border"],
                expand=False,
            )
        )
        return

    # Build evidence summary
    evidence_items = []
    for evidence in report.release.evidence_list:
        status = "✓" if evidence.confidence >= 0.80 else "◐"
        evidence_items.append(
            f"{status} {evidence.source.value}: {evidence.confidence:.0%} confidence"
        )

    evidence_text = "\n".join(evidence_items)

    # Build main content
    content = (
        f"[bold]Artist:[/bold] {report.release.consensus_artist}\n"
        f"[bold]Album:[/bold] {report.release.consensus_album_title}\n"
        f"[bold]Year:[/bold] {report.release.consensus_year}\n"
        f"[bold]Tracks:[/bold] {report.release.consensus_track_count or 'Unknown'}\n"
        f"[bold]Overall Confidence:[/bold] {report.release.overall_confidence:.0%}\n"
        f"\n[dim]Evidence from {len(report.release.evidence_list)} sources:[/dim]\n"
        f"{evidence_text}"
    )

    # Determine styling based on recommendation severity
    border_style = {
        "clean": "green",
        "warning": "yellow",
        "conflict": "red",
    }[report.recommendation_severity]

    # Create panel with appropriate border color
    panel_border_color = {
        "clean": "green",
        "warning": "yellow",
        "conflict": "red",
    }.get(report.recommendation_severity, "blue")
    
    console.print(
        Panel(
            content,
            title="Metadata Verification",
            border_style=panel_border_color,
            expand=False,
        )
    )

    # Display recommendation
    console.print(f"[info]INFO[/info] {report.recommendation}")

    # Display conflicts if present
    if report.conflicts:
        display_conflicts(report.conflicts)


def display_conflicts(conflicts: list[MetadataConflict]) -> None:
    """Display metadata conflicts in a table."""
    if not conflicts:
        return

    table = Table(title="Metadata Conflicts", expand=False)
    table.add_column("Field", style="cyan")
    table.add_column("Values", style="yellow")
    table.add_column("Severity", style="red")

    for conflict in conflicts:
        # Format conflicting claims
        claims_text = "\n".join(
            f"• {source.value}: {value}" for source, value in conflict.claims.items()
        )

        severity_color = {
            "low": "dim",
            "medium": "yellow",
            "high": "red",
        }[conflict.severity]

        table.add_row(conflict.field, claims_text, f"[{severity_color}]{conflict.severity}[/{severity_color}]")

    console.print(Panel(table, expand=False))


def display_evidence_summary(evidence_set: ReleaseEvidenceSet) -> None:
    """Display a summary of gathered evidence."""
    table = Table(title="Evidence Summary", expand=False)
    table.add_column("Source", style="cyan")
    table.add_column("Artist", style="green")
    table.add_column("Album", style="green")
    table.add_column("Year", style="green")
    table.add_column("Confidence", style="yellow")

    for evidence in evidence_set.evidence_list:
        confidence_text = f"{evidence.confidence:.0%}"
        if evidence.confidence >= 0.80:
            confidence_style = "[green]" + confidence_text + "[/green]"
        elif evidence.confidence >= 0.60:
            confidence_style = "[yellow]" + confidence_text + "[/yellow]"
        else:
            confidence_style = "[red]" + confidence_text + "[/red]"

        table.add_row(
            evidence.source.value,
            evidence.artist or "—",
            evidence.album_title or "—",
            evidence.year or "—",
            confidence_style,
        )

    console.print(Panel(table, expand=False))


def display_agreement_scores(evidence_set: ReleaseEvidenceSet) -> None:
    """Display field agreement scores."""
    scores = [
        ("Artist", evidence_set.artist_agreement),
        ("Album Title", evidence_set.album_title_agreement),
        ("Year", evidence_set.year_agreement),
        ("Track Count", evidence_set.track_count_agreement),
    ]

    lines = ["[bold]Field Agreement Scores:[/bold]"]
    for field, score in scores:
        bar_length = int(score * 20)
        bar = "█" * bar_length + "░" * (20 - bar_length)

        # Color based on agreement
        if score >= 0.90:
            color = "green"
        elif score >= 0.70:
            color = "yellow"
        else:
            color = "red"

        lines.append(f"  {field:15} [{color}]{bar}[/{color}] {score:.0%}")

    console.print("\n".join(lines))


def confirmation_prompt(
    message: str,
    default_yes: bool = True,
) -> bool:
    """Prompt user for yes/no confirmation."""
    from rich.prompt import Confirm

    return Confirm.ask(message, default=default_yes)
