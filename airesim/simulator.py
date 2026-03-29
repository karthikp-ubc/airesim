"""Top-level simulator — wires all modules together.

This is the main orchestration loop that implements Figure 1 from the paper:
  Job (Re)Start → Server Failed → Server sent to Repair → ...
  ↓ Host Selection ← Spares Available? → Wait for repairs
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import simpy

from airesim.params import Params
from airesim.server import Server, ServerState
from airesim.coordinator import Coordinator
from airesim.scheduler import Scheduler
from airesim.repairs import RepairShop
from airesim.pool import PoolManager
from airesim.stats import StatsCollector
from airesim.policies import (
    DefaultHostSelection,
    DefaultRepairEscalation,
    NeverRemove,
    HostSelectionPolicy,
    RepairEscalationPolicy,
    ServerRemovalPolicy,
)


class Simulator:
    """Top-level DES orchestrator for AIReSim.

    Usage::

        sim = Simulator(params)
        result = sim.run()
    """

    def __init__(
        self,
        params: Params,
        host_selection_policy: HostSelectionPolicy | None = None,
        escalation_policy: RepairEscalationPolicy | None = None,
        removal_policy: ServerRemovalPolicy | None = None,
        seed: int | None = None,
    ):
        self.params = params
        self.params.validate()

        self.host_selection_policy = host_selection_policy or DefaultHostSelection()
        self.escalation_policy = escalation_policy or DefaultRepairEscalation(
            prob_escalate=params.prob_auto_to_manual
        )
        self.removal_policy = removal_policy or NeverRemove()
        self.seed = seed if seed is not None else params.seed

    def run(self) -> StatsCollector:
        """Execute one simulation run and return collected statistics."""
        # Reset any per-run state in the removal policy (e.g. ScoredRemoval's
        # score dict) so repeated calls with the same policy object produce
        # independent replications instead of carrying over stale scores.
        self.removal_policy.reset()
        rng = random.Random(self.seed)
        env = simpy.Environment()
        stats = StatsCollector()
        p = self.params

        # ── Create servers ───────────────────────────────────────────────
        total_servers = p.working_pool_size + p.spare_pool_size
        num_bad = int(total_servers * p.systematic_failure_fraction)

        all_servers = []
        for i in range(total_servers):
            is_bad = i < num_bad  # first num_bad servers are "bad"
            s = Server(
                server_id=i,
                env=env,
                is_bad=is_bad,
                random_failure_rate=p.random_failure_rate,
                systematic_failure_rate=p.systematic_failure_rate,
            )
            all_servers.append(s)

        # Shuffle so bad servers are distributed randomly
        rng.shuffle(all_servers)

        # ── Initialize pools ─────────────────────────────────────────────
        pool_mgr = PoolManager()
        pool_mgr.init_pools(all_servers, p.working_pool_size, p.spare_pool_size)

        # ── Create components ────────────────────────────────────────────
        coordinator = Coordinator(
            env, stats, rng,
            failure_distribution=p.failure_distribution,
            weibull_shape=p.weibull_shape,
            lognormal_sigma=p.lognormal_sigma,
        )
        scheduler = Scheduler(
            env=env,
            rng=rng,
            job_size=p.job_size,
            warm_standby_count=p.warm_standbys,
            host_selection_time=p.host_selection_time,
            host_selection_policy=self.host_selection_policy,
            pool_manager=pool_mgr,
            stats=stats,
        )
        repair_shop = RepairShop(
            env=env,
            rng=rng,
            auto_repair_time=p.auto_repair_time,
            manual_repair_time=p.manual_repair_time,
            prob_auto_to_manual=p.prob_auto_to_manual,
            auto_repair_fail_prob=p.auto_repair_fail_prob,
            manual_repair_fail_prob=p.manual_repair_fail_prob,
            escalation_policy=self.escalation_policy,
            removal_policy=self.removal_policy,
            pool_manager=pool_mgr,
            stats=stats,
        )
        # Wire the repair shop to the scheduler so repaired servers are
        # offered back as warm standbys mid-job (fix for bug a).
        repair_shop.on_server_returned = scheduler.return_server_to_job

        # ── Start the main simulation process ────────────────────────────
        env.process(self._main_loop(env, rng, p, coordinator, scheduler, repair_shop, pool_mgr, stats, all_servers))

        # Optionally: bad-server regeneration process
        if p.bad_server_regeneration:
            env.process(self._bad_server_regen(env, rng, p, all_servers))

        # Run the simulation
        env.run()

        stats.preemption_count = pool_mgr.preemption_count
        return stats

    def _main_loop(
        self,
        env: simpy.Environment,
        rng: random.Random,
        p: Params,
        coordinator: Coordinator,
        scheduler: Scheduler,
        repair_shop: RepairShop,
        pool_mgr: PoolManager,
        stats: StatsCollector,
        all_servers: list[Server],
    ):
        """Main simulation loop implementing the paper's Figure 1 flowchart."""
        remaining_job_time = p.job_length

        while remaining_job_time > 0:
            # ── Host Selection ───────────────────────────────────────────
            success = scheduler.do_host_selection()

            if not success:
                # Not enough servers — try pulling from spare pool
                while len(pool_mgr.available_in_working) < p.total_servers_needed:
                    if pool_mgr.spare_pool:
                        yield env.timeout(p.preemption_wait_time)
                        stats.total_wait_time += p.preemption_wait_time
                        moved = pool_mgr.move_spare_to_working()
                    else:
                        # No spares — stall and wait for repair.
                        # Check triggered before yielding to avoid the missed-
                        # signal race: if a repair completed while the main
                        # loop was running (not suspended), server_repaired_event
                        # is already triggered and we must not wait on the
                        # already-fired event.  We own the event lifecycle and
                        # reset it here after waking (fix for bug c).
                        stats.job_stall_count += 1

                        # Depletion guard: if server retirements have permanently
                        # reduced the total non-retired pool below the minimum
                        # needed, no amount of waiting will unblock the job.
                        total_active = sum(
                            1 for s in all_servers
                            if s.state != ServerState.RETIRED
                        )
                        if total_active < p.total_servers_needed:
                            stats.cluster_depleted = True
                            stats.total_training_time = env.now
                            return  # exit the SimPy generator

                        if not repair_shop.server_repaired_event.triggered:
                            yield repair_shop.server_repaired_event
                        repair_shop.server_repaired_event = env.event()
                        # Re-check availability after a server returns
                        continue

                # Retry host selection
                success = scheduler.do_host_selection()
                if not success:
                    # Still not enough — this shouldn't happen, but be safe
                    stats.job_stall_count += 1
                    yield env.timeout(1)
                    continue

            # Host selection delay
            yield env.timeout(p.host_selection_time)
            stats.total_host_selection_time += p.host_selection_time

            # ── Job execution loop (using warm standbys) ─────────────────
            while remaining_job_time > 0:
                # Run until either a failure or the remaining job time elapses
                run_result = env.process(
                    coordinator.run_until_failure(
                        scheduler.active_servers, remaining_job_time
                    )
                )
                yield run_result

                failed_server, compute_duration = run_result.value
                remaining_job_time -= compute_duration
                stats.total_compute_time += compute_duration

                if failed_server is None:
                    # Job completed without failure — credit all active servers
                    for s in scheduler.active_servers:
                        self.removal_policy.on_success(s, compute_duration)
                    break

                if remaining_job_time <= 0:
                    break

                # Credit servers that ran successfully this chunk (all except
                # the failed one, which gets penalised after blame resolution).
                for s in scheduler.active_servers:
                    if s is not failed_server:
                        self.removal_policy.on_success(s, compute_duration)

                # ── Handle failure ───────────────────────────────────────
                # Apply diagnosis uncertainty — might blame wrong server
                if p.diagnosis_uncertainty > 0 and rng.random() < p.diagnosis_uncertainty:
                    # Wrong server identified — pick a random active server instead
                    innocents = [s for s in scheduler.active_servers if s is not failed_server]
                    if innocents:
                        misdiagnosed = rng.choice(innocents)
                        # The misdiagnosed server gets sent to repair instead.
                        # Mark it failed and remove it from the pool, then rebind
                        # failed_server so the unconditional submit below handles it.
                        # Do NOT call repair_shop.submit() here — the block below
                        # does the single authoritative submit (fix for bug b-i).
                        misdiagnosed.mark_failed()
                        pool_mgr.remove_from_working(misdiagnosed)
                        # The actual bad server stays running (oops — misdiagnosis)
                        failed_server.state = ServerState.IDLE
                        failed_server = misdiagnosed

                # Send the blamed server (real or misdiagnosed) to repair.
                # remove_from_working is idempotent, so the misdiagnosis case
                # (server already removed above) is safe.
                pool_mgr.remove_from_working(failed_server)
                self.removal_policy.on_failure(failed_server)
                repair_shop.submit(failed_server)

                # Recovery time (loading checkpoint)
                yield env.timeout(p.recovery_time)
                stats.total_recovery_time += p.recovery_time

                # Try warm standby swap
                replacement = scheduler.swap_in_standby(failed_server)

                if replacement is not None:
                    # Continue running with the replacement — no host selection needed
                    continue
                else:
                    # Out of warm standbys — need full host selection
                    break  # break to outer loop for host selection

        # ── Job complete ─────────────────────────────────────────────────
        stats.total_training_time = env.now

    def _bad_server_regen(
        self,
        env: simpy.Environment,
        rng: random.Random,
        p: Params,
        all_servers: list[Server],
    ):
        """Periodically regenerate bad servers (model aging / new hardware)."""
        while True:
            yield env.timeout(p.bad_server_regen_interval)
            # Pick some good servers and make them bad
            good_servers = [s for s in all_servers if not s.is_bad and s.state != ServerState.RETIRED]
            if good_servers:
                num_to_convert = max(1, int(len(good_servers) * p.systematic_failure_fraction * 0.1))
                for s in rng.sample(good_servers, min(num_to_convert, len(good_servers))):
                    s.make_bad()
