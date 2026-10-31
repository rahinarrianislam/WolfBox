from hw5 import word_counts

def test_words():
    assert word_counts("Hi hi wolf") == {"hi": 2, "wolf": 1}

def test_empty():
    assert word_counts("") == {}
