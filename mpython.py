import argparse
import ast
import os
import platform
import shutil
import sys

import masm
from _builtins import BuiltinsMixin


class LocalsVisitor(ast.NodeVisitor):
    """
    Recursively visit a FunctionDef node to find all the locals
    (so we can allocate the right amount of stack space for them).
    """

    def __init__(self):
        self.local_names = []

    def add(self, name):
        if name not in self.local_names:
            self.local_names.append(name)

    def visit_Assign(self, node):
        assert len(node.targets) == 1, "can only assign one variable at a time"
        # self.visit(node.value)
        target = node.targets[0]
        self.add(target.id)


class BaseVisitor:
    def visit(self, node):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, None)
        assert visitor is not None, f"{method} not supported, node {ast.dump(node)}"
        return visitor(node)

    def visit_Str(self, node):
        print(f"Consumed string {node.s}")


class Compiler(BaseVisitor, BuiltinsMixin):
    """
    The main Python AST -> MASM compiler.
    """

    def __init__(self, output_file=sys.stdout):
        self.asm = masm.MASM(output_file)

        self.data = []
        self.codes = []

        self._func = None
        self._locals = None

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
        self.asm.add_assume()

        self.asm.add_segment_header('data')
        self.asm.add_data(masm.Data())
        for d in self.data:
            self.asm.add_data(d)
        self.asm.add_segment_footer('data')

        self.asm.add_segment_header('code')
        self.asm.add_label(masm.Label('start'))
        # init
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

    def visit_Module(self, node):
        for stmt in node.body:
            self.visit(stmt)

    def visit_FunctionDef(self, node):
        assert self._func is None, "nested functions not supported"

        py_args = node.args
        assert py_args.vararg is None, "*args not supported"
        assert not py_args.kwonlyargs, "keyword-only args not supported"
        assert not py_args.kwarg, "keyword args not supported"

        # TODO: kwargs with defaults

        self._func = node.name
        self._locals = [py_arg.arg for py_arg in py_args.args]

        # Find names of additional locals assigned in this function
        locals_visitor = LocalsVisitor()
        locals_visitor.visit(node)
        for name in locals_visitor.local_names:
            if name not in self._locals:
                self._locals.append(name)

        print(self._locals)

        self.malloc_locals(len(self._locals) - len(py_args.args))

        if node.name == 'main':
            for stmt in node.body:
                self.visit(stmt)
        else:
            ...

        self._func = None

    def malloc_locals(self, num_extra_locals):
        """
        占位，塞了一堆垃圾数据进去
        """
        for _ in range(num_extra_locals):
            self.codes.append(masm.Push('ax'))
        # Use bp for a stack frame pointer
        self.codes.append(masm.Push('bp'))
        self.codes.append(masm.Mov('bp', 'sp'))

    def local_offset(self, var_name):
        index = self._locals.index(var_name)
        return (len(self._locals) - index) * 2

    def visit_Assign(self, node):
        assert len(node.targets) == 1, "can only assign one variable at a time"

        py_name = node.targets[0]
        self.visit(node.value)

        self.codes.append(masm.Pop('ax'))
        offset = self.local_offset(py_name.id)
        self.codes.append(masm.Mov(f'[bp+{offset}]', 'ax'))

    def visit_Num(self, node):
        n = node.n
        self.codes.append(masm.Mov('ax', n))
        self.codes.append(masm.Push('ax'))

    def visit_Expr(self, node):
        self.visit(node.value)

    def visit_Call(self, node):
        func_name = node.func.id
        args = node.args
        kwargs = node.keywords

        if func_name == 'print':
            self._print(args, kwargs)
        elif func_name == 'putchar':
            self._putchar(args[0])
        else:
            ...

    def add_exit(self):
        self.codes.append(masm.Mov('ah', 0x4c))
        self.codes.append(masm.Int(0x21))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help="filename to compile")
    args = parser.parse_args()

    name = 'putc'
    args.filename = 'tests' + os.sep + f'{name}.py'

    with open(args.filename, encoding='utf-8') as f:
        source = f.read()
    node = ast.parse(source, filename=args.filename)

    curpath = os.path.abspath(os.curdir)
    output = os.path.join(curpath, 'tests', f'{name}.asm')
    with open(output, 'w') as f:
        compiler = Compiler(output_file=f)
        compiler.compile(node)

    if platform.system() == 'Windows':
        shutil.copyfile(output, os.path.expanduser('~') + f"\{name}.asm")


if __name__ == '__main__':
    main()
