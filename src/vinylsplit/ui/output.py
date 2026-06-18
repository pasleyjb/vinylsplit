from .console import console


def info(message: str) -> None:
    console.print(f"[info]ℹ[/] {message}")


def success(message: str) -> None:
    console.print(f"[success]✓[/] {message}")


def warning(message: str) -> None:
    console.print(f"[warning]⚠[/] {message}")


def error(message: str) -> None:
    console.print(f"[error]✗[/] {message}")