"""Edge-case tests for the AIReSim main simulation loop.

Covers three specific bugs found in simulator.py:

  (a) Repaired servers are never fed back as warm standbys mid-job —
      scheduler.return_server_to_job() exists but is never called.

  (b) diagnosis_uncertainty double-submits the misdiagnosed server to repair,
      and the real failed server stays in active_servers with IDLE state while
      its failure was already recorded.

  (c) server_repaired_event has a missed-signal race: the event is succeeded
      and immediately replaced before the main-loop process has a chance to
      yield on it, so the main loop can wait forever on the new, un-signaled
      event.
"""

import random
import sys
import os

import simpy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airesim.server import Server, ServerState
from airesim.pool import PoolManager
from airesim.scheduler import Scheduler
from airesim.repairs import RepairShop
from airesim.coordinator import Coordinator
from airesim.stats import StatsCollector
from airesim.params import Params
from airesim.simulator import Simulator
from airesim.policies import DefaultHostSelection, NeverRemove, DefaultRepairEscalation


# ── helpers ──────────────────────────────────────────────────────────────────

def make_server(env, server_id=0, is_bad=False, random_failure_rate=0.0):
    return Server(
        server_id=server_id,
        env=env,
        is_bad=is_bad,
        random_failure_rate=random_failure_rate,
        systematic_failure_rate=0.0,
    )


def make_repair_shop(env, rng, pool_mgr, stats,
                     auto_repair_time=1.0, manual_repair_time=1.0,
                     prob_auto_to_manual=0.0):
    """Repair shop that always auto-repairs successfully and never removes servers."""
    return RepairShop(
        env=env,
        rng=rng,
        auto_repair_time=auto_repair_time,
        manual_repair_time=manual_repair_time,
        prob_auto_to_manual=prob_auto_to_manual,
        auto_repair_fail_prob=0.0,        # auto repair always succeeds
        manual_repair_fail_prob=0.0,
        escalation_policy=DefaultRepairEscalation(prob_escalate=0.0),
        removal_policy=NeverRemove(),
        pool_manager=pool_mgr,
        stats=stats,
    )


# ── (a) repaired server not re-added as warm standby mid-job ─────────────────

def test_repaired_server_added_to_warm_standbys():
    """Bug (a): scheduler.return_server_to_job() is never called.

    After a server completes repair mid-job, it should be added back into
    scheduler.warm_standbys so the job doesn't operate without a standby
    indefinitely.  Currently the server silently sits in available_in_working
    and is never promoted to standby until the next full host-selection.
    """
    env = simpy.Environment()
    rng = random.Random(0)
    stats = StatsCollector()

    # 3 servers: 2 active (job_size=2), 1 warm standby
    servers = [make_server(env, i) for i in range(3)]
    pool_mgr = PoolManager()
    pool_mgr.init_pools(servers, working_size=3, spare_size=0)

    scheduler = Scheduler(
        env=env, rng=rng,
        job_size=2, warm_standby_count=1,
        host_selection_time=0,
        host_selection_policy=DefaultHostSelection(),
        pool_manager=pool_mgr,
        stats=stats,
    )
    scheduler.do_host_selection()

    repair_shop = make_repair_shop(env, rng, pool_mgr, stats, auto_repair_time=5.0)

    # Simulate: use the warm standby (now warm_standbys is empty), then
    # send the swapped-out server to repair.  After repair_time minutes
    # the server should re-appear in scheduler.warm_standbys.
    failed = scheduler.active_servers[0]
    failed.mark_failed()
    pool_mgr.remove_from_working(failed)
    replacement = scheduler.swap_in_standby(failed)
    assert replacement is not None, "swap should have succeeded"
    assert len(scheduler.warm_standbys) == 0, "standby list should now be empty"

    repair_shop.submit(failed)

    def check_after_repair():
        yield env.timeout(10)   # well past auto_repair_time=5
        # The repaired server should have been added back to warm_standbys.
        assert failed in scheduler.warm_standbys, (
            "Bug (a): repaired server was NOT added back to scheduler.warm_standbys — "
            "return_server_to_job() is never called from the repair pipeline"
        )

    env.process(check_after_repair())
    env.run()
    print("  [PASS] test_repaired_server_added_to_warm_standbys")


# ── (b) diagnosis_uncertainty bugs ───────────────────────────────────────────

def test_misdiagnosis_does_not_double_submit_to_repair():
    """Bug (b-i): when misdiagnosis fires, the misdiagnosed server is submitted
    to the repair shop twice — once inside the if-block and once by the
    unconditional submit that follows it (after failed_server is rebound).

    Expected: exactly 1 auto_repair recorded for a single failure event
    with diagnosis_uncertainty=1.0.
    Actual:   2 auto_repairs (the server goes through the pipeline twice).
    """
    p = Params(
        job_size=2,
        warm_standbys=1,
        working_pool_size=5,
        spare_pool_size=2,
        job_length=10000,
        # One failure is near-certain within the job
        random_failure_rate=1.0,
        systematic_failure_rate_multiplier=0.0,
        systematic_failure_fraction=0.0,
        recovery_time=0,
        host_selection_time=0,
        preemption_wait_time=0,
        auto_repair_time=1,
        manual_repair_time=1,
        prob_auto_to_manual=0.0,     # always auto repair
        auto_repair_fail_prob=0.0,
        manual_repair_fail_prob=0.0,
        diagnosis_uncertainty=1.0,   # always misdiagnose
        seed=7,
    )
    sim = Simulator(p)
    stats = sim.run()

    # Each misdiagnosis event should send exactly one server to repair.
    # total_failures is the number of failure events detected.
    # auto_repairs should equal total_failures (1 repair per failure event).
    assert stats.auto_repairs == stats.total_failures, (
        f"Bug (b-i): auto_repairs ({stats.auto_repairs}) != total_failures "
        f"({stats.total_failures}). Misdiagnosed server is submitted twice."
    )
    print(f"  [PASS] test_misdiagnosis_does_not_double_submit_to_repair "
          f"(failures={stats.total_failures}, auto_repairs={stats.auto_repairs})")


def test_misdiagnosis_real_failed_server_not_in_active_list():
    """Bug (b-ii): after misdiagnosis the real failed server has its state
    force-set to IDLE and is left in scheduler.active_servers.  The next call
    to run_until_failure therefore includes a server that logically failed but
    was never repaired — its failure_count has been incremented and its
    failure_timestamps updated, but it's still running the job.

    We detect this by running with diagnosis_uncertainty=1.0 and verifying
    that after a failure event, no server in active_servers has
    total_failure_count > 0 while still in IDLE/running state.  (A repaired
    server that re-joined would have count > 0 but a different history.)

    Specifically: after the main loop handles a misdiagnosis, the real failed
    server must NOT still be in active_servers — it should have been removed.
    """
    env = simpy.Environment()
    rng = random.Random(42)

    # Minimal manual wiring so we can inspect scheduler state after the event
    from airesim.simulator import Simulator as _Sim  # noqa: import to inspect internals

    # We run a tiny sim and inspect via a hook injected through subclassing
    captured = {}

    class InspectingSim(_Sim):
        def _main_loop(self, env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats):
            remaining = p.job_length
            # One iteration: host select, then one run_until_failure
            scheduler.do_host_selection()
            yield env.timeout(p.host_selection_time)

            run_result = env.process(
                coordinator.run_until_failure(scheduler.active_servers, remaining)
            )
            yield run_result
            failed_server, duration = run_result.value

            if failed_server is not None:
                # Capture state BEFORE the main loop's misdiagnosis/repair block
                captured["failed_server"] = failed_server
                captured["active_before"] = list(scheduler.active_servers)

                # Replicate the misdiagnosis logic (same as simulator.py)
                if p.diagnosis_uncertainty > 0 and rng.random() < p.diagnosis_uncertainty:
                    innocents = [s for s in scheduler.active_servers
                                 if s is not failed_server]
                    if innocents:
                        misdiagnosed = rng.choice(innocents)
                        misdiagnosed.mark_failed()
                        pool_mgr.remove_from_working(misdiagnosed)
                        repair_shop.submit(misdiagnosed)
                        failed_server.state = ServerState.IDLE
                        failed_server = misdiagnosed

                captured["real_failed_still_active"] = (
                    captured["failed_server"] in scheduler.active_servers
                )
                captured["real_failed_state"] = captured["failed_server"].state

            stats.total_training_time = env.now

    p = Params(
        job_size=3, warm_standbys=1,
        working_pool_size=6, spare_pool_size=2,
        job_length=100000,
        random_failure_rate=1.0,
        systematic_failure_rate_multiplier=0.0,
        systematic_failure_fraction=0.0,
        recovery_time=0, host_selection_time=0, preemption_wait_time=0,
        auto_repair_time=1, manual_repair_time=1,
        prob_auto_to_manual=0.0, auto_repair_fail_prob=0.0,
        manual_repair_fail_prob=0.0,
        diagnosis_uncertainty=1.0,
        seed=3,
    )
    InspectingSim(p).run()

    assert "real_failed_still_active" in captured, "No failure event was triggered"
    assert not captured["real_failed_still_active"], (
        f"Bug (b-ii): real failed server (id={captured['failed_server'].server_id}, "
        f"state={captured['real_failed_state']}) is still in active_servers after "
        f"misdiagnosis — it was never removed from the active list"
    )
    print(f"  [PASS] test_misdiagnosis_real_failed_server_not_in_active_list")


# ── (c) missed-signal race on server_repaired_event ─────────────────────────

def test_server_repaired_event_not_missed_when_signal_fires_before_yield():
    """Bug (c): _signal_repaired() calls event.succeed() then immediately
    replaces self.server_repaired_event with a new un-triggered event.

    If repair completes at SimPy time T while the main loop process is
    running (not yet suspended on the event), the main loop will later
    evaluate repair_shop.server_repaired_event, get the already-replaced
    fresh event, and block forever.

    This test sets up exactly that scenario: a repair process and a waiter
    process both scheduled at time T=5.  SimPy runs them in FIFO order, so
    the repair fires first, replaces the event, and then the waiter yields
    on the new (un-signaled) event — causing a deadlock.

    The simulation should finish within a finite time; if it hangs the
    env.run(until=...) guard will let us detect the missed signal.
    """
    env = simpy.Environment()
    rng = random.Random(0)
    stats = StatsCollector()

    servers = [make_server(env, i) for i in range(3)]
    pool_mgr = PoolManager()
    pool_mgr.init_pools(servers, working_size=3, spare_size=0)

    repair_shop = make_repair_shop(env, rng, pool_mgr, stats, auto_repair_time=5.0)

    woke_up = []

    def waiter():
        # Delay until exactly the same simtime the repair will complete (t=5).
        # Then, without yielding again, grab the event reference and yield on it.
        yield env.timeout(5)
        # At this point, if the repair process also ran at t=5 before us,
        # server_repaired_event has already been replaced — this yield hangs.
        event = repair_shop.server_repaired_event
        yield event
        woke_up.append(True)

    # Submit a server to repair at t=0; auto_repair_time=5 → completes at t=5.
    failed = servers[0]
    failed.mark_failed()
    pool_mgr.remove_from_working(failed)
    repair_shop.submit(failed)

    env.process(waiter())

    # Run with a deadline well beyond t=5 so we can detect a hang.
    env.run(until=50)

    assert woke_up, (
        "Bug (c): waiter process never woke up — missed-signal race: "
        "_signal_repaired() replaced server_repaired_event before the "
        "waiter could yield on it, so the waiter is blocked on a fresh "
        "un-triggered event forever"
    )
    print("  [PASS] test_server_repaired_event_not_missed_when_signal_fires_before_yield")


def test_multiple_simultaneous_repairs_all_wake_waiters():
    """Bug (c) variant: two servers complete repair at the same simtime.

    _signal_repaired is called twice in the same timestep.  The second call
    sees a fresh (already-replaced) event, signals it, then replaces it again.
    A waiter that grabbed the event reference between the two signals would
    see neither.  Even if there is only one waiter, a second simultaneous
    repair should not silently swallow the signal.

    After both repairs complete, the waiter (which woke on the first signal)
    must have run, and both servers must be back in the working pool.
    """
    env = simpy.Environment()
    rng = random.Random(0)
    stats = StatsCollector()

    servers = [make_server(env, i) for i in range(4)]
    pool_mgr = PoolManager()
    pool_mgr.init_pools(servers, working_size=4, spare_size=0)

    # Both servers will finish auto-repair at exactly t=5 (deterministic=True
    # is simulated by using the mean of an expovariate with very small variance—
    # instead we override _repair_process by using a fixed timeout).
    class FixedTimeRepairShop(RepairShop):
        def _repair_process(self, server):
            server.begin_auto_repair()
            yield self.env.timeout(5)          # fixed, not exponential
            self.stats.auto_repairs += 1
            server.complete_repair(success=True)
            self.pool_manager.return_to_working(server)
            self._signal_repaired()

    repair_shop = FixedTimeRepairShop(
        env=env, rng=rng,
        auto_repair_time=5, manual_repair_time=5,
        prob_auto_to_manual=0.0, auto_repair_fail_prob=0.0,
        manual_repair_fail_prob=0.0,
        escalation_policy=DefaultRepairEscalation(prob_escalate=0.0),
        removal_policy=NeverRemove(),
        pool_manager=pool_mgr,
        stats=stats,
    )

    signals_received = []

    def waiter():
        # Wait for first repair signal
        yield repair_shop.server_repaired_event
        signals_received.append(env.now)

    for s in [servers[0], servers[1]]:
        s.mark_failed()
        pool_mgr.remove_from_working(s)
        repair_shop.submit(s)

    env.process(waiter())
    env.run(until=20)

    assert signals_received, (
        "Bug (c): waiter never received the repair signal even though two "
        "servers completed repair at t=5"
    )
    assert signals_received[0] == 5.0, (
        f"Signal received at wrong time: {signals_received[0]}"
    )

    returned = [s for s in servers[:2] if s.state == ServerState.IDLE]
    assert len(returned) == 2, (
        f"Expected both servers back in IDLE after repair, got {len(returned)}"
    )
    print("  [PASS] test_multiple_simultaneous_repairs_all_wake_waiters")


# ── runner ────────────────────────────────────────────────────────────────────

def main():
    print("Running edge-case tests...\n")
    tests = [
        test_repaired_server_added_to_warm_standbys,
        test_misdiagnosis_does_not_double_submit_to_repair,
        test_misdiagnosis_real_failed_server_not_in_active_list,
        test_server_repaired_event_not_missed_when_signal_fires_before_yield,
        test_multiple_simultaneous_repairs_all_wake_waiters,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  [FAIL] {test.__name__}:\n    {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  [ERROR] {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
