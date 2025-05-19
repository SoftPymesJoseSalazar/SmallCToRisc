from lark import Lark, Transformer, Token, v_args
import lark  # Necesario para isinstance(obj, lark.Tree)

# Definir la gramática usando la sintaxis EBNF de Lark
grammar = r"""
start: program

program: (function | declaration)*

function: type_spec ID "(" params? ")" "{" statement* "}"
        | "void" ID "(" params? ")" "{" statement* "}"

type_spec: "int" -> int_type
         | "char" -> char_type

params: param ("," param)*
param: type_spec ID

statement: declaration
         | assignment ";"
         | return_stmt ";"
         | if_stmt
         | while_stmt
         | for_stmt
         | increment ";"
         | block
         | function_call ";"

block: "{" statement* "}"

declaration: type_spec ID ("=" expression)? ";"
           | type_spec ID "[" INT "]" ";"
           | type_spec ID ("," ID)* ";"

assignment: lvalue "=" expression

lvalue: ID | ID "[" expression "]"

increment: lvalue "++" | lvalue "--"

return_stmt: "return" expression?

if_stmt: "if" "(" expression ")" statement ("else" statement)?
while_stmt: "while" "(" expression ")" statement
for_stmt: "for" "(" assignment ";" expression ";" increment ")" statement

expression: logic_expr

logic_expr: comp_expr (("&&"|"||") comp_expr)*
comp_expr: sum_expr (("=="|"!="|"<"|">"|"<="|">=") sum_expr)*
sum_expr: term (("+"|"-") term)*
term: factor (("*"|"/") factor)*
factor: INT 
      | STRING 
      | lvalue 
      | function_call 
      | "(" expression ")"

function_call: ID "(" (expression ("," expression)*)? ")"

// Tokens
INT: /[0-9]+/
ID: /[a-zA-Z_][a-zA-Z0-9_]*/
STRING: /"[^"]*"/

// Ignorar comentarios y espacios en blanco
COMMENT: /\/\/[^\n]*/
BLOCK_COMMENT: /\/\*(.|\n)*?\*\//

%import common.WS
%ignore WS
%ignore COMMENT
%ignore BLOCK_COMMENT
"""

@v_args(inline=True)
class ASTTransformer(Transformer):
    def start(self, program):
        return program
    
    def program(self, *items):
        return list(items)
    
    def function(self, ret_type, name, *items):
        # Extraer parámetros y cuerpo
        params = []
        body_start = 0
        
        for i, item in enumerate(items):
            if item == "(":
                continue
            elif item == ")":
                body_start = i + 1
                break
            elif isinstance(item, list):  # Lista de parámetros
                params = item
                body_start = i + 1
                
        body = items[body_start:]
        # Quitar las llaves del cuerpo
        if body and body[0] == "{":
            body = body[1:]
        if body and body[-1] == "}":
            body = body[:-1]
        
        return {
            "type": "function",
            "return_type": ret_type,
            "name": name.value if hasattr(name, 'value') else name["name"],
            "params": params,
            "body": list(body)
        }
    
    # Nuevos métodos para manejar los tipos sin argumentos
    def int_type(self):
        return "int"
    
    def char_type(self):
        return "char"
    
    def type_spec(self, type_val):
        return type_val
    
    def params(self, *params):
        return list(params)
    
    def param(self, type_val, name):
        return {
            "type": "parameter",
            "param_type": type_val,
            "param_name": name.value if hasattr(name, 'value') else name["name"]
        }
    
    def statement(self, stmt):
        return stmt
    
    def block(self, *statements):
        return {
            "type": "block",
            "statements": list(statements)
        }
    
    def declaration(self, type_val, name, *rest):
        # Declaración simple: type ID;
        if len(rest) == 0 or rest[0] == ";":
            return {
                "type": "declaration",
                "var_type": type_val,
                "var_name": name.value if hasattr(name, 'value') else name["name"],
                "value": None
            }
        # Declaración con inicialización: type ID = expr;
        elif rest[0] == "=" and len(rest) >= 2:
            return {
                "type": "declaration",
                "var_type": type_val,
                "var_name": name.value if hasattr(name, 'value') else name["name"],
                "value": rest[1]
            }
        # Declaración de array: type ID[size];
        elif rest[0] == "[" and len(rest) >= 3 and rest[2] == "]":
            return {
                "type": "array_declaration",
                "var_type": type_val,
                "var_name": name.value if hasattr(name, 'value') else name["name"],
                "size": int(rest[1].value)
            }
        # Declaraciones múltiples: type ID, ID, ...;
        elif rest[0] == "," and len(rest) > 1:
            declarations = [{
                "type": "declaration",
                "var_type": type_val,
                "var_name": name.value if hasattr(name, 'value') else name["name"],
                "value": None
            }]
            
            for i in range(1, len(rest), 2):
                if i+1 < len(rest) and rest[i] == ",":
                    declarations.append({
                        "type": "declaration",
                        "var_type": type_val,
                        "var_name": rest[i+1].value if hasattr(rest[i+1], 'value') else rest[i+1]["name"],
                        "value": None
                    })
            
            return {
                "type": "multi_declaration",
                "declarations": declarations
            }
        
        return {
            "type": "declaration",
            "var_type": type_val,
            "var_name": name.value if hasattr(name, 'value') else name["name"],
            "value": None
        }
    
    def assignment(self, lvalue, expr):
        if isinstance(lvalue, dict) and lvalue.get("type") == "array_access":
            return {
                "type": "array_assignment",
                "array": lvalue["array"],
                "index": lvalue["index"],
                "value": expr
            }
        else:
            return {
                "type": "assignment",
                "var_name": lvalue.value if hasattr(lvalue, 'value') else lvalue,
                "value": expr
            }
    
    def lvalue(self, name, *rest):
        if len(rest) >= 2 and rest[0] == "[" and rest[1] != "]":
            return {
                "type": "array_access",
                "array": name.value if hasattr(name, 'value') else name["name"],
                "index": rest[1]
            }
        return name
    
    def increment(self, lvalue, op):
        return {
            "type": "increment",
            "var": lvalue,
            "op": op.value
        }
    
    def return_stmt(self, *args):
        if len(args) > 0:
            return {
                "type": "return",
                "expression": args[0]
            }
        return {
            "type": "return",
            "expression": None
        }
    
    def if_stmt(self, condition, true_body, *rest):
        result = {
            "type": "if",
            "condition": condition,
            "true_body": true_body,
            "false_body": None
        }
        
        if len(rest) > 1 and rest[0] == "else":
            result["false_body"] = rest[1]
        
        return result
    
    def while_stmt(self, condition, body):
        return {
            "type": "while",
            "condition": condition,
            "body": body
        }
    
    def for_stmt(self, init, condition, update, body):
        return {
            "type": "for",
            "init": init,
            "condition": condition,
            "update": update,
            "body": body
        }
    
    def expression(self, expr):
        return expr
    
    def logic_expr(self, left, *rest):
        if not rest or len(rest) < 2:
            return left
            
        result = left
        i = 0
        while i + 1 < len(rest):
            op = rest[i]
            right = rest[i+1]
            result = {
                "type": "binary_op",
                "op": op.value,
                "left": result,
                "right": right
            }
            i += 2
            
        return result
    
    def comp_expr(self, left, *rest):
        if not rest or len(rest) < 2:
            return left
            
        result = left
        i = 0
        while i + 1 < len(rest):
            op = rest[i]
            right = rest[i+1]
            result = {
                "type": "binary_op",
                "op": op.value,
                "left": result,
                "right": right
            }
            i += 2
            
        return result
    
    def sum_expr(self, left, *rest):
        if not rest or len(rest) < 2:
            return left
            
        result = left
        i = 0
        while i + 1 < len(rest):
            op = rest[i]
            right = rest[i+1]
            result = {
                "type": "binary_op",
                "op": op.value,
                "left": result,
                "right": right
            }
            i += 2
            
        return result
    
    def term(self, left, *rest):
        if not rest or len(rest) < 2:
            return left
            
        result = left
        i = 0
        while i + 1 < len(rest):
            op = rest[i]
            right = rest[i+1]
            result = {
                "type": "binary_op",
                "op": op.value,
                "left": result,
                "right": right
            }
            i += 2
            
        return result
    
    def factor(self, value):
        return value
    
    def function_call(self, name, *args):
        # Filtrar argumentos eliminando paréntesis y comas
        filtered_args = [arg for arg in args if arg != "(" and arg != ")" and arg != ","]
        
        return {
            "type": "function_call",
            "name": name.value if hasattr(name, 'value') else name["name"],
            "args": filtered_args
        }
    
    def INT(self, token):
        return {
            "type": "number",
            "value": int(token.value)
        }
    
    def ID(self, token):
        return {
            "type": "variable",
            "name": token.value
        }
    
    def STRING(self, token):
        # Quitar las comillas
        string_value = token.value[1:-1]
        return {
            "type": "string",
            "value": string_value
        }

def parse(code):
    parser = Lark(grammar, parser="lalr", transformer=ASTTransformer())
    return parser.parse(code)