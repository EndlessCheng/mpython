import sys
from functools import partial


class MASM:
    TAB = ' ' * 4

    def __init__(self, output_file=sys.stdout):
        self.printf = partial(print, file=output_file)
        self.batch = []

    def newline(self):
        self.printf()

    def flush(self):
        for s in self.batch:
            self.printf(f"{MASM.TAB}{s}")
        self.batch = []

    def add_assume(self, cs_segment='code', ds_segment='data'):
        self.printf(f'assume cs:{cs_segment}, ds:{ds_segment}')
        self.newline()

    def add_segment_header(self, name):
        self.printf(f'{name} segment')

    def add_segment_footer(self, name):
        self.flush()
        self.printf(f'{name} ends')
        self.newline()

    def add_data(self, data):
        self.printf(f"{MASM.TAB}{data}")

    def add_label(self, label):
        self.flush()
        self.printf(f'{label.name}:')

    def add_code(self, code):
        self.batch.append(str(code))

    def add_end(self, entry='start'):
        """
        告知程序的入口
        """
        self.printf(f'end {entry}')


class Data:
    def __init__(self, name=None, op='db', args=None):
        self.name = name
        self.op = op
        self.args = args or ('?',)

        for arg in self.args:
            if isinstance(arg, int):
                assert arg <= 0xff, "data arg must <= 0xff"

        self.ins = self._str()

    def _str(self):
        new_args = [f"'{a}'" if isinstance(a, str) else f'{a:02x}h' for a in self.args]
        ins = f"{self.op} {', '.join(new_args)}"
        if self.name:
            ins = f'{self.name} {ins}'
        return ins

    def __str__(self):
        return self.ins


class Label:
    def __init__(self, name):
        self.name = name


class Code:
    def __init__(self, op, *args):
        for arg in args:
            if isinstance(arg, int):
                assert arg <= 0xffff, "code arg must <= 0xffff"

        self.op = op
        self.args = args

        self.ins = self._str()

    def _str(self):
        ins = self.op
        if self.args:
            new_args = map(str, self.args)
            ins += ' ' + ', '.join(new_args)
        return ins

    def __str__(self):
        return self.ins


# -----------------------------------------------
# 数据传送指令
#

class Mov(Code):
    """
    传送

    mem, reg  9 + EA
    reg, mem  8 + EA
    reg, reg  2

    reg, imm  4
    mem, imm

    seg, reg
    seg, mem
    mem, seg
    reg, seg

    mem, acc
    acc, mem
    """

    def __init__(self, dst, src):
        super().__init__('mov', dst, src)


# TODO: 栈溢出？
class Push(Code):
    """
    进栈

    reg  11
    seg
    mem
    """

    def __init__(self, src):
        super().__init__('push', src)


class Pop(Code):
    """
    出栈

    reg  8
    seg
    mem
    """

    def __init__(self, dst):
        super().__init__('pop', dst)


# -----------------------------------------------
# 算数运算指令
#

class Add(Code):
    """
    加法

    mem, reg
    reg, mem
    reg, reg  3
    reg, imm
    mem, imm
    acc, imm
    """

    def __init__(self, dst, src):
        super().__init__('add', dst, src)


class Sub(Code):
    """
    减法

    mem, reg
    reg, mem
    reg, reg  3
    reg, imm
    mem, imm
    acc, imm
    """

    def __init__(self, dst, src):
        super().__init__('sub', dst, src)


class Mul(Code):
    """
    无符号数乘法

    8 位 reg   70 ~ 77
    8 位 mem
    16 位 reg  118 ~ 133
    16 位 mem
    """

    def __init__(self, src):
        super().__init__('mul', src)


class Div(Code):
    """
    无符号数除法

    8 位 reg   101 ~ 112
    8 位 mem
    16 位 reg  164 ~ 184
    16 位 mem
    """

    def __init__(self, src):
        super().__init__('div', src)


# -----------------------------------------------
# 逻辑运算指令
#

class And(Code):
    """
    逻辑与

    mem, reg
    reg, mem
    reg, reg  3
    reg, imm
    mem, imm
    acc, imm
    """

    def __init__(self, dst, src):
        super().__init__('and', dst, src)


class Or(Code):
    """
    逻辑或

    mem, reg
    reg, mem
    reg, reg  3
    reg, imm
    mem, imm
    acc, imm
    """

    def __init__(self, dst, src):
        super().__init__('or', dst, src)


class Xor(Code):
    """
    逻辑异或

    mem, reg
    reg, mem
    reg, reg  3
    reg, imm
    mem, imm
    acc, imm
    """

    def __init__(self, dst, src):
        super().__init__('xor', dst, src)


# -----------------------------------------------
# 控制与转移指令
#

class Int(Code):
    """
    中断调用

    n != 3  51
    n == 3  52
    """

    def __init__(self, n):
        super().__init__('int', n)


# -----------------------------------------------
# 处理机控制指令
#

class Nop(Code):
    """
    无操作

    3
    """

    def __init__(self):
        super().__init__('nop')


class Hlt(Code):
    """
    停机
    """

    def __init__(self):
        super().__init__('hlt')
