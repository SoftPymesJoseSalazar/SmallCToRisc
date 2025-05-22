from frontend.ast_nodes import *
from lark import Tree, Token

class RiscVGenerator:
    def __init__(self):
        self.output = []
        self.regs = [f"x{i}" for i in range(5, 15)]
        self.reg_idx = 0
        self.symtab = {}
        self.sp_offset = 0
        self.label_count = 0
        self.current_function = ""
        self.globals = set()  # Para registrar variables globales
        self.has_main = False  # Para verificar si hay una función main

    def new_reg(self):
        r = self.regs[self.reg_idx]
        self.reg_idx = (self.reg_idx + 1) % len(self.regs)
        return r

    def new_label(self):
        self.label_count += 1
        return f"L{self.label_count}"

    def emit(self, code):
        self.output.append(code)

    def _flatten(self, items):
        """
        Aplanar una lista de nodos de alto nivel que pueden
        venir como {'type':'top_level', 'children':[...]}
        o {'type':'global_decl', 'children':[...]}.
        Devuelve una lista de nodos reales (Declaration, Function, etc.).
        """
        flat = []
        for node in items:
            # Si es un dict con tipo top_level o global_decl
            if isinstance(node, dict) and node.get('type') in ('top_level','global_decl'):
                ch = node.get('children',[]) or node.get('statements',[])
                flat.extend(self._flatten(ch))
            else:
                flat.append(node)
        return flat

    def generate(self, program: Program) -> str:
        """Genera código ensamblador RISC-V para todo el programa."""
        # 0) Extraer y aplanar nodos de alto nivel
        if hasattr(program, 'functions'):
            raw = program.functions
        elif hasattr(program, 'statements'):
            raw = program.statements
        elif isinstance(program, dict):
            raw = program.get('children', []) or program.get('statements', [])
        else:
            raw = []
        items = self._flatten(raw)

        # 1) Detectar función main
        for node in items:
            if (isinstance(node, Function) or (isinstance(node, dict) and node.get('type')=='function')) \
               and (getattr(node, 'name', node.get('name')) == "main"):
                self.has_main = True
                break

        # 2) Sección .data: globals y arrays
        self.emit(".data")
        for node in items:
            # Procesamos todos los nodos de declaración global
            if (isinstance(node, ArrayDeclaration) or 
                isinstance(node, Declaration) or
                (isinstance(node, dict) and node.get('type') in ('array_declaration', 'declaration'))):
                self.visit(node)

        # 3) Sección .text y etiqueta _start
        self.emit(".text")
        self.emit("  .globl _start")
        self.emit("_start:")
        
        # Inicialización de globals (asignaciones top-level)
        for node in items:
            # Procesamos TODOS los nodos, dejando que visit() decida qué hacer
            self.visit(node)

        # Llamar a main si existe
        if self.has_main:
            self.emit("  call main")
        # Exit syscall
        self.emit("  li a0, 0")
        self.emit("  li a7, 93")
        self.emit("  ecall")

        # 4) Generar cada función (prólogos, cuerpo y epílogos)
        for node in items:
            if (isinstance(node, Function) or 
                (isinstance(node, dict) and node.get('type')=='function')):
                # establecer current_function para los retornos
                name = node.name if isinstance(node, Function) else node.get('name')
                self.current_function = name
                self.visit(node)

        return "\n".join(self.output)

    def visit(self, node):
        """Visita un nodo del AST y retorna el resultado"""
        # Si es None, retornar
        if node is None:
            return None
        
        # Manejo de nodos de tipo 'stmt'
        if isinstance(node, dict) and node.get('type') == 'stmt' and 'children' in node:
            # Si 'stmt' contiene children, visitar el primer hijo
            if node['children'] and len(node['children']) > 0:
                return self.visit(node['children'][0])
            return None
        
        # Manejo de bloques en nodos dict
        if isinstance(node, dict) and node.get('type') == 'block' and 'statements' in node:
            # Para cada declaración en el bloque
            for stmt in node['statements']:
                self.visit(stmt)
            return None
        
        # Si es un diccionario con 'type', procesarlo según su tipo
        if isinstance(node, dict) and 'type' in node:
            # Mapeo de nombres de métodos para tipos de nodos
            type_method_map = {
                'declaration': 'visit_Declaration',
                'assignment': 'visit_Assignment',
                'if': 'visit_If',
                'while': 'visit_While',
                'return': 'visit_Return',
                'function_call': 'visit_FuncCall',
                'binary_op': 'visit_BinaryOp',
                'variable': 'visit_Variable',
                'number': 'visit_Number',
                'function': 'visit_Function',
                'block': 'visit_Block',
                'parameter': 'visit_Parameter',
                'program': 'visit_Program',
                'array_access': 'visit_ArrayAccess',
                'array_declaration': 'visit_ArrayDeclaration',
                'multi_declaration': 'visit_MultiDeclaration',
                'for': 'visit_For'
            }
            
            # Si tenemos un método para este tipo
            if node['type'] in type_method_map:
                method_name = type_method_map[node['type']]
                if hasattr(self, method_name):
                    # Crear objeto AST temporal para pasarlo al método
                    from frontend.ast_nodes import Declaration, Assignment, If, While, Return, FuncCall, BinaryOp, Variable, Number, Block, Parameter, Program, Function
                    
                    if node['type'] == 'declaration':
                        obj = Declaration(
                            node.get('var_name', ''), 
                            node.get('var_type', ''), 
                            node.get('value', None)
                        )
                        return getattr(self, method_name)(obj)
                    elif node['type'] == 'assignment':
                        obj = Assignment(
                            node.get('var_name', ''), 
                            node.get('value', None)
                        )
                        return getattr(self, method_name)(obj)
                    # Otros tipos aquí...
                    
                    # Si llegamos aquí, tratamos el nodo como está
                    return getattr(self, method_name)(node)
            
            # Si no tenemos un método específico, pero es un nodo "hijo"
            if 'children' in node and isinstance(node['children'], list) and node['children']:
                return self.visit(node['children'][0])
                
        # Manejo de árboles de Lark
        if isinstance(node, Tree):
            if 'children' in dir(node) and node.children:
                # Convertir Tree.children a una lista normal
                children = list(node.children)
                
                # Para cada hijo en el árbol
                results = []
                for child in children:
                    result = self.visit(child)
                    if result is not None:
                        results.append(result)
                
                # Retornar el último resultado no-None
                return results[-1] if results else None
        
        # Si es un Token, obtén su valor
        if isinstance(node, Token) or (hasattr(node, 'type') and hasattr(node, 'value')):
            return node.value
        
        # Si es una lista, procesar cada elemento
        if isinstance(node, list):
            results = []
            for item in node:
                result = self.visit(item)
                if result is not None:
                    results.append(result)
            return results[-1] if results else None
        
        # Procedimiento normal para nodos AST
        method = f"visit_{type(node).__name__}"
        if hasattr(self, method):
            return getattr(self, method)(node)
        else:
            print(f"ADVERTENCIA: No hay método visit_{type(node).__name__} para {node}")
            # Intenta devolver un valor si es posible
            if hasattr(node, 'value'):
                return node.value
            return None

    def visit_Function(self, fn):
        """Genera código para una función."""
        # Extraer información de la función según el formato del nodo
        if isinstance(fn, dict):
            fn_name = fn.get('name', '')
            fn_params = fn.get('params', [])
            fn_body = fn.get('body', {'statements': []})
        else:
            fn_name = fn.name
            fn_params = fn.params
            fn_body = fn.body
        
        # Registrar si es main
        if fn_name == "main":
            self.has_main = True
        
        # Inicializar tabla de símbolos para esta función
        self.symtab = {}
        self.sp_offset = 0
        self.reg_idx = 0
        self.current_function = fn_name
        
        # Depuración: mostrar parámetros recibidos
        print(f"DEBUG: Función {fn_name} con parámetros: {fn_params}")
        
        # Cabecera de función
        self.emit(f".globl {fn_name}")
        self.emit(f"{fn_name}:")
        
        # Prólogo - reservar espacio para variables locales y registros salvados
        frame_size = 32  # Espacio mínimo para ra, s0 y algunos temporales
        
        # Prólogo estándar
        self.emit(f"  addi sp, sp, -{frame_size}")
        self.emit("  sw ra, 28(sp)")
        self.emit("  sw s0, 24(sp)")
        self.emit(f"  addi s0, sp, {frame_size}")  # s0 apunta al antiguo sp
        
        # Registrar parámetros en la tabla de símbolos
        for i, p in enumerate(fn_params):
            # Extraer el nombre del parámetro según su formato
            param_name = None
            if isinstance(p, str):
                param_name = p
            elif isinstance(p, dict):
                if 'param_name' in p:
                    param_name = p['param_name']
                elif 'name' in p:
                    param_name = p['name']
            elif hasattr(p, 'name'):
                param_name = p.name
            
            if not param_name:
                param_name = f"param{i}"
                print(f"ADVERTENCIA: No se pudo extraer nombre del parámetro {i}, usando {param_name}")
            
            # Guardar parámetro en el stack y registrarlo en la tabla de símbolos
            off = -4 * (i + 1)
            self.symtab[param_name] = off
            self.emit(f"  sw a{i}, {off}(s0)   # param {param_name}")
        
        # Depuración: mostrar tabla de símbolos después de registrar parámetros
        print(f"DEBUG: SYMTAB inicial para {fn_name}: {self.symtab}")
        
        # Pre-procesar declaraciones para reservar espacio
        self.pre_process_declarations(fn_body)
        
        # Depuración: mostrar tabla de símbolos después de pre-procesar
        print(f"DEBUG: SYMTAB final para {fn_name}: {self.symtab}")
        
        # Visitar el cuerpo de la función
        self.visit(fn_body)
        
        # Epílogo
        self.emit(f".exit_{fn_name}:")
        self.emit("  lw s0, 24(sp)")
        self.emit("  lw ra, 28(sp)")
        self.emit(f"  addi sp, sp, {frame_size}")
        self.emit("  ret")

    def pre_process_declarations(self, node):
        """Procesa todas las declaraciones en un bloque primero para registrarlas en la tabla de símbolos"""
        # Si es un dict con tipo bloque, procesar sus statements
        if isinstance(node, dict) and node.get('type') == 'block' and 'statements' in node:
            for stmt in node['statements']:
                self.pre_process_declarations(stmt)
            return
        
        # Si es un bloque normal
        if hasattr(node, 'statements'):
            for stmt in node.statements:
                self.pre_process_declarations(stmt)
            return
        
        # Si es un stmt con children, procesar el primer hijo
        if isinstance(node, dict) and node.get('type') == 'stmt' and 'children' in node:
            if node['children'] and len(node['children']) > 0:
                self.pre_process_declarations(node['children'][0])
            return
        
        # Si es una declaración, procesarla
        if (isinstance(node, Declaration) or 
            (isinstance(node, dict) and node.get('type') == 'declaration')):
            
            if isinstance(node, Declaration):
                var_name = node.var_name
            else:
                var_name = node.get('var_name', '')
            
            self.sp_offset -= 4
            self.symtab[var_name] = self.sp_offset
            print(f"REGISTRO: Variable {var_name} en offset {self.sp_offset}")
        
        # Si es un if, procesar ambos bloques
        if isinstance(node, dict) and node.get('type') == 'if':
            if 'body' in node:
                self.pre_process_declarations(node['body'])
            if 'else_body' in node and node['else_body']:
                self.pre_process_declarations(node['else_body'])
        elif isinstance(node, If):
            self.pre_process_declarations(node.true_body)
            if node.false_body:
                self.pre_process_declarations(node.false_body)
        
        # Si es un while, procesar su bloque
        if isinstance(node, dict) and node.get('type') == 'while':
            if 'body' in node:
                self.pre_process_declarations(node['body'])
        elif isinstance(node, While):
            self.pre_process_declarations(node.body)

    def visit_Block(self, blk: Block):
        for stmt in blk.statements:
            self.visit(stmt)

    def visit_Declaration(self, d: Declaration):
        self.sp_offset -= 4
        self.symtab[d.var_name] = self.sp_offset
        if d.value:
            r = self.visit(d.value)
            self.emit(f"  sw {r}, {self.sp_offset}(s0)")
        else:
            self.emit(f"  sw zero, {self.sp_offset}(s0)")

    def visit_Assignment(self, a: Assignment):
        """
        Genera la instrucción sw para
        - var = expr
        - arr[idx] = expr
        (tanto global como local).
        """
        # 1) evaluamos el valor a guardar
        val_reg = self.visit(a.value)

        # 2) ¿es acceso a array?
        if isinstance(a.var_name, ArrayAccess):
            arr  = a.var_name.array_name
            idxr = self.visit(a.var_name.index)
            addr = self.new_reg()

            # dirección base del array
            if arr in self.symtab:
                # array local
                base_off = self.symtab[arr]
                self.emit(f"  addi {addr}, s0, {base_off}   # base local {arr}")
            else:
                # array global
                self.emit(f"  la {addr}, {arr}   # base global {arr}")

            # calcular offset = idx * 4
            tmp = self.new_reg()
            self.emit(f"  slli {tmp}, {idxr}, 2       # {arr} index*4")
            self.emit(f"  add {addr}, {addr}, {tmp}   # dirección elemento")

            # almacenar
            self.emit(f"  sw {val_reg}, 0({addr})   # {arr}[...] = {val_reg}")
            return

        # 3) asignación a variable normal
        var_name = a.var_name.name if hasattr(a.var_name, 'name') else a.var_name
        if var_name in self.symtab:
            # local / parámetro
            off = self.symtab[var_name]
            self.emit(f"  sw {val_reg}, {off}(s0)   # {var_name} = {val_reg}")
        else:
            # global
            self.emit(f"  la t0, {var_name}      # addr {var_name}")
            self.emit(f"  sw {val_reg}, 0(t0)   # {var_name} = {val_reg}")

    def visit_If(self, node):
        """Genera código para una sentencia if."""
        # Obtener etiquetas para saltos
        L_else = self.new_label()
        L_end = self.new_label()
        
        # Evaluar condición
        r_cond = self.visit(node.condition)
        self.emit(f"  beq {r_cond}, zero, {L_else}")
        
        # Cuerpo del if (then)
        if hasattr(node.true_body, 'statements'):
            # Si es un bloque, visitar sus statements
            self.visit(node.true_body)
        elif hasattr(node.true_body, 'children'):
            # Si es un nodo con children, visitar cada hijo
            for child in node.true_body.children:
                self.visit(child)
        else:
            # Si es una sentencia simple, visitarla directamente
            self.visit(node.true_body)
        
        # Saltar al final si hay else
        if node.false_body:
            self.emit(f"  j {L_end}")
        
        # Etiqueta para else
        self.emit(f"{L_else}:")
        
        # Cuerpo del else (opcional)
        if node.false_body:
            if hasattr(node.false_body, 'statements'):
                # Si es un bloque, visitar sus statements
                self.visit(node.false_body)
            elif hasattr(node.false_body, 'children'):
                # Si es un nodo con children, visitar cada hijo
                for child in node.false_body.children:
                    self.visit(child)
            else:
                # Si es una sentencia simple, visitarla directamente
                self.visit(node.false_body)
            
            # Etiqueta para el final
            self.emit(f"{L_end}:")

    def visit_While(self, node):
        """Genera código para una sentencia while."""
        # Obtener etiquetas para saltos
        L_start = self.new_label()
        L_end = self.new_label()
        
        # Etiqueta de inicio del bucle
        self.emit(f"{L_start}:")
        
        # Evaluar condición
        r_cond = self.visit(node.condition)
        self.emit(f"  beq {r_cond}, zero, {L_end}")
        
        # Cuerpo del while
        if hasattr(node.body, 'statements'):
            # Si es un bloque, visitar sus statements
            self.visit(node.body)
        elif hasattr(node.body, 'children'):
            # Si es un nodo con children, visitar cada hijo
            for child in node.body.children:
                self.visit(child)
        else:
            # Si es una sentencia simple, visitarla directamente
            self.visit(node.body)
        
        # Saltar al inicio para evaluar la condición de nuevo
        self.emit(f"  j {L_start}")
        
        # Etiqueta para el final del bucle
        self.emit(f"{L_end}:")

    def visit_Return(self, node):
        """Genera código para una sentencia return."""
        # Extraer la expresión de retorno según el formato del nodo
        if isinstance(node, dict):
            expr = node.get('value')
        else:
            expr = node.expr if hasattr(node, 'expr') else None
        
        # Si hay una expresión de retorno, evaluarla y moverla a a0
        if expr:
            try:
                reg = self.visit(expr)
                self.emit(f"  mv a0, {reg}   # valor de retorno")
            except Exception as e:
                print(f"ERROR en Return: {e}")
                # Intentamos recuperarnos: si es un Variable, intentar evaluarla directamente
                if hasattr(expr, 'name') or (isinstance(expr, dict) and 'name' in expr):
                    var_name = expr.name if hasattr(expr, 'name') else expr.get('name')
                    if var_name in self.symtab:
                        off = self.symtab[var_name]
                        self.emit(f"  lw a0, {off}(s0)  # Recuperación variable {var_name}")
                    else:
                        print(f"ERROR: Variable {var_name} no encontrada en symtab: {self.symtab}")
                        self.emit(f"  li a0, 0  # ERROR: Variable no encontrada")
        
        # Salto al epílogo de la función actual
        self.emit(f"  j .exit_{self.current_function}")

    def visit_BinaryOp(self, b):
        """Genera código para operaciones binarias."""
        # Evaluar lado izquierdo y derecho primero
        lreg = self.visit(b.left)
        rreg = self.visit(b.right)
        
        # Conseguir registro para el resultado
        result = self.new_reg()
        
        # Convertir operadores numéricos a cadenas
        op = str(b.op) if isinstance(b.op, (int, float)) else b.op
        
        # Mapeo de operadores numéricos
        op_map = {
            '0': '==', '1': '+', '2': '-', '3': '*', '4': '/',
            '5': '<', '6': '>', '7': '<=', '8': '>=', '9': '!=',
            '10': '&&', '11': '||'
        }
        
        # Si es un número como string, convertirlo a su equivalente
        if op in op_map:
            op = op_map[op]
        
        # Operaciones aritméticas
        if op == '+':
            self.emit(f"  add {result}, {lreg}, {rreg}")
        elif op == '-':
            self.emit(f"  sub {result}, {lreg}, {rreg}")
        elif op == '*':
            self.emit(f"  mul {result}, {lreg}, {rreg}")
        elif op == '/':
            self.emit(f"  div {result}, {lreg}, {rreg}")
        # Operaciones de comparación
        elif op == '==' or op == '0':
            self.emit(f"  xor {result}, {lreg}, {rreg}")
            self.emit(f"  seqz {result}, {result}")
        elif op == '!=' or op == '9':
            self.emit(f"  xor {result}, {lreg}, {rreg}")
            self.emit(f"  snez {result}, {result}")
        elif op == '<' or op == '5':
            self.emit(f"  slt {result}, {lreg}, {rreg}")
        elif op == '<=' or op == '7':
            self.emit(f"  sgt {result}, {lreg}, {rreg}")
            self.emit(f"  xori {result}, {result}, 1")
        elif op == '>' or op == '6':
            self.emit(f"  sgt {result}, {lreg}, {rreg}")
        elif op == '>=' or op == '8':
            self.emit(f"  slt {result}, {lreg}, {rreg}")
            self.emit(f"  xori {result}, {result}, 1")
        # Operaciones lógicas
        elif op == '&&' or op == '10':
            self.emit(f"  snez {result}, {lreg}")
            temp = self.new_reg()
            self.emit(f"  snez {temp}, {rreg}")
            self.emit(f"  and {result}, {result}, {temp}")
        elif op == '||' or op == '11':
            self.emit(f"  or {result}, {lreg}, {rreg}")
            self.emit(f"  snez {result}, {result}")
        else:
            print(f"ADVERTENCIA: Operador desconocido '{op}', tratando como suma")
            self.emit(f"  add {result}, {lreg}, {rreg}")
        
        return result

    def visit_Number(self, n: Number):
        r = self.new_reg()
        self.emit(f"  li {r}, {n.value}")
        return r

    def visit_Variable(self, node):
        """Genera código para acceder a una variable."""
        # Extraer el nombre de la variable según el formato del nodo
        if isinstance(node, dict):
            var_name = node.get('name')
        else:
            var_name = node.name
        
        # Obtener un registro para el resultado
        r = self.new_reg()
        
        # Verificar si la variable existe en la tabla de símbolos
        if var_name not in self.symtab:
            print(f"ERROR: Variable '{var_name}' no encontrada en la tabla de símbolos: {self.symtab}")
            self.emit(f"  li {r}, 0  # ERROR: Variable {var_name} no encontrada, usando 0")
            return r
        
        # Cargar el valor de la variable desde su offset en el stack
        off = self.symtab[var_name]
        self.emit(f"  lw {r}, {off}(s0)  # carga {var_name}")
        return r

    def visit_FuncCall(self, node):
        """Genera código para una llamada a función."""
        # Extraer nombre y argumentos según el formato del nodo
        if isinstance(node, dict):
            func_name = node.get('name')
            args = node.get('args', [])
        else:
            func_name = node.name
            args = node.args
        
        # Evaluar y mover cada argumento a los registros a0-a7
        for i, arg in enumerate(args):
            areg = self.visit(arg)
            self.emit(f"  mv a{i}, {areg}   # arg {i}")
        
        # Llamar a la función
        self.emit(f"  call {func_name}")
        
        # Mover el resultado (a0) a un registro temporal
        ret = self.new_reg()
        self.emit(f"  mv {ret}, a0   # resultado de {func_name}")
        return ret

    def visit_ArrayAccess(self, node):
        # Cargar la dirección base del array
        array_name = node.array_name
        
        # Si es un token, obtener su valor
        if hasattr(array_name, 'value'):
            array_name = array_name.value
        
        # Calcular el índice
        index_reg = self.visit(node.index)
        
        # Obtener un registro para el resultado
        result_reg = self.new_reg()
        
        # Si es una variable global
        if array_name in self.globals:
            # Calcular dirección: base_addr + index * 4
            self.emit(f"  la {result_reg}, {array_name}   # Dirección base del array")
            temp_reg = self.new_reg()
            self.emit(f"  slli {temp_reg}, {index_reg}, 2   # Índice * 4 (tamaño de int)")
            self.emit(f"  add {result_reg}, {result_reg}, {temp_reg}   # Dirección del elemento")
            
            # Cargar el valor desde la dirección calculada
            value_reg = self.new_reg()
            self.emit(f"  lw {value_reg}, 0({result_reg})   # Cargar valor de {array_name}[{index_reg}]")
            
            return value_reg
        else:
            # Arrays locales - implementación simplificada
            print(f"ADVERTENCIA: Acceso a array local no implementado completamente: {array_name}")
            return self.new_reg()  # Retornar un registro temporal

    def visit_ArrayDeclaration(self, node: ArrayDeclaration):
        """Reserva espacio en .data para un array global."""
        name = node.var_name
        typ  = node.var_type
        size = node.size
        self.globals.add(name)
        self.emit("  .align 2")
        self.emit(f"  .globl {name}")
        self.emit(f"  {name}: .space {size * 4}   # array global {typ} {name}[{size}]")

    def visit_MultiDeclaration(self, m: MultiDeclaration):
        """Maneja declaraciones múltiples de variables"""
        for var_name in m.var_names:
            # Similar a visit_Declaration pero sin valor inicial
            self.sp_offset -= 4
            self.symtab[var_name] = self.sp_offset
            self.emit(f"  sw zero, {self.sp_offset}(s0)  # {var_name} = 0 (inicialización)")
            
            # Necesitamos también pre-procesar estas declaraciones

    def visit_For(self, node: For):
        L_cond = self.new_label()
        L_body = self.new_label()
        L_end = self.new_label()

        # 1. Inicialización
        if node.init:
            self.visit(node.init)
        
        self.emit(f"  j {L_cond}")

        # 2. Cuerpo del bucle
        self.emit(f"{L_body}:")
        self.visit(node.body)

        # 3. Actualización
        if node.update:
            self.visit(node.update)
        
        # 4. Comprobación de condición
        self.emit(f"{L_cond}:")
        if node.condition:
            r_cond = self.visit(node.condition)
            self.emit(f"  bne {r_cond}, zero, {L_body}")
        else:
            self.emit(f"  j {L_body}")  # Bucle infinito si no hay condición

        # 5. Fin del bucle
        self.emit(f"{L_end}:")
