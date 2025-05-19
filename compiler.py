# compiler.py
from frontend.parser import parse
from backend.riscv import RiscVGenerator
import json
import lark # Necesario para isinstance(obj, lark.Tree)

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

def compile_smallc(source):
    ast = parse(source)
    generator = RiscVGenerator()
    asm_code = generator.generate(ast)
    return asm_code

def compile_smallc(source):
    ast = parse(source)
    print("--- AST Generado ---")
    try:
        print(json.dumps(ast, indent=2)) # Intenta con el serializador normal primero
    except TypeError:
        print("FALLÓ json.dumps normal. Intentando con serializador personalizado para depuración:")
        print(json.dumps(ast, indent=2, default=custom_json_serializer)) # Usa el serializador personalizado
    print("--------------------")

    generator = RiscVGenerator()
    generator.generate(ast)

    print("--- Salida Ensamblador (lista de instrucciones antes de unir) ---")
    print(generator.output) # Imprime la lista de instrucciones generadas
    print("--------------------------------------------------")

    return "\n".join(generator.output)

if __name__ == "__main__":
    # El path al archivo de ejemplo es examples/example.sc
    # El path al archivo de salida es output.asm
    try:
        with open("examples/example.sc", "r") as f:
            source = f.read()
            print("--- Código Fuente ---")
            print(source)
            print("---------------------")
            asm_code = compile_smallc(source)

        with open("output.asm", "w") as outfile:
            outfile.write(asm_code)

        if asm_code.strip():
            print("El código ensamblador ha sido guardado en output.asm")
        else:
            print("ADVERTENCIA: output.asm está vacío. Revisa la salida de depuración (AST e instrucciones).")

    except FileNotFoundError:
        print("Error: No se pudo encontrar 'examples/example.sc'. Asegúrate de que el archivo existe en esa ruta.")
    except Exception as e:
        print(f"Ocurrió un error durante la compilación: {e}")
        import traceback
        traceback.print_exc()