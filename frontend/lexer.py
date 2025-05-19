# frontend/parser.py
from lark import Lark, Transformer

smallc_grammar = """
start: program

program: (function | declaration)+

function: type ID "(" params ")" "{" statement* "}"
type: INT_TYPE
INT_TYPE: "int"
params: (param ("," param)*)?
param: type ID
declaration: type ID ";"

statement: return_stmt | declaration | expression ";"
return_stmt: "return" expression ";"

expression: add_expr
add_expr: mul_expr ("+" mul_expr)*
mul_expr: atom ("*" atom)*
atom: NUMBER | ID | "(" expression ")"

NUMBER: /-?\d+/
ID: /[a-zA-Z_][a-zA-Z0-9_]*/

%ignore / |\t|\r/
%ignore "//" /.*/
"""

class SmallCTransformer(Transformer):
    def start(self, items):
        return {"program": items}
    
    def function(self, items):
        return {"function": {
            "type": items[0],
            "name": items[1],
            "params": items[2],
            "body": items[3:]
        }}
    
    # ... más reglas de transformación ...

def parse(code):
    parser = Lark(smallc_grammar, parser="lalr", transformer=SmallCTransformer())
    return parser.parse(code)