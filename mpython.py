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

    def visit_For(self, node):
        self.add(node.target.id)
        for stmt in node.body:
            self.visit(stmt)


class BaseVisitor:
    def visit(self, node, *args, **kwargs):
        method = 'visit_' + node.__class__.__name__
        visitor = getattr(self, method, None)
        assert visitor is not None, f"{method} not supported, node {ast.dump(node)}"
        return visitor(node, *args, **kwargs)

    def visit_Str(self, node):
        print(f"Consumed string {node.s}")

    # def visit_Pass(self, node):
    #     pass

    def visit_Ellipsis(self, node):
        pass


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
        self.exit()

    def gen_result(self):
        self.asm.add_assume()

        self.asm.add_segment_header('data')
        self.asm.add_data(masm.Data())
        for d in self.data:
            self.asm.add_data(d)
        self.asm.add_segment_footer('data')

        self.asm.add_segment_header('code')
        self.asm.add_label('start')
        # Init ds reg
        self.asm.add_code(masm.Mov('ax', 'data'))
        self.asm.add_code(masm.Mov('ds', 'ax'))
        # TODO: Init ss reg

        for c in self.codes:
            if isinstance(c, str):
                # TODO: 重构 label
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

        self._func = node.name  # For gen label name
        self._loop_labels = []  # See method visit_Continue
        self._break_labels = []  # See method visit_Break

        self._locals = [py_arg.arg for py_arg in py_args.args]
        self._label_num = 0

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
        else:  # TODO: builtin
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

    def visit_Str(self, node):
        # TODO: malloc?
        s = node.s
        if len(s) == 1:
            self.visit(ast.Num(n=ord(s[0])))
        else:
            super().visit_Str(node)

    def visit_NameConstant(self, node):
        # Handle None, False and True
        value = node.value
        if value is None or value is False:
            self.visit(ast.Num(n=0))
        elif value is True:
            self.visit(ast.Num(n=1))
        else:
            assert False, f"{value} not supported"

    def visit_Name(self, node):
        offset = self.local_offset(node.id)
        self.codes.append(masm.Push(f'[bp+{offset}]'))

    def visit_Expr(self, node):
        self.visit(node.value)
        # TODO: self.codes.append(masm.Pop('ax'))

    def visit_Call(self, node):
        func_name = node.func.id
        args = node.args
        kwargs = node.keywords

        # TODO: builtin
        if func_name == 'print':
            self._print(args, kwargs)
        elif func_name == 'putchar':
            self._putchar(args[0])
        else:
            ...

    # TODO: ast.Not, ast.Invert
    def visit_UnaryOp(self, node):
        assert isinstance(node.op, ast.USub), f"only unary minus is supported, not {type(node.op)}"
        self.visit(ast.Num(n=0))
        self.visit(node.operand)
        self.visit(ast.Sub())

    def visit_BinOp(self, node):
        self.visit(node.left)
        self.visit(node.right)
        self.visit(node.op)

    def visit_AugAssign(self, node):
        # +=, -=, ...
        # TODO: inc for += 1
        py_name = node.target
        self.visit(py_name)
        self.visit(node.value)
        self.visit(node.op)

        offset = self.local_offset(py_name.id)
        self.codes.append(masm.Pop(f'[bp+{offset}]'))

    def _simple_bin_op(self, bin_ins_class):
        self.codes.append(masm.Pop('dx'))  # right
        self.codes.append(masm.Pop('ax'))  # left
        self.codes.append(bin_ins_class('ax', 'dx'))
        self.codes.append(masm.Push('ax'))

    def visit_Add(self, node):
        self._simple_bin_op(masm.Add)

    def visit_Sub(self, node):
        self._simple_bin_op(masm.Sub)

    def visit_Mult(self, node):
        self.codes.append(masm.Pop('dx'))  # right
        self.codes.append(masm.Pop('ax'))  # left
        self.codes.append(masm.Mul('dx'))  # ax = ax * dx
        self.codes.append(masm.Push('ax'))  # TODO: 取存放高 16 位的 dx

    def _compile_divide(self, result_reg):
        self.codes.append(masm.Pop('dx'))  # right
        self.codes.append(masm.Pop('ax'))  # left
        self.codes.append(masm.Div('dx'))  # ax, dx = ax // dx, ax % dx
        self.codes.append(masm.Push(result_reg))

    def visit_FloorDiv(self, node):
        self._compile_divide('ax')

    def visit_Mod(self, node):
        self._compile_divide('dx')

    def visit_BitAnd(self, node):
        self._simple_bin_op(masm.And)

    visit_And = visit_BitAnd

    def visit_BitOr(self, node):
        self._simple_bin_op(masm.Or)

    def visit_BitXor(self, node):
        self._simple_bin_op(masm.Xor)

    visit_Or = visit_BitOr

    def _simple_shift_op(self, shift_ins_class):
        self.codes.append(masm.Mov('ax', 'cx'))  # save cx

        self.codes.append(masm.Pop('cx'))  # cnt
        self.codes.append(masm.Pop('dx'))  # opr
        self.codes.append(shift_ins_class('dx', 'cl'))
        self.codes.append(masm.Push('dx'))

        self.codes.append(masm.Mov('cx', 'ax'))  # restore cx

    def visit_LShift(self, node):
        self._simple_shift_op(masm.Sal)

    def visit_RShift(self, node):
        self._simple_shift_op(masm.Sar)

    def visit_BoolOp(self, node):
        self.visit(node.values[0])
        for value in node.values[1:]:
            self.visit(value)
            self.visit(node.op)

    def gen_label(self, slug=''):
        func = self._func or '_global'
        label = f'_{func}_{self._label_num}'
        if slug:
            slug = slug.replace(' ', '_')
            label += f'_{slug}'
        self._label_num += 1
        return label

    def visit_Compare(self, node):
        # TODO: multi-compare
        assert len(node.ops) == 1, "only single comparisons supported"
        self.visit(node.left)
        self.visit(node.comparators[0])
        self.visit(node.ops[0])

    def _compile_comparison(self, cond_jump_class, slug):
        """
        False: push 1
        True: push 0
        """
        self.codes.append(masm.Xor('bx', 'bx'))  # bx = 0
        self.codes.append(masm.Pop('dx'))  # right
        self.codes.append(masm.Pop('ax'))  # left
        self.codes.append(masm.Cmp('ax', 'dx'))  # left - right
        label = self.gen_label(slug)
        self.codes.append(cond_jump_class(label))
        self.codes.append(masm.Inc('bx'))  # False
        self.codes.append(label)
        self.codes.append(masm.Push('bx'))  # True

    def visit_Eq(self, node):
        self._compile_comparison(masm.Je, 'equal')

    def visit_NotEq(self, node):
        self._compile_comparison(masm.Jne, 'not_equal')

    def visit_Lt(self, node):
        self._compile_comparison(masm.Jb, 'less')

    def visit_LtE(self, node):
        self._compile_comparison(masm.Jbe, 'less_or_equal')

    def visit_Gt(self, node):
        self._compile_comparison(masm.Ja, 'greater')

    def visit_GtE(self, node):
        self._compile_comparison(masm.Jae, 'greater_or_equal')

    def visit_If(self, node):
        label_else = self.gen_label('else')
        label_end = self.gen_label('end')

        self.visit(node.test)  # ast.Compare
        self.codes.append(masm.Pop('ax'))
        self.codes.append(masm.Cmp('ax', 1))
        self.codes.append(masm.Je(label_else))  # False

        for stmt in node.body:
            self.visit(stmt)
        if node.orelse:
            # if 执行完后跳到 if-else 串的末尾
            self.codes.append(masm.Jmp(label_end))

        self.codes.append(label_else)
        for stmt in node.orelse:
            self.visit(stmt)

        if node.orelse:
            self.codes.append(label_end)

    def visit_While(self, node, incr=None):
        assert not node.orelse, "while-else not supported"

        while_label = self.gen_label('while')
        self._loop_labels.append(while_label)
        break_label = self.gen_label('break')
        self._break_labels.append(break_label)
        if incr:
            incr_label = self.gen_label('incr')
            self._loop_labels.append(incr_label)

        self.codes.append(while_label)
        self.visit(node.test)
        self.codes.append(masm.Pop('ax'))
        self.codes.append(masm.Cmp('ax', 1))
        self.codes.append(masm.Je(break_label))  # False

        for statement in node.body:
            self.visit(statement)
        if incr:
            self.codes.append(incr_label)
            self.visit(incr)
        self.codes.append(masm.Jmp(while_label))

        self.codes.append(break_label)

        self._break_labels.pop()
        self._loop_labels.pop()
        if incr:
            self._loop_labels.pop()

    def visit_Break(self, node):
        self.codes.append(masm.Jmp(self._break_labels[-1]))

    def visit_Continue(self, node):
        self.codes.append(masm.Jmp(self._loop_labels[-1]))

    def _parse_range_args(self, range_args):
        if len(range_args) == 1:
            start = ast.Num(n=0)
            stop = range_args[0]
            step = ast.Num(n=1)
        elif len(range_args) == 2:
            start, stop = range_args
            step = ast.Num(n=1)
        else:
            start, stop, step = range_args
            # TODO: self.visit(step)
            if isinstance(step, ast.UnaryOp) and isinstance(step.op, ast.USub) and isinstance(step.operand, ast.Num):
                # Handle negative step
                step = ast.Num(n=-step.operand.n)
            assert isinstance(step, ast.Num) and step.n != 0, "range() step must be a nonzero integer constant"
        return start, stop, step

    def visit_For(self, node):
        """
        Turn `for i in range()` loop into a while loop:
        >>>  i = start
        >>>  while i < stop:  # or >
        >>>      node.body
        >>>      i += step  # 考虑到 continue 的情况，略有差别，见 visit_While
        """
        assert not node.orelse, "for-else not supported"

        py_call = node.iter
        assert isinstance(py_call, ast.Call) and py_call.func.id == 'range', "for can only be used with range()"
        start, stop, step = self._parse_range_args(py_call.args)
        py_name = node.target

        init = ast.Assign(targets=[py_name], value=start)
        cond = ast.Compare(left=node.target, ops=[ast.Lt() if step.n > 0 else ast.Gt()], comparators=[stop])
        incr = ast.AugAssign(target=py_name, op=ast.Add(), value=step)

        self.visit(init)
        self.visit(ast.While(test=cond, body=node.body, orelse=[]), incr=incr)

    def exit(self):
        self.codes.append(masm.Mov('ax', 0x4c00))  # return al, which is 0
        self.codes.append(masm.Int(0x21))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help="filename to compile")
    args = parser.parse_args()

    name = 'jmp'
    args.filename = 'tests' + os.sep + f'{name}.py'

    with open(args.filename, encoding='utf-8') as f:
        source = f.read()
    node = ast.parse(source, filename=args.filename)

    curpath = os.path.abspath(os.curdir)
    output = os.path.join(curpath, 'tests', f'{name}.asm')
    print(f"Output to {output}")
    with open(output, 'w') as f:
        compiler = Compiler(output_file=f)
        compiler.compile(node)

    if platform.system() == 'Windows':
        shutil.copyfile(output, os.path.expanduser('~') + f"\{name}.asm")


if __name__ == '__main__':
    main()
