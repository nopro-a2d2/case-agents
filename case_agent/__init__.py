"""Case-Agent: lawyer-facing DeepAgent on Vertex AI."""

from ._env import load_env

# Best-effort: pick up a .env on import so `python -c "from case_agent..."` and
# `uv run case-agent ...` both see GCP_PROJECT/VERTEX_LOCATION/etc. without the
# user having to source anything. Real env vars always win (override=False).
load_env()

__version__ = "0.1.0"
__all__ = ["__version__", "load_env"]
