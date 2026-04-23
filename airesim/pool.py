"""Pool manager — working pool and spare pool bookkeeping.

Tracks which servers are in each pool and handles movement between them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from airesim.server import Server, ServerState

if TYPE_CHECKING:
    pass


class PoolManager:
    """Manages the working pool and spare pool of servers."""

    def __init__(self):
        self.working_pool: list[Server] = []
        self.spare_pool: list[Server] = []
        self.retired: list[Server] = []

        # Counters
        self.preemption_count = 0

    # ── Initialization ───────────────────────────────────────────────────

    def init_pools(self, all_servers: list[Server], working_size: int, spare_size: int) -> None:
        """Partition servers into working and spare pools at simulation start."""
        for s in all_servers[:working_size]:
            s.state = ServerState.IDLE
            self.working_pool.append(s)
        for s in all_servers[working_size : working_size + spare_size]:
            s.move_to_spare()
            self.spare_pool.append(s)

    # ── Queries ──────────────────────────────────────────────────────────

    @property
    def available_in_working(self) -> list[Server]:
        """Servers in the working pool that are idle and can be assigned."""
        return [s for s in self.working_pool if s.state == ServerState.IDLE]

    @property
    def working_pool_active(self) -> int:
        """Number of non-retired servers in working pool."""
        return sum(1 for s in self.working_pool if s.state != ServerState.RETIRED)

    # ── Movement ─────────────────────────────────────────────────────────

    def remove_from_working(self, server: Server) -> None:
        """Remove a server from the working pool (e.g., sent to repair)."""
        if server in self.working_pool:
            self.working_pool.remove(server)

    def return_to_working(self, server: Server) -> None:
        """Return a repaired server to the working pool."""
        server.state = ServerState.IDLE
        if server not in self.working_pool:
            self.working_pool.append(server)

    def move_spare_to_working(self) -> Server | None:
        """Move one server from spare pool to working pool.

        Returns the server moved, or None if spare pool is empty.
        """
        if not self.spare_pool:
            return None
        server = self.spare_pool.pop(0)
        server.return_from_spare()
        self.working_pool.append(server)
        self.preemption_count += 1
        return server

    def return_to_spare(self, server: Server) -> None:
        """Return a server from working pool back to spare pool."""
        if server in self.working_pool:
            self.working_pool.remove(server)
        server.move_to_spare()
        self.spare_pool.append(server)

    def retire_server(self, server: Server) -> None:
        """Permanently remove a server from the cluster."""
        server.retire()
        if server in self.working_pool:
            self.working_pool.remove(server)
        if server in self.spare_pool:
            self.spare_pool.remove(server)
        self.retired.append(server)

    def __repr__(self):
        """Return a concise string showing pool sizes."""
        return (
            f"PoolManager(working={len(self.working_pool)}, "
            f"spare={len(self.spare_pool)}, "
            f"retired={len(self.retired)})"
        )
