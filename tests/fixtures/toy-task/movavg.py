# Toy task for the harness smoke tests (MIT, ZHarvett).
"""Moving average of a list of numbers."""


def moving_average(values, window):
    """Return the mean of every run of `window` consecutive values."""
    out = []
    for i in range(len(values) - window):
        out.append(sum(values[i : i + window]) / window)
    return out
