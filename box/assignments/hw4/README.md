# HW4: list utilities

Implement the four functions in `hw4.py` without changing the input lists.
Run `python -m pytest -q` in this directory to check your work.

- `last_n(xs, n)` returns the final `n` items, in order. Return `[]` when
  `n <= 0`; return all items when `n` exceeds the list length.
- `pairwise_sums(xs)` returns sums of adjacent items. For example,
  `[2, 4, 7]` becomes `[6, 11]`. A list with fewer than two items gives `[]`.
- `chunk(xs, size)` splits a list into consecutive lists of at most `size`
  items. Keep the final partial chunk. Raise `ValueError` if `size <= 0`.
- `safe_max(xs)` returns the largest item. In this version of the assignment,
  an empty list **raises `ValueError`**.

Pay attention to empty inputs and the last index of a list.
