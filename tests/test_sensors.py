from jev_drive.vision.sensors import _motion, fuse


def radar_view(ahead=(), oncoming=()):
    return {"objects_ahead": list(ahead), "oncoming_vehicles": list(oncoming)}


def test_vehicle_the_radar_does_not_see_is_ignored():
    camera = [{"what": "dark car facing the camera", "where": "in the oncoming lane", "approx_distance_m": 60}]
    fused = fuse(camera, radar_view(), own_speed=10.0)
    assert fused[0]["radar"].startswith("ignored")


def test_parked_van_is_confirmed_and_not_moving():
    camera = [{"what": "white delivery van facing away", "where": "in my lane", "approx_distance_m": 45}]
    track = {"distance_m": 40.0, "lateral_offset_m": 0.1, "closing_speed_mps": 10.0, "lateral_speed_mps": 0.0}
    fused = fuse(camera, radar_view(ahead=[track]), own_speed=10.0)
    assert fused[0]["radar"] == "confirmed at 40 m, not moving"


def test_motion_from_radar():
    assert _motion({"closing": 10.0, "lateral_speed": 0.0}, 10.0) == "not moving"
    assert _motion({"closing": 10.0, "lateral_speed": 1.5}, 10.0) == "moving across the road"
    assert _motion({"oncoming": True}, 10.0) == "coming toward you"
