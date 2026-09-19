from jev_drive.planners import RulePlanner
from jev_drive.world import World, stop_gap


def quiet_world(seed: int = 3) -> World:
    world = World(seed=seed, spawning=False, first_hazard_s=1e9, oncoming_headway_s=1e9)
    world.oncoming.clear()
    return world


def run(world: World, seconds: float, each_step=None) -> None:
    for _ in range(int(seconds * 30)):
        world.step()
        if each_step:
            each_step(world)


def test_stops_behind_a_stopped_van():
    world = quiet_world()
    van = world.spawn_hazard("van", distance=60, sudden=False)
    world.command("stop", "test")
    run(world, 20)
    gap = van.rear - world.ego.front
    assert world.ego.vx < 0.3
    assert stop_gap(van) - 3 < gap < stop_gap(van) + 6
    assert world.stats["crashes"] == 0


def test_overtakes_a_stopped_van_and_returns_to_lane():
    world = quiet_world()
    van = world.spawn_hazard("van", distance=40, sudden=False)
    world.command("overtake", "test")
    run(world, 25)
    assert world.ego.front > van.front
    assert abs(world.ego.y) < 0.3
    assert world.stats["overtakes"] >= 1
    assert world.stats["crashes"] == 0


def test_finishes_the_pass_when_a_car_appears_alongside():
    world = quiet_world()
    van = world.spawn_hazard("van", distance=12, sudden=False)
    world.ego.vx = 0
    world.command("overtake", "test")

    def oncoming_while_alongside(w: World) -> None:
        if w.ego.phase == "pass" and not w.oncoming and w.ego.front > van.rear:
            w._spawn_oncoming(w.ego.x + 30)

    run(world, 30, oncoming_while_alongside)
    assert world.stats["crashes"] == 0
    assert world.ego.front > van.front


def test_rule_driver_survives_a_busy_road():
    world = World(seed=11, oncoming_headway_s=12.0, hazard_gap_s=(6.0, 10.0))
    rules = RulePlanner()
    next_decision = 0.0

    def decide(w: World) -> None:
        nonlocal next_decision
        if w.t >= next_decision:
            choice = rules.choose(w)
            if choice != w.ego.maneuver:
                w.command(choice, "rules")
            next_decision = w.t + 0.5

    run(world, 120, decide)
    assert world.stats["hazards"] > 5
    assert world.stats["crashes"] == 0
