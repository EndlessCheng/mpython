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
        self.op = op
        self.args = args

        self.ins = self._str()

    def _str(self):
        ins = self.op
        if self.args:
            new_args = [a if isinstance(a, str) else f'{a:02x}h' for a in self.args]
            ins += ' ' + ', '.join(new_args)
        return ins

    def __str__(self):
        return self.ins


class Mov(Code):
    def __init__(self, reg, data):
        super().__init__('mov', reg, data)


class Int(Code):
    def __init__(self, num):
        super().__init__('int', num)


# TODO: 栈溢出？
class Push(Code):
    def __init__(self, src):
        super().__init__('push', src)


class Pop(Code):
    def __init__(self, dst):
        super().__init__('pop', dst)
