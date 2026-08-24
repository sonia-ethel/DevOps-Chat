from pathlib import Path
from dotenv import load_dotenv


def load_app_env() -> None:
    """Load environment variables from the repository root first.

    The official CodeCamp configuration file is the root `.env`.
    `devops_api/.env` is kept only as a legacy fallback and does not override
    values already loaded from the root file or the process environment.
    """
    api_dir = Path(__file__).resolve().parents[1]
    repo_root = api_dir.parent

    load_dotenv(repo_root / ".env", override=False)
    load_dotenv(api_dir / ".env", override=False)
