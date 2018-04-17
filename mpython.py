import argparse
import ast
import os
import platform
import shutil
import sys

import masm
from _builtins import BuiltinsMixin

MAIN_FUNC_NAME = 'main'


class LocalsVisitor(ast.NodeVisitor):
    """
    Recursively visit a FunctionDef node to find all the locals
    (so we can allocate the right amount of stack space for them).
    """

    def __init__(self, node):
        self._local_names = set()
        self.node = node

    def collect(self):
        self.visit(self.node)
        return self._local_names

    def _add(self, name):
        self._local_names.add(name)

    def visit_Assign(self, node):
        assert len(node.targets) == 1, "can only assign one variable at a time"
        # self.visit(node.value)
        target = node.targets[0]
        self._add(target.id)

    def visit_For(self, node):
        self._add(node.target.id)
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

    def compile(self, node):
        self.before_visit()
        self.visit(node)
        self.after_visit()

        self.gen_result()

    def before_visit(self):
        pass

    def after_visit(self):
        pass

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

        # TODO: global ?
        self.asm.add_code(masm.Jmp(MAIN_FUNC_NAME))

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

    # ---------------------------------------------------------------------------------

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
        func_label = node.name
        self.codes.append(func_label)

        self._label_num = 0
        self._loop_labels = []  # See method visit_Continue
        self._break_labels = []  # See method visit_Break

        self._func_args = [py_arg.arg for py_arg in py_args.args]
        self._locals = list(LocalsVisitor(node).collect() - set(self._func_args))

        print(self._func_args)
        print(self._locals)

        # Also see method visit_Call
        self.compile_prologue(len(self._locals))

        for stmt in node.body:
            self.visit(stmt)
        if not isinstance(node.body[-1], ast.Return):
            # 手动加上 return
            self.visit(ast.Return(value=None))

        # self.codes.append('')
        self._func = None

    def _extend_stack(self, n):
        # 增大栈
        if n > 0:
            self.codes.append(masm.Sub('sp', 2 * n))

    def _rewind_stack(self, n):
        # 回滚栈
        if n > 0:
            self.codes.append(masm.Add('sp', 2 * n))

    def compile_prologue(self, num_locals):
        # Use bp for a stack frame pointer
        self.codes.append(masm.Push('bp'))  # 保存调用函数前的 bp
        self.codes.append(masm.Mov('bp', 'sp'))
        self._extend_stack(num_locals)

    def compile_epilogue(self):
        # TODO: Lea
        self.codes.append(masm.Mov('sp', 'bp'))
        self.codes.append(masm.Pop('bp'))  # 复原成上层函数的 bp
        self.codes.append(masm.Ret())

    def visit_Return(self, node):
        # TODO: multi-return
        value = node.value
        assert not isinstance(value, ast.Tuple), "return multi values not supported"

        if value:
            self.visit(value)

        if self._func == MAIN_FUNC_NAME:
            self.compile_exit(value.n if value else 0)
        else:
            if value:
                # Save return value to ax (see method visit_Call)
                self.codes.append(masm.Pop('ax'))
            self.compile_epilogue()

    def visit_Expr(self, node):
        self.visit(node.value)

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
            # 倒序压栈，便于检索
            for py_arg in reversed(args):
                self.visit(py_arg)
            self.codes.append(masm.Call(func_name))
            if args:
                self._rewind_stack(len(args))

            # Push ax whatever (see method visit_Return)
            self.codes.append(masm.Push('ax'))

    # ---------------------------------------------------------------------------------

    def _local_offset(self, var_name):
        if var_name in self._func_args:
            index = self._func_args.index(var_name) + 2
        elif var_name in self._locals:
            index = -(self._locals.index(var_name) + 1)
        else:
            assert False, f"can't find {var_name} in {self._func}"
        return 2 * index

    def _gen_var_mem(self, offset):
        return f'[bp{offset:+d}]'

    def visit_Assign(self, node):
        assert len(node.targets) == 1, "can only assign one variable at a time"

        py_name = node.targets[0]
        self.visit(node.value)

        self.codes.append(masm.Pop('ax'))
        offset = self._local_offset(py_name.id)
        self.codes.append(masm.Mov(self._gen_var_mem(offset), 'ax'))

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
        offset = self._local_offset(node.id)
        self.codes.append(masm.Push(self._gen_var_mem(offset)))

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

        offset = self._local_offset(py_name.id)
        self.codes.append(masm.Pop(self._gen_var_mem(offset)))

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
        self.codes.append(masm.Push('ax'))
        # TODO: 取存放高 16 位的 dx

    def _compile_divide(self, result_reg):
        self.codes.append(masm.Pop('bx'))  # right
        self.codes.append(masm.Xor('dx', 'dx'))
        self.codes.append(masm.Pop('ax'))  # left
        self.codes.append(masm.Div('bx'))  # ax, dx = ax // bx, ax % bx
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
        self.codes.append(masm.Pop('cx'))  # cnt
        self.codes.append(masm.Pop('dx'))  # opr
        self.codes.append(shift_ins_class('dx', 'cl'))
        self.codes.append(masm.Push('dx'))

    def visit_LShift(self, node):
        self._simple_shift_op(masm.Sal)

    def visit_RShift(self, node):
        self._simple_shift_op(masm.Sar)

    def visit_BoolOp(self, node):
        self.visit(node.values[0])
        for value in node.values[1:]:
            self.visit(value)
            self.visit(node.op)

    # ---------------------------------------------------------------------------------

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
        False: push 0
        True: push 1
        """
        self.codes.append(masm.Mov('bx', 1))
        self.codes.append(masm.Pop('dx'))  # right
        self.codes.append(masm.Pop('ax'))  # left
        self.codes.append(masm.Cmp('ax', 'dx'))  # left - right
        label_true = self.gen_label(slug)
        self.codes.append(cond_jump_class(label_true))
        self.codes.append(masm.Dec('bx'))
        self.codes.append(label_true)
        self.codes.append(masm.Push('bx'))

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
        self.codes.append(masm.Pop('bx'))
        self.codes.append(masm.Cmp('bx', 0))
        self.codes.append(masm.Jz(label_else))  # False

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
        self.codes.append(masm.Pop('bx'))
        self.codes.append(masm.Cmp('bx', 0))
        self.codes.append(masm.Jz(break_label))  # False

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

    # ---------------------------------------------------------------------------------

    def compile_exit(self, return_code):
        assert -128 <= return_code <= 127
        self.codes.append(masm.Mov('ax', 0x4c00 + return_code))  # return al
        self.codes.append(masm.Int(0x21))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', help="filename to compile")
    args = parser.parse_args()

    name = 'algo'
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
