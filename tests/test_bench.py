from jev_drive.vision.bench import classify, iou, match, score
from jev_drive.vision.dataset import motion, where
from jev_drive.world import LANE_W


def test_classify_common_descriptions():
    assert classify("white delivery van facing away") == "vehicle"
    assert classify("a child running toward the road") == "person"
    assert classify("deer standing side-on") == "animal"
    assert classify("fallen tree branch with leaves") == "object"
    assert classify("a shadow") == "other"


def test_iou():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def test_match_needs_same_class_and_overlap():
    truth = [{"class": "vehicle", "where": "in my lane", "distance_m": 30, "box_2d": [400, 400, 600, 600]}]
    good = [{"what": "a parked van", "where": "in my lane", "approx_distance_m": 31, "box_2d": [410, 410, 590, 600]}]
    wrong_class = [{"what": "a person", "where": "in my lane", "approx_distance_m": 30, "box_2d": [400, 400, 600, 600]}]
    assert match(good, truth) == [(0, 0)]
    assert match(wrong_class, truth) == []


def test_score_counts_misses_and_false_objects():
    rows = [{"frame": "a.jpg", "objects": [
        {"class": "person", "where": "in my lane", "distance_m": 20, "box_2d": [400, 450, 600, 520]}]}]
    predictions = {"a.jpg": {"frame": "a.jpg", "error": None, "latency_ms": 10,
                             "objects": [{"what": "a car", "where": "in the oncoming lane", "approx_distance_m": 90}]}}
    result = score(rows, predictions, "test", 0.0)
    assert result["recall"] == 0.0
    assert result["path_recall"] == 0.0
    assert result["false_vehicles_per_frame"] == 1.0


def test_ground_truth_lanes_and_motion():
    assert where(-0.9, 0.9) == "in my lane"
    assert where(LANE_W - 0.9, LANE_W + 0.9) == "in the oncoming lane"
    assert where(0.5, LANE_W + 0.5) == "across both lanes"
    assert where(-3.0, -2.2) == "right sidewalk at the curb"
    assert motion(0.0, 0.0) == "not moving"
    assert motion(0.0, 1.2) == "moving across the road"
