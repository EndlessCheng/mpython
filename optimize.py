import masm

_STATE_DEFAULT = 'default'
_STATE_PUSH = 'push'
_STATE_POP = 'pop'


def optimize_pushes_pops(codes):
    """
    This finds runs of push(es) followed by pop(s) and combines them into simpler, faster mov instructions.

    For example:

    push   [bp+8]
    push   42
    pop    ax
    pop    ax

    Will be turned into:

    mov    ax, 42
    mov    ax, ds:[bp+8]
    """
    optimized = []

    state = _STATE_DEFAULT
    pushes = 0
    pops = 0

    # This nested function combines a sequence of pushes and pops
    def combine():
        mid = len(optimized) - pops
        num = min(pushes, pops)
        masm_moves = []
        for i in range(num):
            pop_arg = optimized[mid + i].args[0]
            push_arg = optimized[mid - i - 1].args[0]
            if push_arg != pop_arg:
                masm_moves.append(masm.Mov(pop_arg, push_arg))
        optimized[mid - num:mid + num] = masm_moves

    def reset():
        nonlocal state, pushes, pops
        state = _STATE_DEFAULT
        pushes = 0
        pops = 0

    # This loop actually finds the sequences
    for ins in codes:
        op = ins.op
        if state == _STATE_DEFAULT:
            if op == 'push':
                state = _STATE_PUSH
                pushes += 1
            else:
                reset()
        elif state == _STATE_PUSH:
            if op == 'push':
                pushes += 1
            elif op == 'pop':
                state = _STATE_POP
                pops += 1
            else:
                reset()
        elif state == _STATE_POP:
            if op == 'pop':
                pops += 1
            else:
                combine()
                if op == 'push':
                    state = _STATE_PUSH
                    pushes = 1
                    pops = 0
                else:
                    reset()
        else:
            assert False, f"bad state: {state}"
        optimized.append(ins)
    if state == _STATE_POP:
        combine()

    return optimized


def optimize_single_ins(ins):
    if isinstance(ins, masm.Mov):
        if ins.args[1] == 0:
            return masm.Xor(ins.args[0], ins.args[0])
    elif isinstance(ins, masm.Add):
        if ins.args[1] == 1:
            return masm.Inc(ins.args[0])
        if ins.args[1] == 0:
            return None
        if ins.args[1] == -1:
            return masm.Dec(ins.args[0])
    elif isinstance(ins, masm.Sub):
        if ins.args[1] == 1:
            return masm.Dec(ins.args[0])
        if ins.args[1] == 0:
            return None
        if ins.args[1] == -1:
            return masm.Inc(ins.args[0])
    elif isinstance(ins, masm.Imul):
        ...  # handle 0, 1; 2, 4, 8, 16
    return ins


def optimize_single_ins_of_batch(batch):
    for ins in batch:
        optimized_ins = optimize_single_ins(ins)
        if optimized_ins:
            yield optimized_ins


def optimize_batch(batch):
    batch = optimize_pushes_pops(batch)
    batch = list(optimize_single_ins_of_batch(batch))
    return batch
