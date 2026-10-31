import pytest
from hw4 import chunk, last_n, pairwise_sums, safe_max


def test_last_n():
    assert last_n([1, 2, 3, 4], 2) == [3, 4]
    assert last_n([1, 2], 8) == [1, 2]
    assert last_n([1, 2], 0) == []
    assert last_n([1, 2], -1) == []


def test_pairwise_sums():
    assert pairwise_sums([2, 4, 7]) == [6, 11]


def test_last_index():
    assert last_n([10, 20, 30], 1) == [30]


def test_chunk():
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    with pytest.raises(ValueError):
        chunk([1], 0)
    with pytest.raises(ValueError):
        chunk([1], -2)


def test_safe_max():
    assert safe_max([-5, -2, -9]) == -2
    xs = [3, 1, 2]
    assert safe_max(xs) == 3
    assert xs == [3, 1, 2]


def test_empty():
    assert last_n([], 3) == []
    assert pairwise_sums([]) == []
    assert pairwise_sums([1]) == []
    assert chunk([], 2) == []
    with pytest.raises(ValueError):
        safe_max([])
