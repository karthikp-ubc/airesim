"""Tests for rack-topology assignment and the PackedByRackFirst policy."""

from __future__ import annotations

import os
import random
import sys

import pytest
import simpy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.params import Params
from airesim.scheduling_policies import PackedByRackFirst
from airesim.server import Server
from airesim.simulator import Simulator
from airesim.topology import assign_racks

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_server(server_id: int = 0, is_bad: bool = False) -> Server:
    env = simpy.Environment()
    return Server(
        server_id=server_id,
        env=env,
        is_bad=is_bad,
        random_failure_rate=0.0,
        systematic_failure_rate=0.0,
    )


def _rng() -> random.Random:
    return random.Random(42)


# ── assign_racks ──────────────────────────────────────────────────────────────

class TestAssignRacks:

    def test_default_rack_id_is_none(self):
        """A freshly-constructed server has no rack assigned."""
        s = make_server(0)
        assert s.rack_id is None

    def test_assigns_contiguous_blocks(self):
        """First rack_size servers get rack 0, next rack_size get rack 1, etc."""
        servers = [make_server(i) for i in range(10)]
        assign_racks(servers, rack_size=4)
        assert [s.rack_id for s in servers] == [0, 0, 0, 0, 1, 1, 1, 1, 2, 2]

    def test_partial_last_rack(self):
        """A non-multiple server count leaves the last rack partially filled."""
        servers = [make_server(i) for i in range(5)]
        assign_racks(servers, rack_size=3)
        assert [s.rack_id for s in servers] == [0, 0, 0, 1, 1]


# ── Params validation ─────────────────────────────────────────────────────────

class TestParamsValidation:

    def test_default_rack_size_is_valid(self):
        Params().validate()  # should not raise

    def test_rejects_non_positive_rack_size(self):
        with pytest.raises(ValueError, match="rack_size"):
            Params(rack_size=0).validate()
        with pytest.raises(ValueError, match="rack_size"):
            Params(rack_size=-1).validate()


# ── PackedByRackFirst unit tests ──────────────────────────────────────────────

class TestPackedByRackFirst:

    def test_packs_into_fewest_racks(self):
        """Prefers filling from the largest rack(s) over spreading across many."""
        policy = PackedByRackFirst()
        big_rack = [make_server(i) for i in range(6)]
        for s in big_rack:
            s.rack_id = 0
        small_racks = []
        for rack in range(1, 5):
            s = make_server(10 + rack)
            s.rack_id = rack
            small_racks.append(s)

        available = big_rack + small_racks
        selected = policy.select(available, job_size=4, warm_standbys=0, rng=_rng())

        assert len(selected) == 4
        assert all(s.rack_id == 0 for s in selected)

    def test_spans_multiple_racks_when_needed(self):
        """Falls back to additional racks once the largest rack is exhausted."""
        policy = PackedByRackFirst()
        rack0 = [make_server(i) for i in range(3)]
        for s in rack0:
            s.rack_id = 0
        rack1 = [make_server(10 + i) for i in range(3)]
        for s in rack1:
            s.rack_id = 1

        selected = policy.select(rack0 + rack1, job_size=5, warm_standbys=0, rng=_rng())
        assert len(selected) == 5
        racks_used = {s.rack_id for s in selected}
        assert racks_used == {0, 1}

    def test_returns_fewer_when_pool_too_small(self):
        policy = PackedByRackFirst()
        servers = [make_server(i) for i in range(3)]
        for s in servers:
            s.rack_id = 0
        selected = policy.select(servers, job_size=5, warm_standbys=2, rng=_rng())
        assert len(selected) == 3

    def test_untagged_servers_treated_as_single_rack(self):
        """rack_id=None (topology disabled) still yields a valid selection."""
        policy = PackedByRackFirst()
        servers = [make_server(i) for i in range(5)]  # rack_id left as None
        selected = policy.select(servers, job_size=3, warm_standbys=1, rng=_rng())
        assert len(selected) == 4

    def test_includes_warm_standbys(self):
        policy = PackedByRackFirst()
        servers = [make_server(i) for i in range(10)]
        for i, s in enumerate(servers):
            s.rack_id = i // 3
        selected = policy.select(servers, job_size=4, warm_standbys=2, rng=_rng())
        assert len(selected) == 6


# ── Integration: Simulator + enable_topology ──────────────────────────────────

class TestTopologyIntegration:

    def _base_params(self, **overrides) -> Params:
        defaults = dict(
            job_size=8,
            warm_standbys=2,
            working_pool_size=20,
            spare_pool_size=5,
            job_length=2 * 24 * 60,
            random_failure_rate=0.02 / (24 * 60),
            systematic_failure_rate_multiplier=5.0,
            systematic_failure_fraction=0.10,
            recovery_time=10,
            host_selection_time=1,
            preemption_wait_time=5,
            auto_repair_time=30,
            manual_repair_time=120,
            prob_auto_to_manual=0.5,
            auto_repair_fail_prob=0.3,
            manual_repair_fail_prob=0.3,
            seed=0,
            num_replications=1,
        )
        defaults.update(overrides)
        return Params(**defaults)

    def test_disabled_by_default_leaves_rack_id_none(self):
        """enable_topology defaults to False — no rack assignment happens."""
        observed = {}

        class InspectingSim(Simulator):
            def _main_loop(self, env, rng, p, coordinator, scheduler,
                           repair_shop, pool_mgr, stats, all_servers):
                observed["all_servers"] = all_servers
                yield from super()._main_loop(
                    env, rng, p, coordinator, scheduler, repair_shop,
                    pool_mgr, stats, all_servers,
                )

        params = self._base_params()
        assert params.enable_topology is False
        sim = InspectingSim(params=params, seed=1)
        sim.run()

        assert all(s.rack_id is None for s in observed["all_servers"])

    def test_enabled_assigns_racks_and_completes(self):
        """enable_topology=True assigns rack_id and the run still completes."""
        observed = {}

        class InspectingSim(Simulator):
            def _main_loop(self, env, rng, p, coordinator, scheduler,
                           repair_shop, pool_mgr, stats, all_servers):
                observed["all_servers"] = all_servers
                yield from super()._main_loop(
                    env, rng, p, coordinator, scheduler, repair_shop,
                    pool_mgr, stats, all_servers,
                )

        params = self._base_params(enable_topology=True, rack_size=5)
        sim = InspectingSim(params=params, seed=1)
        result = sim.run()

        assert result.total_training_time > 0
        assert not result.cluster_depleted
        assert all(s.rack_id is not None for s in observed["all_servers"])
        # 25 total servers (20 working + 5 spare) / rack_size=5 → racks 0..4
        assert {s.rack_id for s in observed["all_servers"]} == {0, 1, 2, 3, 4}

    def test_packed_by_rack_first_completes_with_topology_enabled(self):
        """PackedByRackFirst works end-to-end when topology is enabled."""
        params = self._base_params(enable_topology=True, rack_size=5)
        sim = Simulator(
            params=params,
            host_selection_policy=PackedByRackFirst(),
            seed=1,
        )
        result = sim.run()
        assert result.total_training_time > 0
        assert not result.cluster_depleted
