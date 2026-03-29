"""Tests for AIReSim core components."""

import random
import simpy
import sys
import os
import time

# Add parent dir to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.params import Params
from airesim.server import Server, ServerState
from airesim.pool import PoolManager
from airesim.coordinator import Coordinator
from airesim.simulator import Simulator
from airesim.stats import StatsCollector, AggregateStats
from airesim.sweep import OneWaySweep
from airesim.scheduling_policies import DefaultHostSelection, FewestFailuresFirst
from airesim.policies import ThresholdRemoval


# ── Params tests ─────────────────────────────────────────────────────────────

def test_params_defaults():
    """Params should have sensible defaults and validate."""
    p = Params()
    p.validate()
    assert p.systematic_failure_rate == 5 * p.random_failure_rate
    assert p.total_servers_needed == 4096 + 16
    print("  [PASS] test_params_defaults")


def test_params_override():
    """with_overrides should produce a new Params with changed values."""
    p = Params(recovery_time=20)
    p2 = p.with_overrides(recovery_time=30)
    assert p.recovery_time == 20
    assert p2.recovery_time == 30
    print("  [PASS] test_params_override")


def test_params_validation():
    """Invalid params should raise ValueError."""
    try:
        p = Params(working_pool_size=100, job_size=4096, warm_standbys=16)
        p.validate()
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] test_params_validation")


# ── Server tests ─────────────────────────────────────────────────────────────

def test_server_state_machine():
    """Server should transition through states correctly."""
    env = simpy.Environment()
    s = Server(0, env, is_bad=False, random_failure_rate=0.01,
               systematic_failure_rate=0.0)

    assert s.state == ServerState.IDLE
    s.mark_running()
    assert s.state == ServerState.RUNNING
    s.mark_failed()
    assert s.state == ServerState.FAILED
    s.begin_auto_repair()
    assert s.state == ServerState.AUTO_REPAIR
    s.complete_repair(success=True)
    assert s.state == ServerState.IDLE
    print("  [PASS] test_server_state_machine")


def test_server_failure_rate():
    """Bad servers should have higher failure rates than good servers."""
    env = simpy.Environment()
    good = Server(0, env, is_bad=False, random_failure_rate=0.01,
                  systematic_failure_rate=0.05)
    bad = Server(1, env, is_bad=True, random_failure_rate=0.01,
                 systematic_failure_rate=0.05)

    assert good.failure_rate == 0.01  # only random
    assert abs(bad.failure_rate - 0.06) < 1e-10   # random + systematic
    print("  [PASS] test_server_failure_rate")


def test_server_repair_cures_bad():
    """Successful repair should make a bad server good."""
    env = simpy.Environment()
    s = Server(0, env, is_bad=True, random_failure_rate=0.01,
               systematic_failure_rate=0.05)
    assert s.is_bad
    s.complete_repair(success=True)
    assert not s.is_bad
    assert s.failure_rate == 0.01  # now only random
    print("  [PASS] test_server_repair_cures_bad")


def test_server_failed_repair_stays_bad():
    """Failed repair should leave a bad server bad."""
    env = simpy.Environment()
    s = Server(0, env, is_bad=True, random_failure_rate=0.01,
               systematic_failure_rate=0.05)
    s.complete_repair(success=False)
    assert s.is_bad
    print("  [PASS] test_server_failed_repair_stays_bad")


def test_server_failures_in_window():
    """failures_in_window should count correctly."""
    env = simpy.Environment()
    s = Server(0, env, is_bad=False, random_failure_rate=0.01,
               systematic_failure_rate=0.0)

    env.run(until=1000)
    s.failure_timestamps = [900, 950, 999, 500, 200]
    assert s.failures_in_window(200) == 3  # 900, 950, 999 are within [800, 1000]
    assert s.failures_in_window(1000) == 5
    print("  [PASS] test_server_failures_in_window")


# ── Pool tests ───────────────────────────────────────────────────────────────

def test_pool_manager():
    """Pool manager should correctly partition and move servers."""
    env = simpy.Environment()
    servers = [
        Server(i, env, is_bad=False, random_failure_rate=0.01,
               systematic_failure_rate=0.0)
        for i in range(20)
    ]

    pool = PoolManager()
    pool.init_pools(servers, working_size=15, spare_size=5)

    assert len(pool.working_pool) == 15
    assert len(pool.spare_pool) == 5
    assert len(pool.available_in_working) == 15

    # Move spare to working
    moved = pool.move_spare_to_working()
    assert moved is not None
    assert len(pool.working_pool) == 16
    assert len(pool.spare_pool) == 4
    assert pool.preemption_count == 1

    # Retire a server
    pool.retire_server(servers[0])
    assert servers[0].state == ServerState.RETIRED
    assert len(pool.retired) == 1
    print("  [PASS] test_pool_manager")


# ── Coordinator tests ────────────────────────────────────────────────────────

def test_coordinator_detects_failure():
    """Coordinator should detect when a server fails during job execution."""
    env = simpy.Environment()
    rng = random.Random(42)
    stats = StatsCollector()
    coord = Coordinator(env, stats, rng)

    # Create servers with high failure rate so they fail quickly
    servers = [
        Server(i, env, is_bad=False, random_failure_rate=1.0,
               systematic_failure_rate=0.0)
        for i in range(4)
    ]

    def run_job():
        failed, duration = yield env.process(
            coord.run_until_failure(servers, remaining_job_time=1000.0)
        )
        assert failed is not None, "Expected a failure"
        assert duration > 0
        assert duration < 1000.0  # should fail well before job completes
        assert stats.total_failures == 1

    env.process(run_job())
    env.run()
    print("  [PASS] test_coordinator_detects_failure")


def test_coordinator_job_completes():
    """With zero failure rate, coordinator should report job completion."""
    env = simpy.Environment()
    rng = random.Random(42)
    stats = StatsCollector()
    coord = Coordinator(env, stats, rng)

    servers = [
        Server(i, env, is_bad=False, random_failure_rate=0.0,
               systematic_failure_rate=0.0)
        for i in range(4)
    ]

    def run_job():
        failed, duration = yield env.process(
            coord.run_until_failure(servers, remaining_job_time=100.0)
        )
        assert failed is None, "Expected no failure"
        assert abs(duration - 100.0) < 0.01
        assert stats.total_failures == 0

    env.process(run_job())
    env.run()
    print("  [PASS] test_coordinator_job_completes")


def test_coordinator_bad_server_more_likely_to_fail():
    """Bad servers should fail more often than good servers."""
    rng = random.Random(42)
    bad_count = 0
    good_count = 0
    trials = 500

    for i in range(trials):
        env = simpy.Environment()
        stats = StatsCollector()
        coord = Coordinator(env, stats, random.Random(i))

        servers = [
            Server(0, env, is_bad=True, random_failure_rate=0.01,
                   systematic_failure_rate=0.09),
            Server(1, env, is_bad=False, random_failure_rate=0.01,
                   systematic_failure_rate=0.09),
        ]

        def run(c=coord, s=servers):
            failed, _ = yield env.process(c.run_until_failure(s, 10000.0))
            return failed

        proc = env.process(run())
        env.run()
        if proc.value.server_id == 0:
            bad_count += 1
        else:
            good_count += 1

    # Bad server has rate 0.10, good has 0.01 — bad should fail ~10x more often
    ratio = bad_count / max(good_count, 1)
    assert ratio > 5, f"Bad server should fail much more; ratio={ratio:.1f}"
    print(f"  [PASS] test_coordinator_bad_server_more_likely_to_fail "
          f"(bad={bad_count}, good={good_count}, ratio={ratio:.1f})")


# ── Full simulation tests ────────────────────────────────────────────────────

def test_full_simulation_small():
    """Run a small simulation to verify end-to-end correctness."""
    p = Params(
        job_size=8,
        warm_standbys=2,
        working_pool_size=12,
        spare_pool_size=4,
        job_length=100 * 24 * 60,  # 100 days in minutes
        random_failure_rate=0.01 / (24 * 60),
        systematic_failure_rate_multiplier=5.0,
        systematic_failure_fraction=0.15,
        recovery_time=20,
        host_selection_time=3,
        preemption_wait_time=20,
        auto_repair_time=120,
        manual_repair_time=2 * 1440,
        seed=42,
    )
    sim = Simulator(p)
    stats = sim.run()

    assert stats.total_training_time > 0
    assert stats.total_training_time >= p.job_length
    assert stats.host_selection_count >= 1
    print(f"  [PASS] test_full_simulation_small "
          f"(time={stats.training_time_hours:.1f}hrs, "
          f"failures={stats.total_failures})")


def test_full_simulation_no_failures():
    """With zero failure rate, training time should equal job length + overhead."""
    p = Params(
        job_size=8,
        warm_standbys=2,
        working_pool_size=12,
        spare_pool_size=4,
        job_length=10 * 24 * 60,  # 10 days
        random_failure_rate=0.0,
        systematic_failure_rate_multiplier=0.0,
        systematic_failure_fraction=0.0,
        recovery_time=20,
        host_selection_time=3,
        seed=42,
    )
    sim = Simulator(p)
    stats = sim.run()

    expected = p.job_length + p.host_selection_time
    assert abs(stats.total_training_time - expected) < 1.0, (
        f"Expected ~{expected}, got {stats.total_training_time}"
    )
    assert stats.total_failures == 0
    print(f"  [PASS] test_full_simulation_no_failures "
          f"(time={stats.total_training_time:.1f} mins, expected={expected:.1f})")


def test_full_simulation_4096_nodes():
    """Verify the simulator runs at paper scale (4096 nodes) in reasonable time."""
    p = Params(
        job_size=4096,
        warm_standbys=16,
        working_pool_size=4160,
        spare_pool_size=200,
        job_length=30 * 24 * 60,  # 30 days
        random_failure_rate=0.01 / (24 * 60),
        systematic_failure_rate_multiplier=5.0,
        systematic_failure_fraction=0.15,
        recovery_time=20,
        seed=42,
    )

    t0 = time.time()
    sim = Simulator(p)
    stats = sim.run()
    wall_time = time.time() - t0

    assert stats.total_training_time > 0
    assert stats.total_failures > 0  # with 4096 nodes, failures are expected
    assert wall_time < 10.0, f"Simulation too slow: {wall_time:.1f}s"
    print(f"  [PASS] test_full_simulation_4096_nodes "
          f"(wall={wall_time:.2f}s, sim_time={stats.training_time_hours:.1f}hrs, "
          f"failures={stats.total_failures})")


def test_deterministic_seeds():
    """Same seed should produce identical results."""
    p = Params(
        job_size=16, warm_standbys=2, working_pool_size=20,
        spare_pool_size=5, job_length=30 * 24 * 60, seed=123,
    )
    s1 = Simulator(p, seed=123).run()
    s2 = Simulator(p, seed=123).run()
    assert s1.total_training_time == s2.total_training_time
    assert s1.total_failures == s2.total_failures
    print("  [PASS] test_deterministic_seeds")


# ── Policy tests ─────────────────────────────────────────────────────────────

def test_fewest_failures_policy():
    """FewestFailuresFirst should prefer servers with fewer failures."""
    env = simpy.Environment()
    rng = random.Random(42)
    servers = [
        Server(i, env, is_bad=False, random_failure_rate=0.01,
               systematic_failure_rate=0.0)
        for i in range(10)
    ]
    servers[0].total_failure_count = 5
    servers[1].total_failure_count = 3
    servers[2].total_failure_count = 0

    policy = FewestFailuresFirst()
    selected = policy.select(servers, job_size=3, warm_standbys=0, rng=rng)

    failure_counts = [s.total_failure_count for s in selected]
    assert failure_counts == sorted(failure_counts)
    print("  [PASS] test_fewest_failures_policy")


def test_threshold_removal():
    """ThresholdRemoval should remove servers exceeding failure threshold."""
    env = simpy.Environment()
    rng = random.Random(42)
    s = Server(0, env, is_bad=True, random_failure_rate=0.01,
               systematic_failure_rate=0.05)

    now = 1000.0
    for i in range(6):
        s.failure_timestamps.append(now - i * 60)

    policy = ThresholdRemoval(max_failures=5, window_minutes=7 * 24 * 60)

    env.run(until=now)
    assert policy.should_remove(s, rng) == True
    print("  [PASS] test_threshold_removal")


# ── Stats tests ──────────────────────────────────────────────────────────────

def test_aggregate_stats():
    """AggregateStats should compute correct summaries."""
    runs = []
    for i in range(10):
        s = StatsCollector()
        s.total_training_time = 100 + i * 10  # 100, 110, ..., 190 minutes
        s.total_failures = i
        runs.append(s)

    agg = AggregateStats(
        param_label="test", param_value=42, num_runs=10, raw_results=runs
    )
    tt = agg.training_time_summary()
    # Mean of 100..190 = 145 minutes = 2.417 hours
    assert abs(tt["mean"] - 145 / 60) < 0.1
    print("  [PASS] test_aggregate_stats")


# ── Sweep tests ──────────────────────────────────────────────────────────────

def test_one_way_sweep():
    """OneWaySweep should produce results for each parameter value."""
    base = Params(
        job_size=8, warm_standbys=2, working_pool_size=12,
        spare_pool_size=4, job_length=10 * 24 * 60,
    )
    sweep = OneWaySweep(
        param_name="recovery_time",
        values=[10, 20, 30],
        base_params=base,
        num_replications=3,
    )
    result = sweep.run(verbose=False)

    assert len(result.results) == 3
    # Higher recovery time should generally mean longer training time
    means = [agg.training_time_summary()["mean"] for agg in result.results]
    # Not strictly monotone due to randomness, but should have 3 data points
    assert all(m > 0 for m in means)
    print(f"  [PASS] test_one_way_sweep (means={[f'{m:.1f}' for m in means]})")


# ── Failure-distribution tests ───────────────────────────────────────────────

def test_failure_distributions():
    """All three failure distributions should produce a complete simulation run."""
    base = Params(
        job_size=8,
        warm_standbys=2,
        working_pool_size=12,
        spare_pool_size=4,
        job_length=30 * 24 * 60,
        random_failure_rate=0.01 / (24 * 60),
        systematic_failure_rate_multiplier=5.0,
        systematic_failure_fraction=0.15,
        recovery_time=20,
        host_selection_time=3,
        seed=42,
    )

    results = {}
    for dist in ('exponential', 'weibull', 'lognormal'):
        p = base.with_overrides(failure_distribution=dist)
        stats = Simulator(p).run()
        assert stats.total_training_time > 0, \
            f"{dist}: total_training_time should be > 0"
        assert stats.total_training_time >= p.job_length, \
            f"{dist}: total_training_time should be >= job_length"
        results[dist] = stats

    print("  [PASS] test_failure_distributions")
    for dist, s in results.items():
        print(f"    {dist:12s}: time={s.training_time_hours:.1f}hrs, "
              f"failures={s.total_failures}")


def test_failure_distribution_validation():
    """Invalid failure_distribution should raise ValueError."""
    try:
        Params(failure_distribution='poisson').validate()
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("  [PASS] test_failure_distribution_validation")


def test_weibull_shape_1_matches_exponential_mean():
    """Weibull with k=1 has the same mean as exponential — failure counts
    should be in the same ballpark over many replications."""
    base = Params(
        job_size=4, warm_standbys=1, working_pool_size=7, spare_pool_size=2,
        job_length=30 * 24 * 60,
        random_failure_rate=0.01 / (24 * 60),
        systematic_failure_rate_multiplier=0.0,
        systematic_failure_fraction=0.0,
        recovery_time=0, host_selection_time=0, seed=1,
    )
    failures = {}
    for dist in ('exponential', 'weibull'):
        total = sum(
            Simulator(base.with_overrides(failure_distribution=dist, weibull_shape=1.0,
                                          seed=i)).run().total_failures
            for i in range(20)
        )
        failures[dist] = total / 20

    # With k=1, Weibull is exponential — means should agree within 50 %
    ratio = failures['weibull'] / max(failures['exponential'], 1)
    assert 0.5 < ratio < 2.0, (
        f"Weibull(k=1) mean failures ({failures['weibull']:.1f}) should be "
        f"close to exponential ({failures['exponential']:.1f}), ratio={ratio:.2f}"
    )
    print(f"  [PASS] test_weibull_shape_1_matches_exponential_mean "
          f"(exp={failures['exponential']:.1f}, weibull={failures['weibull']:.1f})")


# ── Runner ───────────────────────────────────────────────────────────────────

def main():
    print("Running AIReSim tests...\n")
    tests = [
        test_params_defaults,
        test_params_override,
        test_params_validation,
        test_server_state_machine,
        test_server_failure_rate,
        test_server_repair_cures_bad,
        test_server_failed_repair_stays_bad,
        test_server_failures_in_window,
        test_pool_manager,
        test_coordinator_detects_failure,
        test_coordinator_job_completes,
        test_coordinator_bad_server_more_likely_to_fail,
        test_full_simulation_small,
        test_full_simulation_no_failures,
        test_full_simulation_4096_nodes,
        test_deterministic_seeds,
        test_fewest_failures_policy,
        test_threshold_removal,
        test_aggregate_stats,
        test_one_way_sweep,
        test_failure_distributions,
        test_failure_distribution_validation,
        test_weibull_shape_1_matches_exponential_mean,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
