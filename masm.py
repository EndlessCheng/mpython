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
        self.printf(f'{label}:')

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
            # 需要注意的是，立即数不能以字母开头。为方便起见，就不转换成 16 进制了
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
        if isinstance(src, str) and src[0] == '[':
            assert src[-1] == ']'
            # mov dst, [imm] 的含义与 mov dst, imm 相同。为方便起见，在 [] 前显式地加上段前缀 ds:
            src = 'ds:' + src
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


class Inc(Code):
    """
    加 1

    reg  2 ~ 3
    mem
    """

    def __init__(self, opr):
        super().__init__('inc', opr)


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


class Dec(Code):
    """
    减 1

    reg  2 ~ 3
    mem
    """

    def __init__(self, opr):
        super().__init__('dec', opr)


class Cmp(Code):
    """
    比较

    reg, reg 3
    reg, imm 4
    mem, imm
    """

    def __init__(self, opr1, opr2):
        super().__init__('cmp', opr1, opr2)


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


class Not(Code):
    """
    逻辑非

    reg  3
    mem
    """

    def __init__(self, opr):
        super().__init__('not', opr)


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


class _Shift(Code):
    def __init__(self, shift_cmd, opr, cnt):
        self.shift_cmd = shift_cmd
        self.opr = opr
        self.cnt = cnt
        super().__init__(shift_cmd, opr, cnt)

    def gen_codes(self):
        assert isinstance(self.cnt, int), "cnt should be int"
        if self.cnt == 1:
            return [self]
        mov = Mov('cl', self.cnt)
        shift_cmd = Code(self.shift_cmd, self.opr, 'cl')
        return [mov, shift_cmd]


class Sal(_Shift):
    """
    算术左移

    1  reg  2
       mem
    CL reg  8
       mem
    """

    def __init__(self, opr, cnt):
        super().__init__('sal', opr, cnt)


class Sar(_Shift):
    """
    算术右移

    1  reg  2
       mem
    CL reg  8
       mem
    """

    def __init__(self, opr, cnt):
        super().__init__('sar', opr, cnt)


# -----------------------------------------------
# 控制与转移指令
#

class Jmp(Code):
    """
    无条件转移

    reg
    mem
    """
    SHORT = 'short'
    NEAR_PTR = 'near ptr'
    WORD_PTR = 'word ptr'
    FAR_PTR = 'far ptr'
    DWORD_PTR = 'dword ptr'

    _DISTANCE_LIST = [SHORT, NEAR_PTR, WORD_PTR, FAR_PTR, DWORD_PTR]

    def __init__(self, *args):
        assert 1 <= len(args) <= 2
        distance = args[0] if len(args) == 2 else ''
        opr = args[1] if len(args) == 2 else args[0]
        assert not distance or distance.lower() in Jmp._DISTANCE_LIST, f"wrong distance {distance}"
        if distance:
            distance += ' '
        super().__init__('jmp', f'{distance}{opr}')


class Jz(Code):
    """
    结果为 0（或相等）则转移

    ZF = 1 则转移到 opr

    16/4
    """

    def __init__(self, opr):
        super().__init__('jz', opr)


Je = Jz


class Jnz(Code):
    """
    结果不为 0（或不相等）则转移

    ZF = 0 则转移到 opr

    16/4
    """

    def __init__(self, opr):
        super().__init__('jnz', opr)


Jne = Jnz


class Jb(Code):
    """
    低于则转移

    CF = 1 且 ZF = 0 则转移到 opr

    16/4
    """

    def __init__(self, opr):
        super().__init__('jb', opr)


Jnae = Jb


class Jbe(Code):
    """
    低于等于则转移

    CF = 1 或 ZF = 1 则转移到 opr

    16/4
    """

    def __init__(self, opr):
        super().__init__('jbe', opr)


Jna = Jbe


class Ja(Code):
    """
    高于则转移

    CF = 0 且 ZF = 0 则转移到 opr

    16/4
    """

    def __init__(self, opr):
        super().__init__('ja', opr)


Jnbe = Ja


class Jae(Code):
    """
    高于等于则转移

    CF = 0 或 ZF = 1 则转移到 opr

    16/4
    """

    def __init__(self, opr):
        super().__init__('jae', opr)


Jnb = Jae


class Call(Code):
    """
    子程序调用

    reg
    mem
    """

    def __init__(self, dst):
        super().__init__('call', dst)


class Ret(Code):
    """
    子程序返回

    近转移，返回到 call 的下一行命令
    有 exp 时栈指针加 exp

    无 exp  16
    有 exp  20
    """

    def __init__(self, exp=None):
        if exp is None:
            super().__init__('ret')
        else:
            super().__init__('ret', exp)


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
