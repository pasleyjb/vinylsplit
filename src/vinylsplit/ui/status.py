from .console import console


def info(message: str):
    console.print(f"[info]ℹ {message}[/]")


def success(message: str):
    console.print(f"[success]✓ {message}[/]")


def warning(message: str):
    console.print(f"[warning]⚠ {message}[/]")


def error(message: str):
    console.print(f"[error]✗ {message}[/]")