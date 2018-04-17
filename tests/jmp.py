def foo(a, b):
    xx = 5
    return a - b + xx


def main():
    # a = 1 << 2
    # if a == 2:
    #     print('aaa')
    # # elif not (a == 1):
    # #     print('wow')
    # else:
    #     print('bbb')

    # for i in range(10):
    #     for j in range(10):
    #         if j > 1:
    #             continue
    #         print('aaa')

    a = 97
    b = 99
    putchar(a)
    putchar(b)

    ret = foo(b, a)

    putchar(a)
    putchar(b)

    ret += 97

    putchar(a)
    putchar(b)

    putchar(ret)
