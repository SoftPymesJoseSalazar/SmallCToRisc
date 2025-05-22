from lark import Lark, Transformer, v_args, Token
from .ast_nodes import *

GRAMMAR = r"""
start: top_level*

top_level: function_decl
         | global_decl

// Global declarations: single, multi, assignment, array
global_decl: declaration
           | multi_decl
           | assignment
           | array_decl

// Declaraciones
declaration: TYPE ID ["=" expression] SEMICOLON        -> declaration
multi_decl : TYPE ID (COMMA ID)+ SEMICOLON             -> multi_declaration
assignment : (ID | array_access) "=" expression SEMICOLON -> assignment
array_decl : TYPE ID "[" NUMBER "]" SEMICOLON          -> array_declaration

// Acceso a arrays
array_access: ID "[" expression "]"                     -> array_access

// Funciones
function_decl: TYPE ID "(" [param_list] ")" block       -> function

param_list: parameter ( COMMA parameter )*
parameter : TYPE ID                                      -> parameter

// Bloques y sentencias
block     : "{" stmt* "}"                         -> block
stmt      : declaration
          | multi_decl
          | assignment
          | array_decl
          | if_stmt
          | while_stmt
          | return_stmt
          | block                                  // Permite bloques como stmt
          | expression SEMICOLON                        -> expr_stmt

// Estructuras de control
if_stmt   : "if" "(" expression ")" stmt ["else" stmt] -> if_stmt
while_stmt: "while" "(" expression ")" stmt              -> while_stmt
return_stmt: "return" [expression] SEMICOLON           -> return_stmt

// Expresiones
?expression: logic_expr

?logic_expr: comp_expr
           | logic_expr AND comp_expr                   -> logic_and
           | logic_expr OR  comp_expr                   -> logic_or

?comp_expr: sum
          | comp_expr EQ  sum                           -> comp_eq
          | comp_expr NE  sum                           -> comp_ne
          | comp_expr LT  sum                           -> comp_lt
          | comp_expr GT  sum                           -> comp_gt
          | comp_expr LE  sum                           -> comp_le
          | comp_expr GE  sum                           -> comp_ge

?sum     : term
         | sum PLUS  term                                -> sum_add
         | sum MINUS term                                -> sum_sub

?term    : factor
         | term STAR  factor                             -> term_mul
         | term SLASH factor                             -> term_div

?factor  : NUMBER                                        -> number
         | STRING                                        -> string
         | ID                                            -> variable
         | function_call
         | "(" expression ")"

// Llamadas a función
function_call: ID "(" [arg_list] ")"                   -> function_call
arg_list     : expression ( COMMA expression )*          -> arg_list

// Tokens
TYPE      : "int" | "char" | "void"
ID        : /[a-zA-Z_]\w*/
NUMBER    : /\d+/
STRING    : ESCAPED_STRING

// Puntuación y operadores
EQ        : "==" 
NE        : "!=" 
LE        : "<=" 
GE        : ">=" 
LT        : "<"  
GT        : ">"  
AND       : "&&" 
OR        : "||" 
PLUS      : "+"  
MINUS     : "-"  
STAR      : "*"  
SLASH     : "/"  
COMMA     : ","  
SEMICOLON : ";"  

%import common.ESCAPED_STRING
%import common.WS
%ignore WS

COMMENT: /\/\/[^\n]*/ | /\/\*.*?\*\//
%ignore COMMENT
"""

@v_args(inline=True)
class ASTTransformer(Transformer):
    def start(self, *items):
        return Program([i for i in items if i is not None])

    def function(self, ret, name, params, body):
        """Transforma una declaración de función en un nodo Function."""
        # Extraer parámetros correctamente
        param_list = []
        
        # Si params es None, usar lista vacía
        if params is None:
            param_list = []
        # Si params ya es una lista, usarla directamente
        elif isinstance(params, list):
            param_list = params
        # Si es un objeto con atributo children, extraer los parámetros
        elif hasattr(params, 'children'):
            param_list = params.children
        
        # Procesar cada parámetro para asegurar formato correcto
        processed_params = []
        for p in param_list:
            if isinstance(p, Parameter):
                # Ya es un objeto Parameter, usarlo directamente
                processed_params.append(p)
            elif isinstance(p, dict) and 'param_name' in p and 'param_type' in p:
                # Ya es un diccionario con formato correcto
                processed_params.append(p)
            elif hasattr(p, 'value') and hasattr(p, 'type'):
                # Es un token, intentar extraer tipo y nombre
                parts = str(p.value).split()
                if len(parts) >= 2:
                    processed_params.append(Parameter(parts[1], parts[0]))
        
        # Crear y devolver el nodo Function
        return Function(name.value, ret.value, processed_params, body)

    def parameter(self, t, n):
        """Transforma un parámetro de función."""
        # Asegurarse de que t y n sean strings
        type_str = t.value if hasattr(t, 'value') else str(t)
        name_str = n.value if hasattr(n, 'value') else str(n)
        
        # Crear y devolver el objeto Parameter
        return Parameter(name_str, type_str)

    def param_list(self, *params):
        """Agrupa múltiples parámetros en una lista."""
        return list(params)

    def declaration(self, *args):
        t_val = None
        n_val = None
        expr = None
        
        for arg in args:
            if isinstance(arg, Token):
                if arg.type == 'TYPE':
                    t_val = arg.value
                elif arg.type == 'ID':
                    n_val = arg.value
                elif arg.type == 'SEMICOLON':
                    pass
            elif not isinstance(arg, Token):
                expr = arg
                
        return Declaration(n_val, t_val, expr)

    def multi_declaration(self, *args):
        t_val = None
        names = []
        
        for arg in args:
            if isinstance(arg, Token):
                if arg.type == 'TYPE':
                    t_val = arg.value
                elif arg.type == 'ID':
                    names.append(arg.value)
                    
        return MultiDeclaration(t_val, names)

    def assignment(self, *args):
        target = None
        expr = None
        
        for arg in args:
            if isinstance(arg, Token):
                if arg.type == 'ID':
                    target = arg.value
                elif arg.type == 'SEMICOLON':
                    pass
            elif isinstance(arg, ArrayAccess):
                target = arg
            elif not isinstance(arg, Token) and target is not None:
                expr = arg
                
        return Assignment(target, expr)

    def array_declaration(self, *args):
        t_val = None
        n_val = None
        size = None
        
        for arg in args:
            if isinstance(arg, Token):
                if arg.type == 'TYPE':
                    t_val = arg.value
                elif arg.type == 'ID':
                    n_val = arg.value
                elif arg.type == 'NUMBER':
                    size = int(arg.value)
                    
        return ArrayDeclaration(n_val, t_val, size)

    def array_access(self, *args):
        n_val = None
        idx = None
        
        for arg in args:
            if isinstance(arg, Token) and arg.type == 'ID':
                n_val = arg.value
            elif not isinstance(arg, Token):
                idx = arg
                
        return ArrayAccess(n_val, idx)

    def block(self, *stmts):
        # Filtrar tokens que no sean sentencias
        real_stmts = [s for s in stmts if not isinstance(s, Token)]
        return Block(real_stmts)

    def if_stmt(self, *args):
        cond = None
        then_b = None
        else_b = None
        
        # El primer no-token debe ser la condición
        for arg in args:
            if not isinstance(arg, Token) and cond is None:
                cond = arg
            elif not isinstance(arg, Token) and cond is not None and then_b is None:
                then_b = arg
            elif not isinstance(arg, Token) and cond is not None and then_b is not None:
                else_b = arg
                
        return If(cond, then_b, else_b)

    def while_stmt(self, *args):
        cond = None
        body = None
        
        for arg in args:
            if not isinstance(arg, Token) and cond is None:
                cond = arg
            elif not isinstance(arg, Token) and cond is not None:
                body = arg
                
        return While(cond, body)

    def return_stmt(self, *args):
        expr = None
        for arg in args:
            if not isinstance(arg, Token) or arg.type != 'SEMICOLON':
                expr = arg
                break
        return Return(expr)

    def expr_stmt(self, *args):
        for arg in args:
            if not isinstance(arg, Token):
                return arg
        return None

    def function_call(self, *args):
        name = None
        arg_list = []
        
        for arg in args:
            if isinstance(arg, Token) and arg.type == 'ID':
                name = arg.value
            elif isinstance(arg, list):
                arg_list = arg
                
        return FuncCall(name, arg_list or [])

    def arg_list(self, *args):
        return [arg for arg in args if not isinstance(arg, Token)]

    # Métodos para operaciones lógicas
    def logic_and(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("&&", operands[0], operands[1])
        return operands[0] if operands else None
        
    def logic_or(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("||", operands[0], operands[1])
        return operands[0] if operands else None
    
    # Métodos para comparaciones
    def comp_eq(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("==", operands[0], operands[1])
        return operands[0] if operands else None
        
    def comp_ne(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("!=", operands[0], operands[1])
        return operands[0] if operands else None
        
    def comp_lt(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("<", operands[0], operands[1])
        return operands[0] if operands else None
        
    def comp_gt(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp(">", operands[0], operands[1])
        return operands[0] if operands else None
        
    def comp_le(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("<=", operands[0], operands[1])
        return operands[0] if operands else None
        
    def comp_ge(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp(">=", operands[0], operands[1])
        return operands[0] if operands else None
    
    # Métodos para sumas y restas
    def sum_add(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("+", operands[0], operands[1])
        return operands[0] if operands else None
        
    def sum_sub(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("-", operands[0], operands[1])
        return operands[0] if operands else None
    
    # Métodos para multiplicación y división
    def term_mul(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("*", operands[0], operands[1])
        return operands[0] if operands else None
        
    def term_div(self, *args):
        operands = [arg for arg in args if not isinstance(arg, Token)]
        if len(operands) >= 2:
            return BinaryOp("/", operands[0], operands[1])
        return operands[0] if operands else None

    def number(self, tok):
        return Number(int(tok.value))

    def string(self, tok):
        return String(tok.value[1:-1])

    def variable(self, tok):
        return Variable(tok.value)

def parse(code: str) -> Program:
    """Parsea código SmallC y retorna un AST completo."""
    parser = Lark(GRAMMAR, parser="earley")
    tree = parser.parse(code)
    return ASTTransformer().transform(tree)