def gcd(x, y):
    """
    x, y 的最大公约数
    """

    if y == 0:
        return x
    return gcd(y, x % y)


def main():
    g = gcd(42, 70)
    putchar(g + 97)
