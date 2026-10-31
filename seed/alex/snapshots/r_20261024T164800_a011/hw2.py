def count_even(xs):
    return sum(1 for value in xs if value % 2 == 0)
