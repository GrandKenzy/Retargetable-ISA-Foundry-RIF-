from __future__ import annotations


class CompileError(Exception):
    def __init__(self, message: str, line: int | None = None, col: int | None = None):
        self.message = message
        self.line = line
        self.col = col
        if line is None:
            super().__init__(message)
        elif col is None:
            super().__init__(f"{message} at line {line}")
        else:
            super().__init__(f"{message} at {line}:{col}")


class SectionError(CompileError):
    pass


class FieldError(CompileError):
    pass


class RuleSyntaxError(CompileError):
    pass


class MacroSyntaxError(CompileError):
    pass


class NeedSyntaxError(CompileError):
    pass


class UnknownNeedTypeError(NeedSyntaxError):
    pass


class NeedTargetError(NeedSyntaxError):
    pass


class OperandCountError(CompileError):
    pass


class LiteralMismatchError(CompileError):
    pass


class OperandTypeError(CompileError):
    pass


class SymbolPendingError(CompileError):
    pass


class RuleInstructionError(CompileError):
    pass


class RuleExecutionError(CompileError):
    pass


class RuleConditionError(RuleExecutionError):
    pass


class EmitError(RuleExecutionError):
    pass
