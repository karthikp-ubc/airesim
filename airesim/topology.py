"""Rack-topology assignment for hierarchical cluster modeling.

Optional layer on top of the flat working/spare pool model.  When enabled
(``Params.enable_topology``), each server is tagged with a ``rack_id`` so that
host-selection policies can reason about network locality — e.g. packing a
job into as few racks as possible.  This module only assigns the topology;
it does not affect failure timing, repair, or pool bookkeeping.
"""

from __future__ import annotations

from airesim.server import Server


def assign_racks(servers: list[Server], rack_size: int) -> None:
    """Assign a ``rack_id`` to each server in place, ``rack_size`` per rack.

    Servers are assigned in list order: the first ``rack_size`` servers get
    rack 0, the next ``rack_size`` get rack 1, and so on (the last rack may
    be partially filled if ``len(servers)`` isn't a multiple of ``rack_size``).
    """
    for i, s in enumerate(servers):
        s.rack_id = i // rack_size
