import argparse
import ast
import os
import sys

import masm


class Compiler:
    """
    The main Python AST -> MASM compiler.
    """

    def __init__(self, output_file=sys.stdout):
        self.asm = masm.MASM(output_file)

        self.data = []
        self.codes = []

    def compile(self, node):
        self.before_visit()
        self.visit(node)
        self.after_visit()

        self.gen_result()

    def before_visit(self):
        pass

    def after_visit(self):
        self.add_exit()

    def gen_result(self):
        self.asm.add_segment_header('data')
        for d in self.data:
            self.asm.add_data(d)
        self.asm.add_segment_footer('data')

        self.asm.add_segment_header('code')
        self.asm.add_assume()

        # init
        self.asm.add_label(masm.Label('start'))
        self.asm.add_code(masm.Mov('ax', 'data'))
        self.asm.add_code(masm.Mov('ds', 'ax'))

        for c in self.codes:
            if isinstance(c, masm.Label):
                self.asm.add_label(c)
            elif isinstance(c, masm.Code):
                self.asm.add_code(c)
            else:
                assert False, str(c)

        self.asm.add_segment_footer('code')
        self.asm.add_end()

    def visit(self, node):
        name = node.__class__.__name__
        visit_func = getattr(self, 'visit_' + name, None)
        assert visit_func is not None, f'{name} not supported, node {ast.dump(node)}'
        visit_func(node)

    def visit_Module(self, node):
        for stmt in node.body:
            self.visit(stmt)

    def visit_FunctionDef(self, node):
        if node.name == 'main':
            for stmt in node.body:
                self.visit(stmt)
        else:
            ...

    def visit_Expr(self, node):
        self.visit(node.value)

    def visit_Call(self, node):
        func_name = node.func.id
        args = node.args
        kwargs = node.keywords

        if func_name == 'print':
            self.print_data(args, kwargs)
        else:
            ...

    def print_data(self, args, kwargs):
        data_name = f'data{len(self.data)}'
        data_list = []
        for expr in args:
            if isinstance(expr, ast.Str):
                s = expr.s
                # TODO: handle char like \n \r \\ \t
                data_list.append(s)
            elif isinstance(expr, ast.Num):
                n = expr.n
                data_list.append(str(n))
            else:
                assert False, "Unsupported"
        data_list = [' '.join(data_list), ord('\n'), ord('\r'), '$']
        self.data.append(masm.Data(name=data_name, args=data_list))
        self.codes.append(masm.Mov('dx', f'offset {data_name}'))
        self.codes.append(masm.Mov('ah', 9))
        self.codes.append(masm.Int(0x21))

    def add_exit(self):
        self.codes.append(masm.Mov('ah', 0x4c))
        self.codes.append(masm.Int(0x21))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help="filename to compile")
    args = parser.parse_args()

    args.filename = 'tests' + os.sep + 'hello.py'

    with open(args.filename) as f:
        source = f.read()

    curpath = os.path.abspath(os.curdir)
    output = os.path.join(curpath, 'tests', 'hello.asm')
    compiler = Compiler(output_file=open(output, 'w'))

    node = ast.parse(source, filename=args.filename)
    compiler.compile(node)


if __name__ == '__main__':
    main()
