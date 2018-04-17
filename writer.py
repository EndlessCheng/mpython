from functools import partial
import sys

from optimize import optimize_batch


class MasmWriter:
    TAB = ' ' * 4

    def __init__(self, output_file=sys.stdout, optimize=True):
        self.printf = partial(print, file=output_file)
        self.optimize = optimize

        self.batch = []

    def newline(self):
        self.printf()

    def flush(self):
        if self.optimize:
            self.batch = optimize_batch(self.batch)

        for s in self.batch:
            self.printf(f"{MasmWriter.TAB}{s}")
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
        self.printf(f"{MasmWriter.TAB}{data}")

    def add_label(self, label):
        self.flush()
        self.printf(f'{label}:')

    def add_code(self, code):
        self.batch.append(code)

    def add_end(self, entry='start'):
        """
        告知程序的入口
        """
        self.printf(f'end {entry}')
