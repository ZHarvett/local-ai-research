# Toy task for the harness smoke tests (MIT, ZHarvett).
from movavg import moving_average


def test_moving_average_covers_every_window():
    assert moving_average([1, 2, 3, 4], 2) == [1.5, 2.5, 3.5]
