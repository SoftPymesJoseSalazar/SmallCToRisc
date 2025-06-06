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
        self.current_function = ""  # Inicializar como string vacío
        self.globals = set()  # Para registrar variables globales
        self.has_main = False  # Para verificar si hay una función main
        # Mapeo de registros para seguimiento de variables
        self.reg_to_var = {}  # Registra qué variable está en qué registro
        
        # Nueva adición: Tabla de símbolos para funciones declaradas
        self.declared_functions = set()
        self.has_errors = False  # Indicador de errores semánticos

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

        # NUEVO: Primera pasada para recopilar todas las funciones declaradas
        self.declared_functions = set()
        for node in items:
            if isinstance(node, Function):
                self.declared_functions.add(node.name)
            elif isinstance(node, dict) and node.get('type') == 'function':
                self.declared_functions.add(node.get('name'))
        
        # Añadir funciones intrínsecas/de biblioteca si es necesario
        self.declared_functions.add("print")  # Ejemplo de función intrínseca
        self.declared_functions.add("exit")   # Ejemplo de función intrínseca
        
        # Resto del código de generación si no hay errores semánticos
        
        # 1) Detectar función main
        for node in items:
            if isinstance(node, Function) and node.name == "main":
                self.has_main = True
                break
            elif (isinstance(node, dict) and node.get('type') == 'function' and node.get('name') == "main"):
                self.has_main = True
                break

        # 2) Sección .data: globals y arrays
        self.emit(".data")
        self.current_function = ""  # Asegurar que estamos en contexto global
        for node in items:
            # Solo procesar declaraciones globales en esta fase
            if (isinstance(node, Declaration) or 
                isinstance(node, ArrayDeclaration) or
                isinstance(node, MultiDeclaration) or
                (isinstance(node, dict) and node.get('type') in ('declaration', 'array_declaration', 'multideclaration'))):
                self.visit(node)

        # 3) Sección .text y etiqueta _start
        self.emit(".text")
        self.emit("  .globl _start")
        self.emit("_start:")
        
        # Inicialización de globals (asignaciones top-level)
        self.current_function = ""  # Asegurar que estamos en contexto global
        for node in items:
            # Solo procesar asignaciones globales en esta fase
            if (isinstance(node, Assignment) or
                (isinstance(node, dict) and node.get('type') == 'assignment')):
                self.visit(node)

        # Llamar a main si existe
        if self.has_main:
            self.emit("  call main")
            # El valor de retorno de main debería estar en a0
        # Exit syscall
        self.emit("  li a7, 93")
        self.emit("  ecall")

        # 4) Generar cada función (prólogos, cuerpo y epílogos)
        for node in items:
            if isinstance(node, Function):
                # establecer current_function para los retornos
                self.current_function = node.name
                self.visit(node)
            elif (isinstance(node, dict) and node.get('type') == 'function'):
                # establecer current_function para los retornos
                self.current_function = node.get('name', '')
                self.visit(node)

        return "\n".join(self.output)

    def visit(self, node):
        """Visita un nodo del AST y retorna el resultado"""
        # Si es None, retornar
        if node is None:
            return None
        
        # Procedimiento principal para nodos AST tipados
        method = f"visit_{type(node).__name__}"
        if hasattr(self, method):
            return getattr(self, method)(node)
        
        # --- COMPATIBILIDAD TEMPORAL CON FORMATOS ANTIGUOS ---
        # Este código debe eliminarse gradualmente
        
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
                    # DEPRECADO: Crear objeto AST temporal (esto debería eliminarse)
                    try:
                        # Intentar adaptar el nodo dict a su equivalente en AST
                        from frontend.ast_nodes import Declaration, Assignment, If, While, Return as ReturnNode, FuncCall, BinaryOp, Variable, Number, Block, Parameter, Program, Function
                        
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
                        elif node['type'] == 'return':
                            # Manejar return statement
                            expr = None
                            if 'children' in node and node['children']:
                                # Buscar la expresión en los children
                                for child in node['children']:
                                    if not isinstance(child, str) and child != ';':
                                        expr = child
                                        break
                            elif 'expression' in node:
                                expr = node['expression']
                            
                            return self.visit_Return(Return(expr))
                        elif node['type'] == 'multideclaration':
                            # Manejar declaración múltiple
                            var_type = node.get('var_type', '')
                            var_names = node.get('var_names', [])
                            obj = MultiDeclaration(var_type, var_names)
                            return self.visit_MultiDeclaration(obj)
                        elif node['type'] == 'if':
                            # Para if, crear un objeto If
                            condition = node['children'][0] if len(node['children']) > 0 else None
                            true_body = node['children'][1] if len(node['children']) > 1 else None
                            false_body = node['children'][2] if len(node['children']) > 2 and node['children'][2] is not None else None
                            from frontend.ast_nodes import If as IfNode
                            return self.visit_If(IfNode(condition, true_body, false_body))
                        elif node['type'] == 'while':
                            # Para while, crear un objeto While
                            condition = node['children'][0] if len(node['children']) > 0 else None
                            body = node['children'][1] if len(node['children']) > 1 else None
                            from frontend.ast_nodes import While as WhileNode
                            return self.visit_While(WhileNode(condition, body))
                        elif node['type'] == 'for_init':
                            # Para for_init, procesar el primer hijo (assignment)
                            if node['children'] and len(node['children']) > 0:
                                return self.visit(node['children'][0])
                            return None
                        else:
                            # Enviar el nodo dict tal cual
                            return getattr(self, method_name)(node)
                    except Exception as e:
                        print(f"ERROR al adaptar nodo dict a AST: {e}")
                        return getattr(self, method_name)(node)
            
            # Si no tenemos un método específico, pero es un nodo "hijo"
            if 'children' in node and isinstance(node['children'], list) and node['children']:
                return self.visit(node['children'][0])
        
        # Manejo de árboles de Lark (ESTO DEBERÍA ELIMINARSE)
        if isinstance(node, Tree):
            if hasattr(node, 'children') and node.children:
                # Convertir Tree.children a una lista normal
                children = list(node.children)
                
                # Casos especiales para diferentes tipos de Tree
                if node.data == 'stmt':
                    # Para stmt, procesar el primer hijo
                    if children:
                        return self.visit(children[0])
                elif node.data == 'return':
                    # Para return, crear un objeto Return
                    expr = None
                    for child in children:
                        if not isinstance(child, Token) or child.type != 'SEMICOLON':
                            expr = child
                            break
                    return self.visit_Return(Return(expr))
                elif node.data == 'if':
                    # Para if, crear un objeto If
                    condition = children[0] if len(children) > 0 else None
                    true_body = children[1] if len(children) > 1 else None
                    false_body = children[2] if len(children) > 2 and children[2] is not None else None
                    from frontend.ast_nodes import If as IfNode
                    return self.visit_If(IfNode(condition, true_body, false_body))
                elif node.data == 'while':
                    # Para while, crear un objeto While
                    condition = children[0] if len(children) > 0 else None
                    body = children[1] if len(children) > 1 else None
                    from frontend.ast_nodes import While as WhileNode
                    return self.visit_While(WhileNode(condition, body))
                elif node.data == 'for_init':
                    # Para for_init, procesar el primer hijo (assignment)
                    if children and len(children) > 0:
                        return self.visit(children[0])
                    return None
        
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
        
        # Si llegamos aquí, no tenemos un manejador específico
        print(f"ADVERTENCIA: No hay método visit_{type(node).__name__} para {node}")
        # Intenta devolver un valor si es posible
        if hasattr(node, 'value'):
            return node.value
        return None

    def visit_Function(self, fn):
        """Genera código para una función."""
        # Extraer información de la función según el formato del nodo
        if isinstance(fn, Function):
            fn_name = fn.name
            fn_params = fn.params
            fn_body = fn.body
        else:
            # Compatibilidad temporal con formato diccionario
            fn_name = fn.get('name', '')
            fn_params = fn.get('params', [])
            fn_body = fn.get('body', {'statements': []})
        
        # Registrar si es main
        if fn_name == "main":
            self.has_main = True
        
        # Inicializar tabla de símbolos para esta función
        self.symtab = {}
        self.sp_offset = 0  # Inicializar a 0, se ajustará después de procesar parámetros
        self.reg_idx = 0
        self.current_function = fn_name
        
        # Comentario descriptivo sobre la función
        self.emit(f"# ====== FUNCIÓN: {fn_name}({', '.join([p.param_type + ' ' + p.name if isinstance(p, Parameter) else 'param' for p in fn_params])}) ======")
        
        # Cabecera de función
        self.emit(f".globl {fn_name}")
        self.emit(f"{fn_name}:")
        
        # Procesamiento de parámetros - guardamos su posición en el stack
        last_param_offset = 0
        for i, p in enumerate(fn_params):
            # Extraer el nombre del parámetro según su formato
            param_name = None
            if isinstance(p, Parameter):
                param_name = p.name
            elif isinstance(p, dict):
                param_name = p.get('param_name') or p.get('name')
            else:
                param_name = f"param{i}"
                print(f"ADVERTENCIA: Formato de parámetro no reconocido: {p}")
            
            # Guardar parámetro en el stack y registrarlo en la tabla de símbolos
            off = -4 * (i + 1)
            self.symtab[param_name] = off
            last_param_offset = off  # Guardar el último offset usado por parámetros
        
        # CORRECCIÓN: Inicializar sp_offset para que comience DESPUÉS de los parámetros
        self.sp_offset = last_param_offset
        
        # Pre-procesar declaraciones para reservar espacio
        required_locals_space = self.pre_process_declarations(fn_body)
        
        # MEJORA: Cálculo dinámico del tamaño del frame
        saved_regs_space = 8  # ra y s0
        total_locals_space = abs(self.sp_offset)  # Convertir a positivo
        frame_size = total_locals_space + saved_regs_space
        frame_size = (frame_size + 15) & ~15  # Alinear a 16 bytes
        
        # Prólogo con comentarios detallados
        self.emit(f"# ----- Prólogo de función '{fn_name}' -----")
        self.emit(f"# Reservar frame de {frame_size} bytes: {total_locals_space} para variables locales + {saved_regs_space} para registros salvados")
        self.emit(f"  addi sp, sp, -{frame_size}  # Expandir stack frame")
        self.emit(f"  sw ra, {frame_size-4}(sp)   # Guardar dirección de retorno")
        self.emit(f"  sw s0, {frame_size-8}(sp)   # Guardar frame pointer anterior")
        self.emit(f"  addi s0, sp, {frame_size}   # Establecer nuevo frame pointer")
        
        # Ahora transferimos los argumentos desde a0-aN a sus posiciones en el stack
        if fn_params:
            self.emit(f"# Copiar argumentos de registros a0-a{len(fn_params)-1} a stack frame")
        for i, p in enumerate(fn_params):
            param_name = p.name if isinstance(p, Parameter) else f"param{i}"
            off = self.symtab[param_name]
            self.emit(f"  sw a{i}, {off}(s0)      # Guardar parámetro '{param_name}' en stack")
        
        # Visitar el cuerpo de la función
        self.emit(f"# ----- Cuerpo de función '{fn_name}' -----")
        self.visit(fn_body)
        
        # Epílogo con comentarios detallados
        self.emit(f"# ----- Epílogo de función '{fn_name}' -----")
        self.emit(f".exit_{fn_name}:")
        self.emit(f"  lw s0, {frame_size-8}(sp)   # Restaurar frame pointer anterior")
        self.emit(f"  lw ra, {frame_size-4}(sp)   # Restaurar dirección de retorno")
        self.emit(f"  addi sp, sp, {frame_size}   # Liberar stack frame ({frame_size} bytes)")
        self.emit("  ret                       # Retornar al llamador")
        self.emit(f"# ====== FIN FUNCIÓN {fn_name} ======\n")

    def pre_process_declarations(self, node):
        """Procesa todas las declaraciones en un bloque primero para registrarlas en la tabla de símbolos.
        Retorna el espacio total requerido para variables locales."""
        # MEJORA: Retornar el espacio necesario para variables locales
        initial_sp_offset = self.sp_offset
        
        # Si es un bloque tipado (Block de ast_nodes)
        if isinstance(node, Block):
            for stmt in node.statements:
                self.pre_process_declarations(stmt)
        # Compatibilidad temporal con formato dict
        elif isinstance(node, dict) and node.get('type') == 'block' and 'statements' in node:
            for stmt in node.get('statements', []):
                self.pre_process_declarations(stmt)
        # Si es una declaración, procesarla
        elif isinstance(node, Declaration):
            self.sp_offset -= 4
            self.symtab[node.var_name] = self.sp_offset
            print(f"REGISTRO: Variable {node.var_name} en offset {self.sp_offset}")
        # Si es una declaración múltiple, procesar cada variable
        elif isinstance(node, MultiDeclaration):
            for var_name in node.var_names:
                self.sp_offset -= 4
                self.symtab[var_name] = self.sp_offset
                print(f"REGISTRO: Variable {var_name} en offset {self.sp_offset}")
        # Compatibilidad temporal con formato dict para declaraciones
        elif isinstance(node, dict) and node.get('type') == 'declaration':
            var_name = node.get('var_name', '')
            self.sp_offset -= 4
            self.symtab[var_name] = self.sp_offset
            print(f"REGISTRO: Variable {var_name} en offset {self.sp_offset}")
        # Si es una declaración múltiple, procesar cada variable
        elif isinstance(node, dict) and node.get('type') == 'multideclaration':
            var_names = node.get('var_names', [])
            for var_name in var_names:
                self.sp_offset -= 4
                self.symtab[var_name] = self.sp_offset
                print(f"REGISTRO: Variable {var_name} en offset {self.sp_offset}")
        # Si es un if, procesar ambos bloques
        elif isinstance(node, If):
            self.pre_process_declarations(node.true_body)
            if node.false_body:
                self.pre_process_declarations(node.false_body)
        # Compatibilidad temporal con formato dict para if
        elif isinstance(node, dict) and node.get('type') == 'if':
            if 'body' in node or 'true_body' in node:
                body = node.get('body') or node.get('true_body')
                self.pre_process_declarations(body)
            if ('else_body' in node and node['else_body']) or ('false_body' in node and node['false_body']):
                else_body = node.get('else_body') or node.get('false_body')
                self.pre_process_declarations(else_body)
        # Si es un while, procesar su bloque
        elif isinstance(node, While):
            self.pre_process_declarations(node.body)
        # Compatibilidad temporal con formato dict para while
        elif isinstance(node, dict) and node.get('type') == 'while':
            if 'body' in node:
                self.pre_process_declarations(node.get('body'))
        # Si es un for, procesar inicialización y cuerpo
        elif isinstance(node, For):
            if node.init:
                self.pre_process_declarations(node.init)
            self.pre_process_declarations(node.body)
        
        # Retornar el espacio requerido para variables locales
        return abs(self.sp_offset - initial_sp_offset)

    def visit_Block(self, blk: Block):
        self.emit("  # Inicio de bloque")
        for stmt in blk.statements:
            self.visit(stmt)
        self.emit("  # Fin de bloque")

    def visit_Declaration(self, d: Declaration):
        """Genera código para una declaración de variable"""
        var_name = d.var_name
        var_type = d.var_type
        
        # Verificar si estamos dentro de una función o en nivel global
        if self.current_function == "":
            # VARIABLE GLOBAL - debe ir en sección .data
            self.globals.add(var_name)
            
            # Generar etiqueta en sección .data
            if d.value is not None:
                # Declaración con valor inicial - solo valores inmediatos
                immediate_val = self._get_immediate_value(d.value)
                self.emit(f"{var_name}: .word {immediate_val}")
            else:
                # Declaración sin valor inicial (inicializar a 0)
                self.emit(f"{var_name}: .word 0")
            
            # Registrar en tabla de símbolos como global
            self.symtab[var_name] = {'type': 'global', 'label': var_name}
            
        else:
            # VARIABLE LOCAL - debe ir en el stack
            self.emit(f"  # Declaración: {var_type} {var_name}")
            self.sp_offset += 4
            
            if d.value is not None:
                # Evaluar la expresión
                val_reg = self.visit(d.value)
                self.emit(f"  sw {val_reg}, -{self.sp_offset}(s0)   # Guardar '{var_name}' en stack")
            else:
                # Inicializar a cero
                self.emit(f"  sw zero, -{self.sp_offset}(s0)   # Inicializar '{var_name}' a 0")
            
            # Registrar en tabla de símbolos como local
            self.symtab[var_name] = {'type': 'local', 'offset': -self.sp_offset}
    
    def _get_immediate_value(self, expr):
        """Extrae el valor inmediato de una expresión simple para variables globales"""
        if isinstance(expr, Number):
            return expr.value
        elif isinstance(expr, dict) and expr.get('type') == 'number':
            return expr.get('value', 0)
        else:
            return 0  # Por defecto para expresiones complejas

    def visit_Assignment(self, a: Assignment):
        """Genera código para una asignación de variable"""
        var_name = a.var_name
        
        # Verificar si es una asignación a un elemento de array
        if isinstance(var_name, ArrayAccess) or (isinstance(var_name, dict) and var_name.get('type') == 'arrayaccess'):
            # ASIGNACIÓN A ELEMENTO DE ARRAY
            if isinstance(var_name, ArrayAccess):
                array_name = var_name.array_name
                index_expr = var_name.index
            else:
                array_name = var_name.get('array_name', '')
                index_expr = var_name.get('index', None)
            
            self.emit(f"  # Asignación a array: {array_name}[<índice>] = <expr>")
            
            # Evaluar la expresión del lado derecho
            val_reg = self.visit(a.value)
            
            # Evaluar el índice
            index_reg = self.visit(index_expr)
            
            # Si es un array global
            if array_name in self.globals:
                # Calcular dirección: base_addr + index * 4
                addr_reg = self.new_reg()
                self.emit(f"  la {addr_reg}, {array_name}    # Cargar dirección base del array global '{array_name}'")
                temp_reg = self.new_reg()
                self.emit(f"  slli {temp_reg}, {index_reg}, 2  # Multiplicar índice por 4 (tamaño de int)")
                self.emit(f"  add {addr_reg}, {addr_reg}, {temp_reg} # Calcular dirección del elemento")
                self.emit(f"  sw {val_reg}, 0({addr_reg})  # Guardar valor en {array_name}[<índice>]")
            else:
                # Arrays locales (si los hay)
                if array_name in self.symtab:
                    if isinstance(self.symtab[array_name], dict):
                        base_off = self.symtab[array_name].get('offset', 0)
                    else:
                        base_off = self.symtab[array_name]
                    
                    self.emit(f"# Asignación a array local '{array_name}' en offset {base_off}")
                    addr_reg = self.new_reg()
                    self.emit(f"  addi {addr_reg}, s0, {base_off} # Dirección base del array")
                    
                    offset_reg = self.new_reg()
                    self.emit(f"  slli {offset_reg}, {index_reg}, 2 # Convertir índice a bytes (×4)")
                    self.emit(f"  add {addr_reg}, {addr_reg}, {offset_reg} # Calcular dirección final")
                    
                    self.emit(f"  sw {val_reg}, 0({addr_reg}) # Guardar valor en array")
                else:
                    # Error: array no declarado
                    self.emit(f"# ERROR: Array '{array_name}' no encontrado")
            
            return val_reg
        
        # Si var_name es un string normal, continuar con la lógica original
        if not isinstance(var_name, str):
            var_name = str(var_name)
        
        # Verificar si la variable es global o local
        if var_name in self.globals or (var_name in self.symtab and isinstance(self.symtab[var_name], dict) and self.symtab[var_name].get('type') == 'global'):
            # ASIGNACIÓN A VARIABLE GLOBAL
            self.emit(f"  # Asignación global: {var_name} = <expr>")
            
            # Evaluar la expresión del lado derecho
            val_reg = self.visit(a.value)
            
            # Cargar la dirección de la variable global y guardar el valor
            addr_reg = self.new_reg()
            self.emit(f"  la {addr_reg}, {var_name}      # Cargar dirección de variable global '{var_name}'")
            self.emit(f"  sw {val_reg}, 0({addr_reg})    # Guardar valor en variable global '{var_name}'")
            
        elif var_name in self.symtab and isinstance(self.symtab[var_name], dict) and self.symtab[var_name].get('type') == 'local':
            # ASIGNACIÓN A VARIABLE LOCAL
            self.emit(f"  # Asignación local: {var_name} = <expr>")
            
            # Evaluar la expresión del lado derecho  
            val_reg = self.visit(a.value)
            
            # Obtener offset de la variable local
            offset = self.symtab[var_name]['offset']
            self.emit(f"  sw {val_reg}, {offset}(s0)          # Guardar valor en variable local '{var_name}'")
        elif var_name in self.symtab and isinstance(self.symtab[var_name], int):
            # ASIGNACIÓN A VARIABLE LOCAL (formato antiguo - entero como offset)
            self.emit(f"  # Asignación local: {var_name} = <expr>")
            
            # Evaluar la expresión del lado derecho  
            val_reg = self.visit(a.value)
            
            # Obtener offset de la variable local
            offset = self.symtab[var_name]
            self.emit(f"  sw {val_reg}, {offset}(s0)          # Guardar valor en variable local '{var_name}'")
        else:
            # Si no está en symtab, asumir que es una nueva variable local
            self.sp_offset += 4
            offset = -self.sp_offset
            self.symtab[var_name] = {'type': 'local', 'offset': offset}
            # Evaluar la expresión del lado derecho  
            val_reg = self.visit(a.value)
            self.emit(f"  sw {val_reg}, {offset}(s0)          # Guardar valor en variable local '{var_name}'")
        
        return val_reg

    def visit_If(self, node):
        """Genera código para una estructura if-else."""
        # Generar etiquetas para los bloques
        L_else = self.new_label()
        L_end = self.new_label()
        
        # Comentario descriptivo
        self.emit(f"  # ----- Estructura if-else -----")
        
        # 1. Evaluar la condición
        self.emit(f"  # Evaluación de condición if")
        r_cond = self.visit(node.condition)
        
        # 2. Instrucción de salto condicional - SOLUCIÓN DEL BUG
        # Si la condición es falsa (r_cond == 0), saltar al bloque else o al final
        if node.false_body:
            self.emit(f"  beq {r_cond}, zero, {L_else}  # Si condición es falsa, saltar a 'else'")
        else:
            self.emit(f"  beq {r_cond}, zero, {L_end}   # Si condición es falsa, saltar al final")
        
        # 3. Generar código para el bloque "then"
        self.emit(f"  # Inicio bloque 'then'")
        self.visit(node.true_body)
        
        # 4. Si hay un bloque "else", agregar salto para evitar su ejecución - SOLUCIÓN DEL BUG
        if node.false_body:
            self.emit(f"  j {L_end}                    # Saltar al final después de ejecutar 'then'")
            self.emit(f"{L_else}:                      # Etiqueta para bloque 'else'")
            self.emit(f"  # Inicio bloque 'else'")
            self.visit(node.false_body)
        
        # 5. Etiqueta de fin de la estructura if-else
        self.emit(f"{L_end}:                        # Fin de estructura if-else")
        self.emit(f"  # ----- Fin estructura if-else -----")

    def visit_While(self, node):
        """Genera código para una sentencia while."""
        # Obtener etiquetas para saltos
        L_start = self.new_label()
        L_end = self.new_label()
        
        # Comentario descriptivo del bucle while
        self.emit(f"  # ----- Inicio de bucle while -----")
        
        # Etiqueta de inicio del bucle
        self.emit(f"{L_start}:                              # Inicio de la evaluación de condición while")
        
        # Evaluar condición
        self.emit(f"  # Evaluar condición del bucle")
        r_cond = self.visit(node.condition)
        self.emit(f"  beq {r_cond}, zero, {L_end}          # Si condición es falsa, salir del bucle")
        
        # Cuerpo del while
        self.emit(f"  # Cuerpo del bucle while")
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
        self.emit(f"  j {L_start}                         # Volver al inicio para reevaluar condición")
        
        # Etiqueta para el final del bucle
        self.emit(f"{L_end}:                              # Fin del bucle while")
        self.emit(f"  # ----- Fin de bucle while -----")

    def visit_Return(self, node):
        """Genera código para una sentencia return."""
        self.emit(f"  # ----- Return statement -----")
        
        # 1. Evaluar la expresión de retorno (si existe)
        if node.expr:
            self.emit(f"  # Evaluar expresión de retorno")
            reg_result = self.visit(node.expr)
            
            # 2. Mover el resultado a a0 (registro de valor de retorno) - SOLUCIÓN DEL BUG
            self.emit(f"  mv a0, {reg_result}           # Colocar valor de retorno en a0")
        else:
            # Si no hay expresión, retornar 0 por defecto
            self.emit(f"  li a0, 0                    # Return sin valor (default 0)")
        
        # 3. Saltar al epílogo de la función - SOLUCIÓN DEL BUG
        self.emit(f"  j .exit_{self.current_function}  # Saltar al epílogo de la función")

    def visit_BinaryOp(self, b):
        """Genera código para operaciones binarias."""
        # Evaluar lado izquierdo y derecho primero
        self.emit(f"  # Evaluar operando izquierdo")
        lreg = self.visit(b.left)
        self.emit(f"  # Evaluar operando derecho")
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
        
        # Descripción legible de la operación
        op_desc = {
            '+': 'suma', '-': 'resta', '*': 'multiplicación', '/': 'división',
            '==': 'igualdad', '!=': 'desigualdad', 
            '<': 'menor que', '>': 'mayor que', 
            '<=': 'menor o igual que', '>=': 'mayor o igual que',
            '&&': 'AND lógico', '||': 'OR lógico'
        }.get(op, op)
        
        self.emit(f"  # Operación binaria: {op_desc}")
        
        # Operaciones aritméticas
        if op == '+':
            self.emit(f"  add {result}, {lreg}, {rreg}      # {result} = {lreg} + {rreg}")
        elif op == '-':
            self.emit(f"  sub {result}, {lreg}, {rreg}      # {result} = {lreg} - {rreg}")
        elif op == '*':
            self.emit(f"  mul {result}, {lreg}, {rreg}      # {result} = {lreg} * {rreg}")
        elif op == '/':
            self.emit(f"  div {result}, {lreg}, {rreg}      # {result} = {lreg} / {rreg}")
        # Operaciones de comparación
        elif op == '==' or op == '0':
            self.emit(f"  xor {result}, {lreg}, {rreg}      # XOR para comparar bits")
            self.emit(f"  seqz {result}, {result}           # {result} = 1 si {lreg} == {rreg}, 0 en caso contrario")
        elif op == '!=' or op == '9':
            self.emit(f"  xor {result}, {lreg}, {rreg}      # XOR para comparar bits")
            self.emit(f"  snez {result}, {result}           # {result} = 1 si {lreg} != {rreg}, 0 en caso contrario")
        elif op == '<' or op == '5':
            self.emit(f"  slt {result}, {lreg}, {rreg}      # {result} = 1 si {lreg} < {rreg}, 0 en caso contrario")
        elif op == '<=' or op == '7':
            self.emit(f"  sgt {result}, {lreg}, {rreg}      # Comprobar si {lreg} > {rreg}")
            self.emit(f"  xori {result}, {result}, 1        # Negar resultado: {result} = 1 si {lreg} <= {rreg}")
        elif op == '>' or op == '6':
            self.emit(f"  sgt {result}, {lreg}, {rreg}      # {result} = 1 si {lreg} > {rreg}, 0 en caso contrario")
        elif op == '>=' or op == '8':
            self.emit(f"  slt {result}, {lreg}, {rreg}      # Comprobar si {lreg} < {rreg}")
            self.emit(f"  xori {result}, {result}, 1        # Negar resultado: {result} = 1 si {lreg} >= {rreg}")
        # Operaciones lógicas
        elif op == '&&' or op == '10':
            self.emit(f"  snez {result}, {lreg}             # Convertir {lreg} a booleano (0 o 1)")
            temp = self.new_reg()
            self.emit(f"  snez {temp}, {rreg}               # Convertir {rreg} a booleano (0 o 1)")
            self.emit(f"  and {result}, {result}, {temp}    # {result} = {lreg} && {rreg}")
        elif op == '||' or op == '11':
            self.emit(f"  or {result}, {lreg}, {rreg}       # Combinar bits con OR")
            self.emit(f"  snez {result}, {result}           # {result} = 1 si {lreg} || {rreg} es verdadero")
        else:
            print(f"ADVERTENCIA: Operador desconocido '{op}', tratando como suma")
            self.emit(f"  add {result}, {lreg}, {rreg}      # ADVERTENCIA: Operador desconocido '{op}', tratado como suma")
        
        return result

    def visit_Number(self, n: Number):
        r = self.new_reg()
        self.emit(f"  li {r}, {n.value}                # Cargar constante {n.value}")
        return r

    def visit_Variable(self, node):
        """Genera código para acceder a una variable"""
        # Extraer el nombre de la variable
        if isinstance(node, Variable):
            var_name = node.name
        elif isinstance(node, dict):
            var_name = node.get('name', '')
        else:
            var_name = str(node)
        
        reg = self.new_reg()
        
        # Verificar si es variable global o local
        if var_name in self.globals or (var_name in self.symtab and isinstance(self.symtab[var_name], dict) and self.symtab[var_name].get('type') == 'global'):
            # VARIABLE GLOBAL
            self.emit(f"  la {reg}, {var_name}               # Cargar dirección de variable global '{var_name}'")
            self.emit(f"  lw {reg}, 0({reg})                # Cargar valor de variable global '{var_name}'")
        elif var_name in self.symtab and isinstance(self.symtab[var_name], dict) and 'offset' in self.symtab[var_name]:
            # VARIABLE LOCAL (formato nuevo)
            offset = self.symtab[var_name]['offset']
            self.emit(f"  lw {reg}, {offset}(s0)               # Cargar valor de variable local '{var_name}'")
        elif var_name in self.symtab and isinstance(self.symtab[var_name], int):
            # VARIABLE LOCAL (formato antiguo - entero como offset)
            offset = self.symtab[var_name]
            self.emit(f"  lw {reg}, {offset}(s0)               # Cargar valor de variable local '{var_name}'")
        else:
            # Variable no declarada - marcar error pero generar código válido
            self.has_errors = True
            self.emit(f"  # ERROR: Variable '{var_name}' no declarada")
            self.emit(f"  li {reg}, 0                       # Valor por defecto para variable no declarada")
        
        return reg

    def visit_FuncCall(self, node):
        """Genera código para una llamada a función."""
        # Extraer nombre y argumentos según el formato del nodo
        if isinstance(node, dict):
            func_name = node.get('name')
            args = node.get('args', [])
        else:
            func_name = node.name
            args = node.args
        
        # NUEVO: Verificar si la función está declarada
        if func_name not in self.declared_functions:
            error_msg = f"ERROR: Llamada a función no declarada '{func_name}'"
            print(error_msg)
            self.emit(f"  # {error_msg}")
            self.has_errors = True
            # Retornar un registro temporal para no interrumpir la generación
            # Aunque este código no sea correcto, permite continuar la compilación
            # para encontrar más errores
            return self.new_reg()
        
        # Comentario descriptivo de la llamada
        args_desc = f"{len(args)} argumento{'s' if len(args) != 1 else ''}"
        self.emit(f"# Llamada a función: {func_name}({args_desc})")
        
        # Evaluar y mover cada argumento a los registros a0-a7
        for i, arg in enumerate(args):
            self.emit(f"# Preparar argumento {i+1}")
            areg = self.visit(arg)
            self.emit(f"  mv a{i}, {areg}               # Colocar argumento {i+1} en a{i}")
        
        # Llamar a la función
        self.emit(f"  call {func_name}                # Llamar a función")
        
        # Mover el resultado (a0) a un registro temporal
        ret = self.new_reg()
        self.emit(f"  mv {ret}, a0                   # Guardar resultado de '{func_name}' en {ret}")
        return ret

    def visit_ArrayAccess(self, node):
        # Cargar la dirección base del array
        array_name = node.array_name
        
        # Si es un token, obtener su valor
        if hasattr(array_name, 'value'):
            array_name = array_name.value
        
        # Comentario descriptivo del acceso al array
        self.emit(f"# Acceso a array: {array_name}[<índice>]")
        
        # Calcular el índice
        self.emit(f"# Calcular índice del array")
        index_reg = self.visit(node.index)
        
        # Obtener un registro para el resultado
        result_reg = self.new_reg()
        
        # Si es una variable global
        if array_name in self.globals:
            # Calcular dirección: base_addr + index * 4
            self.emit(f"  la {result_reg}, {array_name}    # Cargar dirección base del array global '{array_name}'")
            temp_reg = self.new_reg()
            self.emit(f"  slli {temp_reg}, {index_reg}, 2  # Multiplicar índice por 4 (tamaño de int)")
            self.emit(f"  add {result_reg}, {result_reg}, {temp_reg} # Calcular dirección del elemento")
            
            # Cargar el valor desde la dirección calculada
            value_reg = self.new_reg()
            self.emit(f"  lw {value_reg}, 0({result_reg})  # Cargar valor de {array_name}[<índice>]")
            
            return value_reg
        else:
            # Arrays locales
            if array_name in self.symtab:
                base_off = self.symtab[array_name]
                self.emit(f"# Acceso a array local '{array_name}' en offset {base_off}")
                addr_reg = self.new_reg()
                self.emit(f"  addi {addr_reg}, s0, {base_off} # Dirección base del array")
                
                offset_reg = self.new_reg()
                self.emit(f"  slli {offset_reg}, {index_reg}, 2 # Convertir índice a bytes (×4)")
                self.emit(f"  add {addr_reg}, {addr_reg}, {offset_reg} # Calcular dirección final")
                
                value_reg = self.new_reg()
                self.emit(f"  lw {value_reg}, 0({addr_reg}) # Cargar valor del array")
                return value_reg
            else:
                # Error: array no declarado
                print(f"ERROR: Array '{array_name}' no encontrado")
                self.emit(f"# ERROR: Array '{array_name}' no encontrado")
                return self.new_reg()  # Retornar un registro temporal

    def visit_ArrayDeclaration(self, node: ArrayDeclaration):
        """Reserva espacio en .data para un array global."""
        name = node.var_name
        typ  = node.var_type
        size = node.size
        self.globals.add(name)
        self.emit(f"# Array global: {typ} {name}[{size}]")
        self.emit("  .align 2")
        self.emit(f"  .globl {name}")
        self.emit(f"  {name}: .space {size * 4}   # Reservar {size * 4} bytes para array de {size} elementos")

    def visit_MultiDeclaration(self, m: MultiDeclaration):
        """Maneja declaraciones múltiples de variables"""
        self.emit(f"  # Declaración múltiple: {m.var_type} {', '.join(m.var_names)}")
        
        # Si estamos en una función, las variables ya fueron registradas en pre_process_declarations
        # Solo necesitamos inicializarlas a 0
        if self.current_function != "":
            for var_name in m.var_names:
                if var_name in self.symtab:
                    if isinstance(self.symtab[var_name], int):
                        # Formato antiguo
                        offset = self.symtab[var_name]
                        self.emit(f"  sw zero, {offset}(s0)  # Inicializar '{var_name}' a 0")
                    elif isinstance(self.symtab[var_name], dict) and 'offset' in self.symtab[var_name]:
                        # Formato nuevo
                        offset = self.symtab[var_name]['offset']
                        self.emit(f"  sw zero, {offset}(s0)  # Inicializar '{var_name}' a 0")
        else:
            # Variables globales
            for var_name in m.var_names:
                self.globals.add(var_name)
                self.emit(f"{var_name}: .word 0")
                self.symtab[var_name] = {'type': 'global', 'label': var_name}

    def visit_For(self, node: For):
        L_cond = self.new_label()
        L_body = self.new_label()
        L_end = self.new_label()
        L_update = self.new_label()

        self.emit(f"# ----- Inicio de bucle for -----")
        
        # 1. Inicialización
        if node.init:
            self.emit(f"# Inicialización del bucle for")
            self.visit(node.init)
        
        self.emit(f"  j {L_cond}                      # Saltar a evaluación de condición")

        # 2. Cuerpo del bucle
        self.emit(f"{L_body}:                          # Inicio del cuerpo del bucle for")
        self.emit(f"# Cuerpo del bucle for")
        self.visit(node.body)
        
        # 3. Actualización
        self.emit(f"{L_update}:                        # Actualización del bucle for")
        if node.update:
            self.emit(f"# Actualización del bucle for")
            # Manejar diferentes tipos de update
            if isinstance(node.update, str):
                # Si es un string como "i", crear una asignación i = i + 1
                from frontend.ast_nodes import Assignment, Variable, BinaryOp, Number
                update_expr = BinaryOp('+', Variable(node.update), Number(1))
                update_stmt = Assignment(node.update, update_expr)
                self.visit(update_stmt)
            else:
                # Si es una expresión o statement, visitarlo directamente
                self.visit(node.update)
        
        # 4. Comprobación de condición
        self.emit(f"{L_cond}:                          # Evaluación de condición del bucle for")
        if node.condition:
            self.emit(f"# Evaluar condición del bucle for")
            r_cond = self.visit(node.condition)
            self.emit(f"  bne {r_cond}, zero, {L_body}   # Si condición es verdadera, ejecutar cuerpo")
        else:
            self.emit(f"# Bucle for sin condición (infinito)")
            self.emit(f"  j {L_body}                    # Bucle infinito (no hay condición)")

        # 5. Fin del bucle
        self.emit(f"{L_end}:                          # Fin del bucle for")
        self.emit(f"# ----- Fin de bucle for -----")

