from pathlib import Path

def get_project_root(start_path: str = __file__) -> Path:
    return Path(start_path).resolve().parent.parent

def get_apps_dir() -> Path:
    return get_project_root() / "apps"