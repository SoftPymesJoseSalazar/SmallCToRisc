from dataclasses import dataclass
from typing import List, Optional

# — Nodos de alto nivel —
@dataclass
class Program:
    functions: List['Function']

@dataclass
class Function:
    name: str
    return_type: str
    params: List['Parameter']
    body: 'Block'

# — Parámetros —
@dataclass
class Parameter:
    name: str
    param_type: str

# — Bloques y statements —
@dataclass
class Block:
    statements: List['Statement']

class Statement: pass

@dataclass
class Declaration(Statement):
    var_name: str
    var_type: str
    value: Optional['Expression']

@dataclass
class Assignment(Statement):
    var_name: str
    value: 'Expression'

@dataclass
class If(Statement):
    condition: 'Expression'
    true_body: Block
    false_body: Optional[Block] = None

@dataclass
class While(Statement):
    condition: 'Expression'
    body: Block

@dataclass
class Return(Statement):
    expr: Optional['Expression']

@dataclass
class ExprStmt(Statement):
    expr: 'Expression'  # para llamadas a función sueltas

@dataclass
class For(Statement):
    init: Optional[Statement]        # Inicialización (ej. int i = 0; o i = 0;)
    condition: Optional['Expression'] # Condición (ej. i < 10)
    update: Optional['Expression']    # Actualización (ej. i++)
    body: Block                      # Cuerpo del bucle

# — Expresiones —
class Expression: pass

@dataclass
class BinaryOp(Expression):
    op: str
    left: Expression
    right: Expression

@dataclass
class Number(Expression):
    value: int

@dataclass
class Variable(Expression):
    name: str

@dataclass
class FuncCall(Expression):
    name: str
    args: List[Expression]

class ArrayAccess:
    def __init__(self, array_name, index):
        self.array_name = array_name
        self.index = index

class ArrayDeclaration:
    """Representa una declaración de array"""
    def __init__(self, var_name, var_type, size):
        self.var_name = var_name
        self.var_type = var_type
        self.size = size

class MultiDeclaration:
    """Representa una declaración múltiple de variables"""
    def __init__(self, var_type, var_names):
        self.var_type = var_type
        self.var_names = var_names  # Lista de nombres de variables 