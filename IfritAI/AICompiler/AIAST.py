# AIAST.py - Updated __str__ methods
from dataclasses import dataclass
from typing import List, Optional, Union


# Base class for all AST nodes
class ASTNode:
    def __str__(self):
        return self._to_str()

    def _to_str(self, indent=0):
        """Default string representation with indentation"""
        spaces = "  " * indent
        return f"{spaces}{self.__class__.__name__}"


# Expressions and values
@dataclass
class Value(ASTNode):
    value: str

    def _to_str(self, indent=0):
        spaces = "  " * indent
        return f"{spaces}Value('{self.value}')"


@dataclass
class ParamList(ASTNode):
    params: List[Value]

    def _to_str(self, indent=0):
        spaces = "  " * indent
        result = [f"{spaces}ParamList:"]
        for param in self.params:
            result.append(param._to_str(indent + 1))
        return "\n".join(result)


# Statements
@dataclass
class Command(ASTNode):
    name: str
    params: Optional[ParamList] = None

    def _to_str(self, indent=0):
        spaces = "  " * indent
        result = [f"{spaces}Command('{self.name}'):"]
        if self.params:
            result.append(self.params._to_str(indent + 1))
        return "\n".join(result)


@dataclass
class Condition(ASTNode):
    params: ParamList

    def _to_str(self, indent=0):
        spaces = "  " * indent
        result = [f"{spaces}Condition:"]
        result.append(self.params._to_str(indent + 1))
        return "\n".join(result)


@dataclass
class Block(ASTNode):
    statements: List['Statement']

    def _to_str(self, indent=0):
        spaces = "  " * indent
        result = [f"{spaces}Block:"]
        for stmt in self.statements:
            result.append(stmt._to_str(indent + 1))
        return "\n".join(result)


@dataclass
class IfStatement(ASTNode):
    condition: Condition
    then_block: Block
    elif_branches: List['ElifBranch']
    else_block: Optional[Block]

    def _to_str(self, indent=0):
        spaces = "  " * indent
        result = [f"{spaces}IfStatement:"]

        # Condition
        result.append(f"{spaces}  Condition:")
        result.append(self.condition.params._to_str(indent + 2))

        # Then block
        result.append(f"{spaces}  ThenBlock:")
        result.append(self.then_block._to_str(indent + 2))

        # Elseif branches (only if they exist)
        for i, elif_branch in enumerate(self.elif_branches):
            result.append(f"{spaces}  ElseIf[{i}]:")
            result.append(f"{spaces}    Condition:")
            result.append(elif_branch.condition.params._to_str(indent + 3))
            result.append(f"{spaces}    Block:")
            result.append(elif_branch.block._to_str(indent + 3))

        # Else block (only if it exists)
        if self.else_block:
            result.append(f"{spaces}  ElseBlock:")
            result.append(self.else_block._to_str(indent + 2))

        return "\n".join(result)


@dataclass
class ElifBranch(ASTNode):
    condition: Condition
    block: Block

    def _to_str(self, indent=0):
        spaces = "  " * indent
        result = [f"{spaces}ElifBranch:"]
        result.append(f"{spaces}  Condition:")
        result.append(self.condition.params._to_str(indent + 2))
        result.append(f"{spaces}  Block:")
        result.append(self.block._to_str(indent + 2))
        return "\n".join(result)


# Union type for all statement types
Statement = Union[Command, IfStatement]