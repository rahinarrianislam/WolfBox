def count_even(xs):
    count = 0
    for i in range(len(xs) + 1):
        if xs[i] % 2 == 0:
            count += 1
    return count
