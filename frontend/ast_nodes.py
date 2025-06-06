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

@dataclass
class ArrayParameter:
    name: str
    param_type: str
    is_array: bool = True

# — Bloques y statements —
@dataclass
class Block:
    statements: List['Statement']

class Statement: pass

@dataclass
class Stmt(Statement):
    children: List['Expression']

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
    init: Optional['Statement']       # Inicialización (ej. i = 0)
    condition: Optional['Expression'] # Condición (ej. i < 10)
    update: Optional['Statement']     # Actualización (ej. i++)
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

class StringArrayDeclaration:
    """Representa una declaración de array de char inicializado con string"""
    def __init__(self, var_name, string_value):
        self.var_name = var_name
        self.var_type = "char"
        self.string_value = string_value
        self.size = len(string_value) + 1  # +1 para null terminator

class MultiDeclaration:
    """Representa una declaración múltiple de variables"""
    def __init__(self, var_type, var_names):
        self.var_type = var_type
        self.var_names = var_names  # Lista de nombres de variables

@dataclass
class String(Expression):
    value: str

@dataclass
class Character(Expression):
    value: str  # El carácter sin las comillas 