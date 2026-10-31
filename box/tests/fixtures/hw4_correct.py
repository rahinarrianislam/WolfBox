def last_n(xs, n):
    return xs[-n:] if n > 0 else []


def pairwise_sums(xs):
    return [xs[i] + xs[i + 1] for i in range(len(xs) - 1)]


def chunk(xs, size):
    if size <= 0:
        raise ValueError("size must be positive")
    return [xs[i : i + size] for i in range(0, len(xs), size)]


def safe_max(xs):
    return max(xs)
