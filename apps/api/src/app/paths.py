from pathlib import Path


def repo_root() -> Path:
    """Repository root (``apps/api/src/app/paths.py`` is four levels below it)."""
    return Path(__file__).resolve().parents[4]


def resolve(path: str) -> Path:
    """Resolve a configured path; relative paths are taken from the repository root."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root() / candidate
