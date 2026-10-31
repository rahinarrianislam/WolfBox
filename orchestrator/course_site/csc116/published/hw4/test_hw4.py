import pytest
from hw4 import last_n, pairwise_sums, chunk, safe_max

def test_last_index():
    assert last_n([1, 2, 3], 1) == [3]

def test_pairwise():
    assert pairwise_sums([1, 2, 3]) == [3, 5]

def test_chunk():
    assert chunk([1, 2, 3], 2) == [[1, 2], [3]]

def test_empty():
    with pytest.raises(ValueError):
        safe_max([])

def test_max():
    assert safe_max([1, 5, 3]) == 5
