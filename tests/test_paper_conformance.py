"""Regression tests for the paper-conformance fixes (arXiv 2603.07041).

1. The job stalls only when it cannot run at all (< job_size idle servers), not
   whenever it is short of warm standbys; the depletion guard uses job_size too.
2. diagnosis_probability defaults to 0.8 (Table I).
3. Servers borrowed from the spare pool are returned once the need subsides.
4. Weibull / lognormal failure sampling is conditioned on server age, so ages
   carry across job restarts instead of resetting at every failure.
5. The bad-server regeneration rate is a parameter, not a hardcoded factor.
6. OneWaySweep accepts the paper's (label, param_name, values) form.
"""

from __future__ import annotations

import os
import random
import statistics

import pytest
import simpy

from airesim.coordinator import Coordinator
from airesim.params import Params
from airesim.policies import ServerRemovalPolicy
from airesim.pool import PoolManager
from airesim.run import _load_params
from airesim.server import Server, ServerState
from airesim.simulator import Simulator
from airesim.stats import StatsCollector
from airesim.sweep import OneWaySweep

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _small(**overrides) -> Params:
    base = dict(
        job_size=10, warm_standbys=4, working_pool_size=14, spare_pool_size=0,
        job_length=20000, random_failure_rate=1 / 600,
        systematic_failure_rate_multiplier=0.0, systematic_failure_fraction=0.0,
        recovery_time=1, host_selection_time=1, preemption_wait_time=5,
        auto_repair_time=200, manual_repair_time=200, prob_auto_to_manual=0.0,
        auto_repair_fail_prob=0.0, manual_repair_fail_prob=0.0,
        diagnosis_probability=1.0,
    )
    base.update(overrides)
    return Params(**base)


def _server(i: int, env=None, is_bad: bool = False) -> Server:
    return Server(i, env, is_bad, random_failure_rate=1e-3, systematic_failure_rate=0.0)


# ── 1. Stall threshold ───────────────────────────────────────────────────────

class _StallRecorder(Simulator):
    """Records how many servers were idle each time the main loop waits for a repair."""

    def _main_loop(self, env, rng, p, coordinator, scheduler, repair_shop, pool_mgr,
                   stats, all_servers):
        self.idle_at_stall: list[int] = []
        gen = super()._main_loop(env, rng, p, coordinator, scheduler, repair_shop,
                                 pool_mgr, stats, all_servers)
        value = None
        while True:
            try:
                event = gen.send(value)
            except StopIteration:
                return
            if event is repair_shop.server_repaired_event:
                self.idle_at_stall.append(len(pool_mgr.available_in_working))
            value = yield event


def test_no_stall_while_job_size_servers_are_idle():
    """With the spare pool empty, the job must start as soon as job_size servers are
    idle instead of waiting for its warm standbys to be refilled."""
    p = _small()
    sim = _StallRecorder(p, seed=1)
    stats = sim.run()
    assert sim.idle_at_stall, "scenario should exercise the stall path"
    assert max(sim.idle_at_stall) < p.job_size
    assert stats.total_compute_time == pytest.approx(p.job_length)


class _RetireFirstN(ServerRemovalPolicy):
    """Retire the first ``n`` servers that come out of repair."""

    def __init__(self, n: int):
        self.n = n
        self.retired = 0

    def reset(self) -> None:
        self.retired = 0

    def should_remove(self, server: Server, rng: random.Random) -> bool:
        if self.retired < self.n:
            self.retired += 1
            return True
        return False


def test_cluster_not_depleted_while_job_size_servers_remain():
    """Retiring below job_size + warm_standbys (but not below job_size) must not abort
    the job: it can still run without standbys."""
    p = _small(auto_repair_time=50, manual_repair_time=50)
    stats = Simulator(p, removal_policy=_RetireFirstN(3), seed=3).run()
    assert stats.servers_retired == 3
    assert not stats.cluster_depleted
    assert stats.total_compute_time == pytest.approx(p.job_length)


# ── 2. Diagnosis probability default ────────────────────────────────────────

def test_diagnosis_probability_default_matches_table_1():
    assert Params().diagnosis_probability == 0.8
    assert _load_params(os.path.join(ROOT, "config.yaml")).diagnosis_probability == 0.8


# ── 3. Returning borrowed spare-pool servers ────────────────────────────────

def test_release_borrowed_respects_keep_and_assignment():
    pm = PoolManager()
    servers = [_server(i) for i in range(6)]
    pm.init_pools(servers, working_size=3, spare_size=3)
    borrowed = [pm.move_spare_to_working() for _ in range(3)]
    assert pm.borrowed == borrowed and len(pm.available_in_working) == 6

    # Assigned borrowed servers are never released; release stops at keep_available.
    released = pm.release_borrowed(keep_available=4, assigned={id(borrowed[0])})
    assert released == 2
    assert pm.borrowed == [borrowed[0]]
    assert [s.state for s in borrowed[1:]] == [ServerState.SPARE] * 2
    assert len(pm.available_in_working) == 4
    assert pm.spare_return_count == 2

    # Non-idle borrowed servers (e.g. in repair) stay put.
    borrowed[0].begin_auto_repair()
    assert pm.release_borrowed(keep_available=0) == 0


def test_retiring_a_borrowed_server_drops_it_from_borrowed():
    pm = PoolManager()
    servers = [_server(i) for i in range(2)]
    pm.init_pools(servers, working_size=1, spare_size=1)
    s = pm.move_spare_to_working()
    pm.retire_server(s)
    assert pm.borrowed == []


def _spare_params(**overrides) -> Params:
    return _small(working_pool_size=14, spare_pool_size=10, auto_repair_time=60,
                  manual_repair_time=60, job_length=60000, **overrides)


def test_borrowed_spares_are_returned():
    stats = Simulator(_spare_params(), seed=5).run()
    assert stats.preemption_count > 0
    assert stats.spare_return_count > 0


def test_spare_return_can_be_disabled():
    stats = Simulator(_spare_params(return_borrowed_spares=False), seed=5).run()
    assert stats.preemption_count > 0
    assert stats.spare_return_count == 0


def test_job_never_runs_on_spare_pool_servers(monkeypatch):
    """Releasing borrowed servers must never pull one out from under the job."""
    orig = Coordinator.run_until_failure

    def checked(self, servers, remaining):
        assert all(s.state != ServerState.SPARE for s in servers)
        assert len({id(s) for s in servers}) == len(servers)
        return (yield from orig(self, servers, remaining))

    monkeypatch.setattr(Coordinator, "run_until_failure", checked)
    for seed in range(5):
        Simulator(_spare_params(), seed=seed).run()


# ── 4. Age-aware non-exponential failures ───────────────────────────────────

def _coord(dist: str, **kw) -> Coordinator:
    env = simpy.Environment()
    return Coordinator(env, StatsCollector(), random.Random(0), failure_distribution=dist, **kw)


def _mean_residual(coord: Coordinator, rate: float, age: float, n: int = 20000) -> float:
    return statistics.fmean(coord._sample_residual(rate, age) for _ in range(n))


def test_weibull_shape_one_is_memoryless():
    c = _coord("weibull", weibull_shape=1.0)
    assert _mean_residual(c, 0.01, age=0.0) == pytest.approx(100, rel=0.03)
    assert _mean_residual(c, 0.01, age=500.0) == pytest.approx(100, rel=0.03)


def test_weibull_wear_out_shortens_residual_life_with_age():
    c = _coord("weibull", weibull_shape=3.0)
    assert _mean_residual(c, 0.01, age=0.0) == pytest.approx(100, rel=0.03)
    assert _mean_residual(c, 0.01, age=150.0) < 0.5 * _mean_residual(c, 0.01, age=0.0)


def test_lognormal_residual_sampling():
    c = _coord("lognormal", lognormal_sigma=1.0)
    assert _mean_residual(c, 0.01, age=0.0) == pytest.approx(100, rel=0.05)
    samples = [c._sample_residual(0.01, age) for age in (1e-9, 50.0, 1e4, 1e9)
               for _ in range(200)]
    assert all(t >= 0 and t == t for t in samples)  # non-negative, no NaN


def test_server_age_accumulates_and_resets_on_repair():
    env = simpy.Environment()
    c = Coordinator(env, StatsCollector(), random.Random(0), failure_distribution="weibull",
                    weibull_shape=2.0)
    servers = [_server(i, env) for i in range(3)]
    env.process(c.run_until_failure(servers, remaining_job_time=1e9))
    env.run()
    assert env.now > 0
    assert all(s.age == pytest.approx(env.now) for s in servers)
    servers[0].complete_repair(success=True)
    assert servers[0].age == 0.0


# ── 5. Bad-server regeneration rate ─────────────────────────────────────────

@pytest.mark.parametrize("scale,expected", [(0.1, 10), (0.5, 50)])
def test_bad_server_regen_scale(scale, expected):
    env = simpy.Environment()
    servers = [_server(i, env) for i in range(1000)]
    p = Params(bad_server_regen_scale=scale, systematic_failure_fraction=0.1,
               bad_server_regen_interval=10)
    env.process(Simulator(p)._bad_server_regen(env, random.Random(0), p, servers))
    env.run(until=15)
    assert sum(s.is_bad for s in servers) == expected


def test_bad_server_regen_scale_validated():
    with pytest.raises(ValueError):
        Params(bad_server_regen_scale=-1).validate()


# ── 6. OneWaySweep paper form ───────────────────────────────────────────────

def test_one_way_sweep_paper_form():
    base = _small(job_length=2000)
    sweep = OneWaySweep("Systematic Failure Fraction", "systematic_failure_fraction",
                        [0.0, 0.2], base_params=base, num_replications=1)
    assert sweep.param_name == "systematic_failure_fraction"
    assert sweep.values == [0.0, 0.2]
    result = sweep.run(verbose=False)
    assert result.sweep_name == "Systematic Failure Fraction"
    assert [a.param_value for a in result.results] == [0.0, 0.2]


def test_one_way_sweep_positional_forms():
    base = Params()
    paper = OneWaySweep("Label", "recovery_time", [10, 20], base, 3)
    plain = OneWaySweep("recovery_time", [10, 20], base, 3)
    for sweep in (paper, plain):
        assert (sweep.param_name, sweep.values) == ("recovery_time", [10, 20])
        assert sweep.base_params is base and sweep.num_replications == 3
    assert paper.label == "Label" and plain.label is None


def test_one_way_sweep_rejects_duplicate_arguments():
    with pytest.raises(TypeError):
        OneWaySweep("recovery_time", [10, 20], values=[30])
    with pytest.raises(TypeError):
        OneWaySweep("Label", "recovery_time", [10], label="Other")
    with pytest.raises(TypeError):
        OneWaySweep("recovery_time")
