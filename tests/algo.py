def gcd(x, y):
    """
    x, y 的最大公约数
    """

    if y == 0:
        return x
    return gcd(y, x % y)


def main():
    g1 = gcd(42, 70)
    g2 = gcd(5, 3)
    putchar(g1 + g2 + 97)
