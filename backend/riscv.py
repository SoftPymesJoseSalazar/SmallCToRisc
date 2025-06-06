from frontend.ast_nodes import *
from lark import Tree, Token

class RiscVGenerator:
    def __init__(self, clean_mode=False):
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
        self.global_arrays = {}  # Para registrar arrays globales
        
        # NUEVO: Modo limpio sin comentarios
        self.clean_mode = clean_mode

    def new_reg(self):
        r = self.regs[self.reg_idx]
        self.reg_idx = (self.reg_idx + 1) % len(self.regs)
        return r

    def new_label(self):
        self.label_count += 1
        return f"L{self.label_count}"

    def emit(self, code):
        # Si estamos en clean_mode, filtrar comentarios
        if self.clean_mode:
            # Si la línea es solo un comentario, no agregarla
            stripped = code.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                return
            
            # Si hay comentario inline, removerlo
            if '#' in code:
                # Buscar el primer # que no esté dentro de comillas
                in_quotes = False
                comment_pos = -1
                for i, char in enumerate(code):
                    if char == '"' and (i == 0 or code[i-1] != '\\'):
                        in_quotes = not in_quotes
                    elif char == '#' and not in_quotes:
                        comment_pos = i
                        break
                
                if comment_pos != -1:
                    # Remover comentario pero mantener espacios para alineación
                    code = code[:comment_pos].rstrip()
                    
                    # Si después de remover comentario queda solo espacios, no agregar
                    if not code.strip():
                        return
        
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
                isinstance(node, StringArrayDeclaration) or
                isinstance(node, MultiDeclaration) or
                (isinstance(node, dict) and node.get('type') in ('declaration', 'array_declaration', 'string_array_declaration', 'multideclaration'))):
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
        
        # Si es un diccionario, procesarlo
        if isinstance(node, dict):
            return self.visit_dict(node)
        
        # Si es una lista, procesar cada elemento
        if isinstance(node, list):
            results = []
            for item in node:
                result = self.visit(item)
                if result is not None:
                    results.append(result)
            return results[-1] if results else None
        
        # Si llegamos aquí, no tenemos un manejador específico
        if hasattr(node, 'value'):
            return node.value
        return None

    def visit_dict(self, node):
        """Visita un nodo en formato diccionario"""
        if not isinstance(node, dict) or 'type' not in node:
            return None
            
        node_type = node['type']
        
        # Casos especiales
        if node_type == 'stmt':
            # Procesar statements
            if 'children' in node and node['children']:
                child = node['children'][0]
                # Si el hijo es un if con múltiples children, procesarlo especialmente
                if isinstance(child, dict) and child.get('type') == 'if' and len(child.get('children', [])) > 2:
                    return self.visit_complex_if(child)
                return self.visit(child)
        elif node_type == 'if':
            # Convertir if dict a objeto If
            children = node.get('children', [])
            if len(children) >= 2:
                condition = children[0]
                true_body = children[1]
                false_body = children[2] if len(children) > 2 else None
                from frontend.ast_nodes import If as IfNode
                return self.visit_If(IfNode(condition, true_body, false_body))
        elif node_type == 'block':
            # Procesar bloque
            if 'statements' in node:
                for stmt in node['statements']:
                    self.visit(stmt)
            return None
        elif node_type == 'declaration':
            # Convertir declaration dict a objeto Declaration
            from frontend.ast_nodes import Declaration
            obj = Declaration(
                node.get('var_name', ''), 
                node.get('var_type', ''), 
                node.get('value', None)
            )
            return self.visit_Declaration(obj)
        elif node_type == 'assignment':
            # Convertir assignment dict a objeto Assignment
            from frontend.ast_nodes import Assignment
            obj = Assignment(
                node.get('var_name', ''), 
                node.get('value', None)
            )
            return self.visit_Assignment(obj)
        elif node_type == 'return':
            # Convertir return dict a objeto Return
            expr = None
            if 'children' in node and node['children']:
                for child in node['children']:
                    if not isinstance(child, str) and child != ';':
                        expr = child
                        break
            elif 'expression' in node:
                expr = node['expression']
            from frontend.ast_nodes import Return
            return self.visit_Return(Return(expr))
        elif node_type == 'binary_op':
            # Convertir binary_op dict a objeto BinaryOp
            from frontend.ast_nodes import BinaryOp
            obj = BinaryOp(
                node.get('op', ''),
                node.get('left', None),
                node.get('right', None)
            )
            return self.visit_BinaryOp(obj)
        elif node_type == 'variable':
            # Convertir variable dict a objeto Variable
            from frontend.ast_nodes import Variable
            obj = Variable(node.get('name', ''))
            return self.visit_Variable(obj)
        elif node_type == 'number':
            # Convertir number dict a objeto Number
            from frontend.ast_nodes import Number
            obj = Number(node.get('value', 0))
            return self.visit_Number(obj)
        elif node_type == 'function_call':
            # Convertir function_call dict a objeto FuncCall
            from frontend.ast_nodes import FuncCall
            obj = FuncCall(
                node.get('name', ''),
                node.get('args', [])
            )
            return self.visit_FuncCall(obj)
        elif node_type == 'while':
            # Convertir while dict a objeto While
            from frontend.ast_nodes import While as WhileNode
            children = node.get('children', [])
            if len(children) >= 2:
                condition = children[0]
                body = children[1]
                return self.visit_While(WhileNode(condition, body))
            else:
                self.emit(f"  # ERROR: while malformado - necesita condición y cuerpo")
                return None
        
        # Si no hay caso específico, buscar en children
        if 'children' in node and node['children']:
            return self.visit(node['children'][0])
        
        return None

    def visit_complex_if(self, node):
        """Maneja estructuras if-else-if complejas"""
        children = node.get('children', [])
        if len(children) < 2:
            return None
        
        # Labels para el control de flujo
        labels_end = []
        label_final = self.new_label()
        
        self.emit(f"  # ----- Estructura if-else-if compleja -----")
        
        i = 0
        while i < len(children):
            if i == 0:
                # Primera condición (if inicial)
                self.emit(f"  # Evaluación de condición if principal")
                r_cond = self.visit(children[i])
                label_next = self.new_label()
                labels_end.append(label_next)
                self.emit(f"  beq {r_cond}, zero, {label_next}  # Si condición es falsa, saltar a siguiente")
                
                # Cuerpo del if
                if i + 1 < len(children):
                    self.emit(f"  # Cuerpo del if principal")
                    self.visit(children[i + 1])
                    self.emit(f"  j {label_final}  # Saltar al final")
                i += 2
                
            elif i + 1 < len(children) and i + 2 < len(children):
                # else if (condición + cuerpo)
                self.emit(f"{labels_end[-1]}:")  # Etiqueta del salto anterior
                labels_end.pop()
                
                self.emit(f"  # Evaluación de condición else-if")
                r_cond = self.visit(children[i])
                label_next = self.new_label()
                labels_end.append(label_next)
                self.emit(f"  beq {r_cond}, zero, {label_next}  # Si condición es falsa, saltar a siguiente")
                
                # Cuerpo del else if
                self.emit(f"  # Cuerpo del else-if")
                self.visit(children[i + 1])
                self.emit(f"  j {label_final}  # Saltar al final")
                i += 2
                
            else:
                # else final (solo cuerpo, sin condición)
                if labels_end:
                    self.emit(f"{labels_end[-1]}:")  # Etiqueta del último salto
                    labels_end.pop()
                
                self.emit(f"  # Cuerpo del else final")
                self.visit(children[i])
                break
        
        # Limpiar etiquetas restantes
        for label in labels_end:
            self.emit(f"{label}:")
        
        self.emit(f"{label_final}:")
        self.emit(f"  # ----- Fin estructura if-else-if compleja -----")

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
            elif hasattr(p, '__class__') and p.__class__.__name__ == 'ArrayParameter':
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
            if isinstance(p, Parameter):
                param_name = p.name
            elif hasattr(p, '__class__') and p.__class__.__name__ == 'ArrayParameter':
                param_name = p.name
            else:
                param_name = f"param{i}"
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
        elif isinstance(node, ArrayDeclaration):
            # Array global - no necesita espacio en stack local
            pass
        elif isinstance(node, StringArrayDeclaration):
            # String array global - no necesita espacio en stack local
            pass
        elif isinstance(node, MultiDeclaration):
            for var_name in node.var_names:
                self.sp_offset -= 4
                self.symtab[var_name] = self.sp_offset
                print(f"REGISTRO: Variable multi {var_name} en offset {self.sp_offset}")
        # Compatibilidad temporal con declaraciones de tipo dict
        elif isinstance(node, dict) and node.get('type') == 'declaration':
            var_name = node.get('var_name', 'unknown')
            self.sp_offset -= 4
            self.symtab[var_name] = self.sp_offset
            print(f"REGISTRO: Variable dict {var_name} en offset {self.sp_offset}")
        # Procesar recursivamente en bloques y otras estructuras
        elif hasattr(node, 'body'):
            self.pre_process_declarations(node.body)
        elif hasattr(node, 'true_body'):
            self.pre_process_declarations(node.true_body)
            if hasattr(node, 'false_body') and node.false_body:
                self.pre_process_declarations(node.false_body)
        elif isinstance(node, For):
            if node.init:
                self.pre_process_declarations(node.init)
            self.pre_process_declarations(node.body)
        elif isinstance(node, While):
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
            '+': 'suma', '-': 'resta', '*': 'multiplicación', '/': 'división', '%': 'módulo',
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
        elif op == '%':
            self.emit(f"  rem {result}, {lreg}, {rreg}      # {result} = {lreg} % {rreg}")
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

    def visit_Character(self, c):
        """Genera código para cargar un carácter (convertido a su valor ASCII)."""
        r = self.new_reg()
        # Extraer el carácter sin las comillas
        char_value = c.value
        if len(char_value) >= 3:  # 'x' tiene 3 caracteres
            actual_char = char_value[1]  # Tomar el carácter del medio
        else:
            actual_char = char_value
        
        # Convertir a valor ASCII
        ascii_value = ord(actual_char)
        self.emit(f"  li {r}, {ascii_value}                # Cargar carácter '{actual_char}' (ASCII {ascii_value})")
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
            # Verificar si es un array de char
            if array_name in self.global_arrays and self.global_arrays[array_name]['type'] == 'char':
                # Array de char - usar acceso por bytes
                self.emit(f"  la {result_reg}, {array_name}    # Cargar dirección base del array global de char '{array_name}'")
                self.emit(f"  add {result_reg}, {result_reg}, {index_reg} # Calcular dirección del carácter (índice directo)")
                
                # Cargar el byte y convertir a word
                value_reg = self.new_reg()
                self.emit(f"  lbu {value_reg}, 0({result_reg})  # Cargar byte de {array_name}[<índice>] (sin signo)")
                
                return value_reg
            else:
                # Array de int - usar acceso por words
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
        """Genera código para declaración de array global."""
        # Solo manejar arrays globales por ahora
        self.global_arrays[node.var_name] = {
            'type': node.var_type,
            'size': node.size
        }
        
        # Reservar espacio en la sección .data
        self.emit(f"{node.var_name}: .space {node.size * 4}  # Array {node.var_type}[{node.size}]")

    def visit_StringArrayDeclaration(self, node):
        """Genera código para declaración de array de char con string."""
        # Registrar en globals y arrays globales
        self.globals.add(node.var_name)
        self.global_arrays[node.var_name] = {
            'type': 'char',
            'size': node.size
        }
        
        # Generar string literal en sección .data
        # Convertir caracteres especiales
        escaped_string = node.string_value.replace('\\n', '\\n').replace('\\t', '\\t')
        self.emit(f"{node.var_name}: .asciz \"{escaped_string}\"  # String array: char {node.var_name}[]")

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

    def visit_Stmt(self, node):
        """Genera código para una sentencia stmt."""
        # Si el stmt contiene children, procesar el primer hijo
        if hasattr(node, 'children') and node.children:
            child = node.children[0]
            
            # Si el hijo es un Tree de Lark (especialmente if o while), procesarlo
            if hasattr(child, 'data') and child.data == 'if':
                # Convertir Tree a una estructura procesable
                from lark import Tree
                if isinstance(child, Tree):
                    # Extraer children del Tree
                    tree_children = [c for c in child.children if not hasattr(c, 'type') or c.type not in ['LPAREN', 'RPAREN']]
                    
                    # Si tiene más de 3 children, es un if-else-if complejo
                    if len(tree_children) > 3:
                        # Crear un dict temporal para usar visit_complex_if
                        temp_dict = {
                            'type': 'if',
                            'children': tree_children
                        }
                        return self.visit_complex_if(temp_dict)
                    else:
                        # If normal (con o sin else), crear objeto If directamente
                        condition = tree_children[0] if len(tree_children) > 0 else None
                        true_body = tree_children[1] if len(tree_children) > 1 else None
                        false_body = tree_children[2] if len(tree_children) > 2 else None
                        from frontend.ast_nodes import If as IfNode
                        return self.visit_If(IfNode(condition, true_body, false_body))
            
            # Si el hijo es un Tree de while, procesarlo
            elif hasattr(child, 'data') and child.data == 'while':
                from lark import Tree
                if isinstance(child, Tree):
                    # Extraer children del Tree
                    tree_children = [c for c in child.children if not hasattr(c, 'type') or c.type not in ['LPAREN', 'RPAREN']]
                    
                    if len(tree_children) >= 2:
                        condition = tree_children[0]
                        body = tree_children[1]
                        from frontend.ast_nodes import While as WhileNode
                        return self.visit_While(WhileNode(condition, body))
                    else:
                        self.emit(f"  # ERROR: while Tree malformado")
                        return None
            
            # Si el hijo es un Tree de return, procesarlo
            elif hasattr(child, 'data') and child.data == 'return':
                from lark import Tree
                if isinstance(child, Tree):
                    # Extraer children del Tree
                    tree_children = [c for c in child.children if not hasattr(c, 'type') or c.type not in ['LPAREN', 'RPAREN', 'SEMICOLON']]
                    
                    # El return puede tener una expresión o estar vacío
                    expr = tree_children[0] if len(tree_children) > 0 else None
                    from frontend.ast_nodes import Return as ReturnNode
                    return self.visit_Return(ReturnNode(expr))
            
            # Si el hijo es un If con múltiples children en formato dict, procesarlo especialmente
            elif isinstance(child, dict) and child.get('type') == 'if':
                children = child.get('children', [])
                if len(children) > 2:
                    # Es un if-else-if complejo
                    return self.visit_complex_if(child)
                else:
                    # Es un if simple, procesarlo normalmente
                    return self.visit(child)
            
            # Si el hijo es un While en formato dict, procesarlo especialmente
            elif isinstance(child, dict) and child.get('type') == 'while':
                # Crear un objeto While temporal para procesarlo
                from frontend.ast_nodes import While as WhileNode
                children = child.get('children', [])
                if len(children) >= 2:
                    condition = children[0]
                    body = children[1]
                    return self.visit_While(WhileNode(condition, body))
                else:
                    # Error: while sin condición o cuerpo
                    self.emit(f"  # ERROR: while malformado")
                    return None
            
            # Para otros casos, procesar normalmente
            return self.visit(child)
        
        return None

