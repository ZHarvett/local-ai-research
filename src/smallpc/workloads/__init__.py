"""WP8 workloads: real-source prompts of exact token length, Request A / B pairs and the manifest.

``python -m smallpc.workloads run build verify check`` (see ``__main__``). WP9 uses the interface
re-exported here; its documentation is in ``api``.
"""

from .api import CacheMiss, Workload, get_workload
from .recipe import depths_for_context, fits, plan_sweep, variant_for

__all__ = [
    "CacheMiss",
    "Workload",
    "depths_for_context",
    "fits",
    "get_workload",
    "plan_sweep",
    "variant_for",
]
