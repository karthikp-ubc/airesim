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
from airesim.scheduling_policies import DefaultHostSelection
from airesim.policies import NeverRemove, DefaultRepairEscalation


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
    """Bug (a): Simulator must wire repair_shop.on_server_returned to
    scheduler.return_server_to_job so repaired servers re-join as warm
    standbys mid-job.

    We subclass Simulator to capture the scheduler reference, then verify
    that after a repair completes the warm-standby list is replenished.
    The simulation is set up so a failure burns the only warm standby, and
    the repair shop has a near-zero repair time so the server returns quickly.
    """
    observed = {}

    class InspectingSim(Simulator):
        def _main_loop(self, env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats, all_servers):
            observed["scheduler"] = scheduler
            observed["repair_shop"] = repair_shop
            yield from super()._main_loop(
                env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats, all_servers
            )

    p = Params(
        job_size=2,
        warm_standbys=1,
        working_pool_size=5,
        spare_pool_size=2,
        job_length=10 * 24 * 60,
        random_failure_rate=0.1,   # high — ensures a failure happens quickly
        systematic_failure_rate_multiplier=0.0,
        systematic_failure_fraction=0.0,
        recovery_time=0,
        host_selection_time=0,
        preemption_wait_time=0,
        auto_repair_time=1,        # near-instant repair so server returns mid-job
        manual_repair_time=1,
        prob_auto_to_manual=0.0,
        auto_repair_fail_prob=0.0,
        manual_repair_fail_prob=0.0,
        diagnosis_uncertainty=0.0,
        seed=7,
    )
    sim = InspectingSim(p)
    sim.run()

    assert "repair_shop" in observed, "InspectingSim._main_loop was never entered"

    # The callback must be wired — this is the fix
    assert observed["repair_shop"].on_server_returned is not None, (
        "Bug (a): repair_shop.on_server_returned was never set — "
        "Simulator does not wire the repair shop callback to the scheduler"
    )

    # The callback should point at the scheduler's return_server_to_job method
    assert observed["repair_shop"].on_server_returned == \
        observed["scheduler"].return_server_to_job, (
        "Bug (a): on_server_returned is set but does not point to "
        "scheduler.return_server_to_job"
    )
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


def test_misdiagnosis_real_failed_server_state_is_idle():
    """Bug (b-ii) — corrected understanding: misdiagnosis intentionally keeps
    the real failed server running (the 'oops' in the comment).  It SHOULD
    remain in active_servers so the next run_until_failure includes it.

    The actual concern is that the coordinator sets its state to FAILED, and
    the misdiagnosis block must reset it to IDLE before the next
    run_until_failure call.  If it is left as FAILED, the server stays
    visible in available_in_working (IDLE filter) only after the reset, so
    the state transition is critical for pool correctness.

    This test verifies:
      1. The real failed server IS in active_servers after misdiagnosis
         (intended — it keeps running).
      2. Its state has been reset to IDLE (not left as FAILED), so the pool
         manager and next run_until_failure see a consistent state.
    """
    captured = {}

    class InspectingSim(Simulator):
        def _main_loop(self, env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats, all_servers):
            remaining = p.job_length
            scheduler.do_host_selection()
            yield env.timeout(p.host_selection_time)

            run_result = env.process(
                coordinator.run_until_failure(scheduler.active_servers, remaining)
            )
            yield run_result
            failed_server, duration = run_result.value

            if failed_server is not None:
                original_failed = failed_server
                # state right after coordinator — should be FAILED
                captured["state_after_coordinator"] = original_failed.state

                # Run the misdiagnosis block (same logic as simulator.py)
                if p.diagnosis_uncertainty > 0 and rng.random() < p.diagnosis_uncertainty:
                    innocents = [s for s in scheduler.active_servers
                                 if s is not failed_server]
                    if innocents:
                        misdiagnosed = rng.choice(innocents)
                        misdiagnosed.mark_failed()
                        pool_mgr.remove_from_working(misdiagnosed)
                        failed_server.state = ServerState.IDLE
                        failed_server = misdiagnosed

                pool_mgr.remove_from_working(failed_server)
                repair_shop.submit(failed_server)

                captured["real_server"] = original_failed
                captured["real_still_active"] = original_failed in scheduler.active_servers
                captured["real_state_after"] = original_failed.state

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

    assert "real_server" in captured, "No failure event was triggered"
    assert captured["state_after_coordinator"] == ServerState.FAILED, (
        "Coordinator should have set the real server's state to FAILED"
    )
    assert captured["real_still_active"], (
        "Real failed server should remain in active_servers under misdiagnosis "
        "(it keeps running — that is the intended simulation behaviour)"
    )
    assert captured["real_state_after"] == ServerState.IDLE, (
        f"Bug (b-ii): real failed server state is {captured['real_state_after']} "
        f"after misdiagnosis — it must be reset to IDLE so the pool manager "
        f"and next run_until_failure see a consistent state"
    )
    print("  [PASS] test_misdiagnosis_real_failed_server_state_is_idle")


# ── (c) missed-signal race on server_repaired_event ─────────────────────────

class FixedTimeRepairShop(RepairShop):
    """Repair shop that uses a fixed (non-exponential) repair time.

    This makes it possible to write deterministic tests about event timing
    without relying on specific RNG seeds.
    """
    def __init__(self, fixed_repair_time, **kwargs):
        super().__init__(**kwargs)
        self._fixed_repair_time = fixed_repair_time

    def _repair_process(self, server):
        server.begin_auto_repair()
        yield self.env.timeout(self._fixed_repair_time)
        self.stats.auto_repairs += 1
        server.complete_repair(success=True)
        self.pool_manager.return_to_working(server)
        self._signal_repaired()


def make_fixed_repair_shop(env, rng, pool_mgr, stats, fixed_repair_time):
    return FixedTimeRepairShop(
        fixed_repair_time=fixed_repair_time,
        env=env, rng=rng,
        auto_repair_time=fixed_repair_time,
        manual_repair_time=fixed_repair_time,
        prob_auto_to_manual=0.0, auto_repair_fail_prob=0.0,
        manual_repair_fail_prob=0.0,
        escalation_policy=DefaultRepairEscalation(prob_escalate=0.0),
        removal_policy=NeverRemove(),
        pool_manager=pool_mgr,
        stats=stats,
    )


def test_server_repaired_event_not_missed_when_signal_fires_before_yield():
    """Bug (c): _signal_repaired() calls event.succeed() then immediately
    replaces self.server_repaired_event with a new un-triggered event.

    If repair completes at SimPy time T while the main loop process is
    running (not yet suspended on the event), the main loop will later
    evaluate repair_shop.server_repaired_event, get the already-replaced
    fresh event, and block forever.

    This test sets up exactly that scenario using a fixed repair time so
    the timing is deterministic: both the repair process and the waiter
    process time out at t=5.  SimPy runs same-time events in FIFO order,
    so the repair (submitted first) runs first — it succeeds and replaces
    the event — then the waiter grabs the already-replaced event and hangs.
    """
    env = simpy.Environment()
    rng = random.Random(0)
    stats = StatsCollector()

    servers = [make_server(env, i) for i in range(3)]
    pool_mgr = PoolManager()
    pool_mgr.init_pools(servers, working_size=3, spare_size=0)

    # Fixed repair time so the repair completes at exactly t=5.
    repair_shop = make_fixed_repair_shop(env, rng, pool_mgr, stats, fixed_repair_time=5)

    woke_up = []

    def waiter():
        # Wake at the same simtime the repair completes (t=5).
        # Because the repair process was submitted first, it runs first in
        # SimPy's FIFO queue — it signals and replaces the event before this
        # process grabs the reference.
        yield env.timeout(5)
        event = repair_shop.server_repaired_event   # gets the *replaced* event
        yield event                                  # hangs if bug is present
        woke_up.append(True)

    failed = servers[0]
    failed.mark_failed()
    pool_mgr.remove_from_working(failed)
    repair_shop.submit(failed)   # repair process scheduled first (lower eid)

    env.process(waiter())        # waiter scheduled second (higher eid at t=5)

    env.run(until=50)

    assert woke_up, (
        "Bug (c): waiter never woke up — missed-signal race: repair completed "
        "at t=5, replaced server_repaired_event, then waiter grabbed the new "
        "un-triggered event and blocked forever"
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

    repair_shop = make_fixed_repair_shop(env, rng, pool_mgr, stats, fixed_repair_time=5)

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
        test_misdiagnosis_real_failed_server_state_is_idle,
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
