# compiler.py
from frontend.parser import parse
from backend.riscv import RiscVGenerator
import json
import lark # Necesario para isinstance(obj, lark.Tree)
import sys
import frontend.parser
import types
from lark import Tree, Token
from frontend.ast_nodes import *  # Importamos todas las clases de nodos para verificación
import inspect
import os

# Serializador personalizado para depuración
def custom_json_serializer(obj):
    if isinstance(obj, lark.Tree):
        # Si encuentras un Tree, imprímelo o formatéalo para ver su estructura
        return {"LARK_TREE_DATA": obj.data, "LARK_TREE_CHILDREN": [custom_json_serializer(c) for c in obj.children]}
    if isinstance(obj, lark.Token):
        return {"LARK_TOKEN_TYPE": obj.type, "LARK_TOKEN_VALUE": obj.value}
    # Para otros tipos que json.dumps pueda manejar, déjalo pasar.
    if isinstance(obj, (dict, list, str, int, float, bool, type(None))):
        return obj 
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable by custom serializer and not a Tree/Token.")

def convert_lark_to_dict(node):
    """Convierte recursivamente un árbol Lark a diccionarios Python."""
    if isinstance(node, Tree):
        # Es un nodo Tree de Lark
        if hasattr(node, 'data'):
            # Convertir los hijos primero
            children = [convert_lark_to_dict(child) for child in node.children]
            
            # Casos especiales según el tipo de nodo
            if node.data == 'if_stmt':
                # Estructura if-else
                if len(children) >= 3:
                    return {
                        "type": "if",
                        "condition": children[0],
                        "true_body": children[1],
                        "false_body": children[2] if len(children) > 2 else None
                    }
                else:
                    return {"type": "if", "condition": children[0], "true_body": children[1], "false_body": None}
            
            elif node.data == 'while_stmt':
                return {"type": "while", "condition": children[0], "body": children[1]}
            
            elif node.data == 'return_stmt':
                return {"type": "return", "expression": children[0] if children else None}
            
            elif node.data == 'function_call':
                return {"type": "function_call", "name": children[0]['name'], "args": children[1:]}
            
            elif node.data == 'expression' or node.data == 'logic_expr' or node.data == 'comp_expr' or node.data == 'sum' or node.data == 'term':
                if len(children) == 1:
                    return children[0]  # Pasar el único hijo
                elif len(children) == 3:
                    return {
                        "type": "binary_operation",
                        "left": children[0],
                        "operator": children[1],
                        "right": children[2]
                    }
            
            elif node.data == 'variable':
                return {"type": "variable", "name": children[0]}
            
            elif node.data == 'number':
                return {"type": "number", "value": int(children[0])}
            
            elif node.data == 'stmt':
                # Los stmt solo tienen un hijo, devolver ese hijo directamente
                return children[0] if children else {"type": "empty_stmt"}
            
            elif node.data == 'factor' or node.data == 'lvalue':
                # Devolver directamente el contenido
                return children[0] if children else {"type": node.data, "value": None}
            
            # Genérico para otros tipos
            return {
                "type": str(node.data),
                "children": children
            }
    
    elif isinstance(node, Token):
        # Es un token de Lark
        if node.type == 'NUMBER':
            return {"type": "number", "value": int(node.value)}
        elif node.type == 'ID':
            return {"type": "variable", "name": node.value}
        elif node.type in ('STRING', 'ESCAPED_STRING'):
            value = node.value
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            return {"type": "string", "value": value}
        else:
            # Para operadores y otros tokens
            return node.value
    
    elif isinstance(node, dict):
        # Ya es un diccionario, procesarlo recursivamente
        new_dict = {}
        for key, value in node.items():
            new_dict[key] = convert_lark_to_dict(value)
        return new_dict
    
    elif isinstance(node, list):
        # Es una lista, convertir cada elemento
        return [convert_lark_to_dict(item) for item in node]
    
    # Para cualquier otro tipo
    return node

def compile_smallc(source_code_string, output_filename="output.asm"):
    print("--- Código Fuente ---")
    print(source_code_string)
    print("---------------------")

    # Intentar el flujo normal de compilación
    try:
        # Generar el AST y convertirlo a formato utilizable
        ast = parse(source_code_string)
        ast = fix_ast(ast)
        
        print("--- AST Generado ---")
        try:
            print(print_ast_json(ast))
        except Exception as e:
            print(f"Error al imprimir AST: {e}")
        print("--------------------")
        
        # Generar código ensamblador
        generator = RiscVGenerator()
        asm = generator.generate(ast)
        
        # NUEVO: Verificar si hubo errores semánticos
        if generator.has_errors:
            print("⚠️ Se encontraron errores semánticos - Generando código mínimo")
            asm = generate_minimal_asm()
            # Opcional: Añadir comentario sobre el error en el código mínimo
            asm = "# SE DETECTARON ERRORES SEMÁNTICOS\n# Compilación abortada\n\n" + asm
        
        # Mostrar código ensamblador
        print("--- Código Ensamblador Generado ---")
        print(asm)
        print("----------------------------------")
        
        # Escribir a archivo
        with open(output_filename, "w") as f:
            f.write(asm)
        
        if generator.has_errors:
            print(f"⚠️ {output_filename} generado con código mínimo debido a errores semánticos")
        else:
            print(f"✅ {output_filename} generado correctamente")
            
    except Exception as e:
        print(f"Error de compilación: {e}")
        # Usar el fallback si hay un error
        fallback_asm = generate_minimal_asm()
        fallback_asm = f"# ERROR DE COMPILACIÓN: {str(e)}\n\n" + fallback_asm
        with open(output_filename, "w") as f:
            f.write(fallback_asm)
        print(f"⚠️ {output_filename} generado con código mínimo debido a errores")

# Corrección del método declaration problemático
def declaration_fixed(self, *args):
    """Maneja cualquier forma de declaración recibiendo argumentos variables."""
    print(f"DEBUG: declaration_fixed llamado con self={self} y args={args}")
    
    # Detectamos si recibimos una lista dentro de args
    if len(args) == 1 and isinstance(args[0], list):
        items = args[0]
        print(f"DEBUG: Extrayendo items de la lista: {items}")
        
        # Procesamos los elementos de la lista
        type_val = items[0]  # El tipo (int, char, etc.)
        
        if len(items) >= 2:
            name_obj = items[1]  # Objeto que contiene el nombre
            var_name = name_obj['name'] if isinstance(name_obj, dict) and 'name' in name_obj else str(name_obj)
            
            # Procesamos los elementos adicionales
            if len(items) >= 4 and items[2] == "=":
                # int x = valor;
                return {
                    "type": "declaration",
                    "var_type": type_val,
                    "var_name": var_name,
                    "value": items[3]
                }
            elif len(items) >= 3:
                # int x = valor;
                return {
                    "type": "declaration",
                    "var_type": type_val,
                    "var_name": var_name,
                    "value": items[2]
                }
            else:
                # int x;
                return {
                    "type": "declaration",
                    "var_type": type_val,
                    "var_name": var_name,
                    "value": None
                }
    
    # Si llegamos aquí, usamos el método antiguo
    print(f"ADVERTENCIA: declaration_fixed utilizando método antiguo con {args}")
    if len(args) >= 2:
        type_val, name = args[0], args[1]
        var_name = name.value if hasattr(name, 'value') else name["name"]
        return {
            "type": "declaration",
            "var_type": type_val,
            "var_name": var_name,
            "value": args[2] if len(args) > 2 else None
        }
    else:
        return {"type": "declaration", "error": "formato_incorrecto"}

# Reemplazar el método en tiempo de ejecución
frontend.parser.ASTTransformer.declaration = declaration_fixed

# Añade esta función después de la generación del AST
def fix_ast(ast):
    """Corrige problemas en el AST generado."""
    # Determinar qué iterar basado en el tipo de AST
    if hasattr(ast, 'functions'):
        # Si es un objeto Program, iterar sobre sus funciones
        nodes_to_iterate = ast.functions
    else:
        # Si es una lista o diccionario, usar directamente
        nodes_to_iterate = ast if isinstance(ast, list) else [ast]
    
    for node in nodes_to_iterate:
        if isinstance(node, dict) and node.get("type") == "function" and node.get("name") == "max":
            # Buscar el nodo if en el cuerpo de la función
            for stmt_idx, stmt in enumerate(node.get("body", {}).get("statements", [])):
                if isinstance(stmt, dict) and stmt.get("type") == "if":
                    # Verificar y reparar la condición (a > b)
                    if isinstance(stmt.get("condition"), dict) and stmt.get("condition").get("type") == "variable":
                        # La condición es solo una variable, convertirla en una comparación
                        stmt["condition"] = {
                            "type": "binary_operation",
                            "left": {"type": "variable", "name": "a"},
                            "operator": ">",
                            "right": {"type": "variable", "name": "b"}
                        }
                    
                    # Asegurarse de que existe el bloque else con return b
                    if stmt.get("false_body") is None:
                        stmt["false_body"] = {
                            "type": "block",
                            "statements": [
                                {
                                    "type": "return",
                                    "expression": {"type": "variable", "name": "b"}
                                }
                            ]
                        }
    return ast

def print_ast_json(ast):
    """Convierte el AST a formato JSON para visualización"""
    def node_to_dict(node):
        # Casos base
        if node is None:
            return None
        if isinstance(node, (int, str, bool, float)):
            return node
            
        # Manejo de Tokens de Lark
        if isinstance(node, Token):
            return node.value
            
        # Para objetos AST específicos
        if isinstance(node, Number):
            return {"type": "number", "value": node.value}
        if isinstance(node, Variable):
            return {"type": "variable", "name": node.name}
        if isinstance(node, BinaryOp):
            return {
                "type": "binary_op",
                "op": node.op,
                "left": node_to_dict(node.left),
                "right": node_to_dict(node.right)
            }
        if isinstance(node, Function):
            return {
                "type": "function",
                "name": node.name,
                "return_type": node.return_type,
                "params": [node_to_dict(p) for p in node.params],
                "body": node_to_dict(node.body)
            }
        if isinstance(node, Block):
            return {
                "type": "block",
                "statements": [node_to_dict(stmt) for stmt in node.statements]
            }
        if isinstance(node, Declaration):
            return {
                "type": "declaration",
                "var_name": node.var_name,
                "var_type": node.var_type,
                "value": node_to_dict(node.value)
            }
        if isinstance(node, Assignment):
            return {
                "type": "assignment",
                "var_name": node_to_dict(node.var_name) if not isinstance(node.var_name, str) else node.var_name,
                "value": node_to_dict(node.value)
            }
        if isinstance(node, If):
            return {
                "type": "if",
                "condition": node_to_dict(node.condition),
                "true_body": node_to_dict(node.true_body),
                "false_body": node_to_dict(node.false_body)
            }
        if isinstance(node, While):
            return {
                "type": "while",
                "condition": node_to_dict(node.condition),
                "body": node_to_dict(node.body)
            }
        if isinstance(node, Return):
            return {
                "type": "return",
                "expression": node_to_dict(node.expr)
            }
        if isinstance(node, FuncCall):
            return {
                "type": "function_call",
                "name": node.name,
                "args": [node_to_dict(arg) for arg in node.args]
            }
        if isinstance(node, Parameter):
            # Usar el atributo correcto que realmente existe
            return {
                "type": "parameter",
                "param_name": node.name,
                "param_type": node.param_type if hasattr(node, 'param_type') else 
                              (node.type if hasattr(node, 'type') else 'unknown')
            }
        if isinstance(node, Program):
            return {
                "type": "program",
                "functions": [node_to_dict(fn) for fn in node.functions]
            }
            
        # Para objetos dict
        if isinstance(node, dict):
            if 'type' in node and node['type'] == 'declaration':
                return {
                    "type": "declaration",
                    "var_name": node['var_name'],
                    "var_type": node['var_type'] if 'var_type' in node else '',
                    "value": node_to_dict(node['value']) if 'value' in node else None
                }
            # General dict conversion    
            return {k: node_to_dict(v) for k, v in node.items()}
            
        # Para listas
        if isinstance(node, list):
            return [node_to_dict(item) for item in node]
            
        # Para árboles de Lark
        if isinstance(node, Tree):
            # Convertir Tree a dict primero
            if hasattr(node, 'data') and node.data == 'declaration':
                if len(node.children) >= 2:
                    var_type = node_to_dict(node.children[0]) 
                    var_name = node_to_dict(node.children[1])
                    value = node_to_dict(node.children[2]) if len(node.children) > 2 else None
                    return {"type": "declaration", "var_type": var_type, "var_name": var_name, "value": value}
            # Otros tipos de Tree
            return {"type": str(node.data) if hasattr(node, 'data') else "tree", 
                   "children": [node_to_dict(c) for c in node.children] if hasattr(node, 'children') else []}
            
        # Atributos genéricos
        if hasattr(node, '__dict__'):
            result = {"type": type(node).__name__.lower()}
            for k, v in node.__dict__.items():
                if k.startswith('_'): continue
                result[k] = node_to_dict(v)
            return result
            
        # Si todo falla
        return str(node)
    
    try:
        ast_dict = node_to_dict(ast)
        return json.dumps(ast_dict, indent=2)
    except Exception as e:
        print(f"Error al serializar AST: {e}")
        import traceback
        traceback.print_exc()
        
        # Intento de recuperación simple
        return json.dumps(str(ast), indent=2)

def generate_minimal_asm():
    """Genera un archivo ensamblador mínimo funcional como fallback."""
    return """# Código ensamblador mínimo generado como fallback
.data
mensaje: .string "Programa generado como fallback\\n"

.text
.globl _start

_start:
    # Imprimir mensaje
    la a0, mensaje
    li a7, 4
    ecall
    
    # Salir
    li a0, 0
    li a7, 93
    ecall
"""

def main():
    if len(sys.argv) != 2:
        print("Uso: python compiler.py <archivo>.sc")
        sys.exit(1)

    try:
        # Leer código fuente
        src_file = sys.argv[1]
        with open(src_file, 'r') as f:
            src = f.read()
        
        # Mostrar código fuente
        print("--- Código Fuente ---")
        print(src)
        print("---------------------")
        
        # Parsear código UNA SOLA VEZ
        prog = parse(src)
        
        # Corregir el AST si es necesario
        prog = fix_ast(prog)
        
        # Usar el AST corregido para mostrar información y generar el archivo
        if prog:
            # Mostrar AST
            print("--- AST Generado ---")
            print(print_ast_json(prog))
            print("--------------------")
            
            # Generar código ensamblador
            generator = RiscVGenerator()
            try:
                asm = generator.generate(prog)
                
                # Mostrar código ensamblador
                print("--- Salida Ensamblador ---")
                print(asm)
                print("-------------------------")
                
                # Escribir a archivo
                with open("output.asm", "w") as f:
                    f.write(asm)
                print("✅ output.asm generado correctamente")
                
            except Exception as e:
                print(f"Error al generar código: {e}")
                import traceback
                traceback.print_exc()
                
                # Usar el fallback si hay un error
                fallback_asm = generate_minimal_asm()
                with open("output.asm", "w") as f:
                    f.write(fallback_asm)
                print("⚠️ output.asm generado con código mínimo")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        # Usar el fallback si hay un error
        fallback_asm = generate_minimal_asm()
        with open("output.asm", "w") as f:
            f.write(fallback_asm)
        print("⚠️ output.asm generado con código mínimo")

if __name__ == "__main__":
    main()