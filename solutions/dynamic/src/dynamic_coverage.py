# dynamic analysis using coverage based fuzzing.
from collections.abc import Iterable
import random
import sys
import string
from abstractions import AbstractSmith
import jpamb
import jvm
import jvm.state as jvmc

from helpers.bitstring_input_generation import (
    generate_bitstring_inputs,
    mutate_input as mutate_bitstring,
)
from helpers.fuzz_context import (
    FuzzContext,
    init_context,
    analysis_inputs,
    smith_outcomes,
    static_smith_seeds,
    get_method_dictionary,
    get_bitstring_structure,
    MAX_SMITH_SEED_LENGTH,
)
from helpers.integer_input_generation import (
    IntegerOperation,
    mutate_integer,
)
from interpreter import (
    binary,
    compare,
    initial,
    interpret,
    signed_int,
    step,
)
from helpers.state_snapshot import ExecutionSnapshots


def mutate_input(
    seed: jpamb.case.Input,
    structure,
    dictionary,
    *,
    target: AbstractSmith | None = None,
    integer_operations: tuple[IntegerOperation, ...] = (),
) -> jpamb.case.Input:
    
    new_values = []
    for val in seed.values:
        match val:
            case jpamb.case.Smith(bits):
                new_bits = mutate_bitstring(bits, structure, dictionary)
                if target is not None:
                    lower = max(0, target.length.min or 0)
                    upper = min(
                        MAX_SMITH_SEED_LENGTH,
                        target.length.max if target.length.max is not None else MAX_SMITH_SEED_LENGTH,
                    )
                    preferred = random.choice((len(new_bits), len(target.pattern), lower))
                    length = min(max(preferred, lower), upper)
                    new_bits = new_bits[:length] + "".join(
                        random.choice("01") for _ in range(length - len(new_bits))
                    )
                    new_bits = "".join(
                        bit if fixed == "?" else fixed
                        for bit, fixed in zip(new_bits, target.pattern)
                    ) + new_bits[len(target.pattern):]
                new_values.append(jpamb.case.Smith(new_bits))
            case jpamb.case.Int(num):
                new_values.append(jpamb.case.Int(mutate_integer(num, integer_operations)))
            case jpamb.case.Boolean(b):
                new_values.append(jpamb.case.Boolean(not b))
            case jpamb.case.Array(contains=ct, values=arr_vals):
                vals_list = list(arr_vals)
                choice = random.choice(["extend", "shorten", "modify", "keep"])
                match choice:
                    case "extend" if len(vals_list) < 20:
                        if ct == jvm.Char():
                            cand = random.choice(string.ascii_letters)
                        else:
                            cand = random.choice(dictionary.get(int, [0, 1])) if dictionary else 0
                        vals_list.append(cand)
                    case "shorten" if vals_list:
                        vals_list.pop()
                    case "modify" if vals_list:
                        idx = random.randrange(len(vals_list))
                        if ct == jvm.Char():
                            vals_list[idx] = random.choice(string.ascii_letters)
                        elif isinstance(vals_list[idx], int):
                            vals_list[idx] = mutate_integer(vals_list[idx], integer_operations)
                    case _:
                        pass  
                new_values.append(jpamb.case.Array(ct, tuple(vals_list)))
            case other:
                new_values.append(other)
    return jpamb.case.Input(tuple(new_values))
    
    
    
def loop_is_independent_of_changed_locals(
    bc: jpamb.Bytecode,
    loop_path: list[jvmc.PC],
    previous_locals: tuple,
    current_locals: tuple,
) -> bool:
    changed_local_indices = set()
    for index, (previous, current) in enumerate(zip(previous_locals, current_locals)):
        if previous == current:
            continue
        if not (isinstance(previous, jvmc.StackInt) and isinstance(current, jvmc.StackInt)):
            return False
        changed_local_indices.add(index)

    for pc in loop_path:
        instruction = bc[pc]
        if isinstance(instruction, (jvm.InvokeStatic, jvm.Return)):
            return False
        if isinstance(instruction, jvm.Load) and instruction.index in changed_local_indices:
            return False
    return True


def execute_input(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    inp: jpamb.case.Input,
    max_steps: int = 2000,
) -> tuple[set, str | None, list[tuple[str, int, int]]]:
    """Runs a single input through the dynamic interpreter, tracking coverage, behavior, and dynamic reads."""
    state = initial(bc, methodid, inp)
    recorded_reads: list[tuple[str, int, int]] = []
    state.recorded_reads = recorded_reads
    seen_states = set()
    snapshots = ExecutionSnapshots()
    run_pcs = set()
    executed_path: list[jvmc.PC] = []
    loop_visits: dict[tuple, tuple[int, tuple]] = {}

    for _ in range(max_steps):
        pc, state = step(bc, state)
        run_pcs.add(pc)
        if isinstance(state, str):
            return run_pcs, state, recorded_reads

        snapshot = snapshots.snapshot(state)
        if snapshot in seen_states:
            return run_pcs, "*", recorded_reads
        seen_states.add(snapshot)
        executed_path.append(pc)

        callers, (next_pc, operand_stack, current_locals), heap = snapshot
        if next_pc.method != pc.method or next_pc.offset > pc.offset:
            continue

        loop_key = (next_pc, callers, operand_stack, heap)
        previous_visit = loop_visits.get(loop_key)
        loop_visits[loop_key] = (len(executed_path), current_locals)
        if previous_visit is None:
            continue

        loop_start, previous_locals = previous_visit
        loop_path = executed_path[loop_start:]
        if loop_is_independent_of_changed_locals(bc, loop_path, previous_locals, current_locals):
            return run_pcs, "*", recorded_reads

    return run_pcs, None, recorded_reads


def queue_dynamic_field_inputs(
    ctx: FuzzContext,
    discovering_input: jpamb.case.Input,
    new_fields: list[tuple[str, int, int]],
) -> None:
    """Queues targeted inputs for newly discovered dynamic bitfields"""
    smith_idx = next(
        (i for i, v in enumerate(discovering_input.values) if isinstance(v, jpamb.case.Smith)),
        None,
    )
    if smith_idx is None:
        return

    match discovering_input.values[smith_idx]:
        case jpamb.case.Smith(base_bits):
            pass
        case _:
            return
    for new_bits in generate_bitstring_inputs(new_fields, ctx.dictionary, base_seed=base_bits):
        values = list(discovering_input.values)
        values[smith_idx] = jpamb.case.Smith(new_bits)
        candidate = jpamb.case.Input(tuple(values))
        if candidate not in ctx.used_corpus:
            ctx.queued_inputs.append(candidate)


def run_initial_seeds(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    ctx: FuzzContext,
    max_steps: int = 2000,
) -> None:
    """Runs initial seeds and adds only coverage- or structure-expanding seeds to ctx.corpus."""
    normalized_seeds: list[jpamb.case.Input] = []
    for raw_seed in ctx.initial_seeds:
        # Array values must be immutable tuples for Input to be hashable in used_corpus set
        norm_values = tuple(
            jpamb.case.Array(v.contains, tuple(v.values))
            if isinstance(v, jpamb.case.Array) and not isinstance(v.values, tuple)
            else v
            for v in raw_seed.values
        )
        normalized_seeds.append(jpamb.case.Input(norm_values))

    if not normalized_seeds:
        normalized_seeds.append(jpamb.case.Input(()))

    for seed in normalized_seeds:
        if seed in ctx.used_corpus:
            continue
        ctx.used_corpus.add(seed)
        run_pcs, behavior, recorded = execute_input(bc, methodid, seed, max_steps)
        if behavior:
            ctx.behaviors.add(behavior)

        new_fields = []
        if ctx.use_dynamic_structure:
            new_fields = [field for field in recorded if field not in ctx.structure]
            if new_fields:
                ctx.structure.extend(new_fields)
                queue_dynamic_field_inputs(ctx, seed, new_fields)

        if (run_pcs - ctx.pc_coverage) or new_fields:
            ctx.pc_coverage.update(run_pcs)
            ctx.corpus.append(seed)

    if not ctx.corpus:
        ctx.corpus.append(normalized_seeds[0])

    ctx.structure.sort(key=lambda f: (f[1], f[2]))


def init_pending_targets(ctx: FuzzContext) -> dict[str, list[AbstractSmith]]:
    """Filters static Smith outcomes to only include unseen, valid target states."""
    pending_targets: dict[str, list[AbstractSmith]] = {}
    for outcome, states in ctx.smith_results.items():
        if outcome in ctx.behaviors:
            continue
        eligible = [
            smith for smith in states
            if not smith.is_bot and (smith.length.min or 0) <= MAX_SMITH_SEED_LENGTH
        ]
        if eligible:
            pending_targets[outcome] = eligible
    return pending_targets


def generate_mutant(
    ctx: FuzzContext,
    attempts_left: int,
    pending_targets: dict[str, list[AbstractSmith]],
) -> jpamb.case.Input:
    """Picks a seed from the corpus and produces a mutant, alternating between targeted and random mutation."""
    seed = random.choice(ctx.corpus)
    target = None
    if pending_targets and attempts_left % 3 == 0:
        outcome = random.choice(list(pending_targets))
        target = random.choice(pending_targets[outcome])

    mutant = mutate_input(
        seed, ctx.structure, ctx.dictionary, target=target, integer_operations=ctx.integer_operations
    )
    if target is not None and mutant in ctx.used_corpus:
        mutant = mutate_input(seed, ctx.structure, ctx.dictionary, integer_operations=ctx.integer_operations)

    return mutant


def coverage_based_fuzzing(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    ctx: FuzzContext,
    budget: int = 200,
    max_steps: int = 2000,
) -> set[str]:
    """Mutate corpus inputs, using static Smith states to target unseen outcomes."""
    if not ctx.corpus:
        return ctx.behaviors

    pending_targets = init_pending_targets(ctx)

    for attempts_left in range(budget, 0, -1):
        mutant = (
            ctx.queued_inputs.pop(0)
            if ctx.queued_inputs and attempts_left % 3 == 1
            else generate_mutant(ctx, attempts_left, pending_targets)
        )
        if mutant in ctx.used_corpus:
            continue
        ctx.used_corpus.add(mutant)

        run_pcs, behavior, recorded = execute_input(bc, methodid, mutant, max_steps)
        if behavior:
            ctx.behaviors.add(behavior)
            # Retire the outcome that actually occurred, even on an ordinary mutation.
            pending_targets.pop(behavior, None)

        new_fields = []
        if ctx.use_dynamic_structure:
            new_fields = [field for field in recorded if field not in ctx.structure]
            if new_fields:
                ctx.structure.extend(new_fields)
                ctx.structure.sort(key=lambda f: (f[1], f[2]))
                queue_dynamic_field_inputs(ctx, mutant, new_fields)

        if (run_pcs - ctx.pc_coverage) or new_fields:
            ctx.pc_coverage.update(run_pcs)
            ctx.corpus.append(mutant)

    return ctx.behaviors


def analyse():
    """The dynamic analysis: initial seeds + coverage-based fuzzing."""
    methodid = jpamb.getmethodid(
        "dynamic",
        "1.0",
        "Bit Diddlers",
        ["dynamic", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    MAX_STEPS = 2000
    BUDGET = 200

    ctx = init_context(methodid, suite, bc)
    run_initial_seeds(bc, methodid, ctx, max_steps=MAX_STEPS)
    coverage_based_fuzzing(bc, methodid, ctx, budget=BUDGET, max_steps=MAX_STEPS)

    for query in jpamb.QUERIES:
        if query in ctx.behaviors:
            if query == "*":
                print(f"{query};timeout")
            else:
                print(f"{query};found")
        else:
            print(f"{query};not-found")

