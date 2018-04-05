import sys
from functools import partial


class MASM:
    TAB = ' ' * 4

    def __init__(self, output_file=sys.stdout):
        self.printf = partial(print, file=output_file)
        self.batch = []

    def flush(self):
        for s in self.batch:
            self.printf(f"{MASM.TAB}{s}")
        self.batch = []

    def add_segment_header(self, name):
        self.flush()
        self.printf(f'{name} segment')

    def add_segment_footer(self, name):
        self.flush()
        self.printf(f'{name} ends')

    def add_data(self, data):
        self.printf(f"{MASM.TAB}{data}")

    def add_assume(self, ds_segment='data', cs_segment='code'):
        self.flush()
        self.printf(f'assume cs:{cs_segment}, ds:{ds_segment}')

    def add_label(self, label):
        self.flush()
        self.printf(f'{label.name}:')

    def add_code(self, code):
        self.batch.append(str(code))

    def add_end(self, name='start'):
        self.flush()
        self.printf(f'end {name}')


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
