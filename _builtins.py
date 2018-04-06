import ast

import masm


class BuiltinsMixin:
    def _putchar(self, expr):
        if isinstance(expr, ast.Name):
            offset = self.local_offset(expr.id)
            self.codes.append(masm.Mov('ax', f'[bp+{offset}]'))
        else:
            assert False, f"{type(expr)} not supported"
        self.codes.append(masm.Mov('dl', 'al'))
        self.codes.append(masm.Mov('ah', 2))
        self.codes.append(masm.Int(0x21))

    def _print(self, args, kwargs):
        parsed_kwargs = {'sep': ' ', 'end': [ord('\n'), ord('\r')]}
        for py_kw in kwargs:
            if py_kw.arg == 'sep':
                expr = py_kw.value
                if isinstance(expr, ast.Str):
                    # TODO: handle char like \n \r \\ \t
                    parsed_kwargs['sep'] = expr.s
                else:
                    assert False, f"{type(expr)} not supported"
            elif py_kw.arg == 'end':
                expr = py_kw.value
                if isinstance(expr, ast.Str):
                    # TODO: handle char like \n \r \\ \t
                    parsed_kwargs['end'] = [expr.s]
                else:
                    assert False, f"{type(expr)} not supported"
            else:
                assert False, f"keyword {py_kw.arg} not supported"

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
                assert False, f"{type(expr)} not supported"
        sep = parsed_kwargs['sep']
        data_list = [sep.join(data_list)] + parsed_kwargs['end'] + ['$']

        self.data.append(masm.Data(name=data_name, args=data_list))

        self.codes.append(masm.Mov('dx', f'offset {data_name}'))
        self.codes.append(masm.Mov('ah', 9))
        self.codes.append(masm.Int(0x21))
