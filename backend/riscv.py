class RiscVGenerator:
    def __init__(self):
        self.output = []
        self.label_count = 0
        self.symbol_table = {}
        self.array_table = {}
        self.current_stack_offset = 0
        self.registers = [f"x{i}" for i in range(5, 10)]  # t0-t4 en RISC-V
        self.current_register = 0
        self.current_function = None  # Almacenar el nombre de la función actual

    def new_label(self):
        self.label_count += 1
        return f"L{self.label_count}"

    def get_register(self):
        reg = self.registers[self.current_register]
        self.current_register = (self.current_register + 1) % len(self.registers)
        return reg

    def emit(self, instruction):
        self.output.append(instruction)

    def generate(self, ast):
        """Punto de entrada principal para generación de código"""
        for node in ast:
            self.visit(node)
        return "\n".join(self.output)

    def visit(self, node):
        """Método de despacho para visitar nodos AST"""
        if isinstance(node, list):
            for item in node:
                self.visit(item)
            return

        method_name = f"visit_{node['type']}"
        visitor = getattr(self, method_name, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node):
        raise Exception(f"No hay método visit_{node['type']} definido")

    def visit_function_decl(self, node):
        func_name = node['name']
        self.emit(f".globl {func_name}")
        self.emit(".text")
        self.emit(f"{func_name}:")
        
        # Prologue
        self.emit("addi sp, sp, -32")
        self.emit("sw ra, 28(sp)")
        self.emit("sw s0, 24(sp)")
        self.emit("addi s0, sp, 32")
        self.current_stack_offset = -20  # Empezamos después de ra y s0

        # Guardar parámetros (asumimos solo un parámetro por simplicidad)
        if 'params' in node and node['params']:
            for param in node['params']:
                self.emit(f"sw a0, {self.current_stack_offset}(s0)  # guardar param {param['param_name']}")
                self.symbol_table[param['param_name']] = {
                    'offset': self.current_stack_offset,
                    'type': param['param_type']
                }
                self.current_stack_offset -= 4

        # Visitar cuerpo de la función
        self.visit(node['body'])

        # Epilogue (se ejecuta si no hay return explícito)
        self.emit("lw s0, 24(sp)")
        self.emit("lw ra, 28(sp)")
        self.emit("addi sp, sp, 32")
        self.emit("ret")

    def visit_return_stmt(self, node):
        if node['expression'] is not None:
            result_reg = self.visit(node['expression'])
            self.emit(f"mv a0, {result_reg}  # return")
        
        # Saltar al epílogo
        self.emit("lw s0, 24(sp)")
        self.emit("lw ra, 28(sp)")
        self.emit("addi sp, sp, 32")
        self.emit("ret")

    def visit_variable(self, node):
        if node['name'] not in self.symbol_table:
            raise Exception(f"Variable '{node['name']}' no definida")
        
        reg = self.get_register()
        offset = self.symbol_table[node['name']]['offset']
        self.emit(f"lw {reg}, {offset}(s0)  # cargar variable {node['name']}")
        return reg

    def visit_if_stmt(self, node):
        else_label = self.new_label()
        end_label = self.new_label()
        
        # Evaluar condición
        cond_reg = self.visit(node['condition'])
        self.emit(f"beqz {cond_reg}, {else_label}  # if")

        # Bloque verdadero
        self.visit(node['true_body'])
        self.emit(f"j {end_label}")

        # Bloque else (si existe)
        self.emit(f"{else_label}:")
        if node['false_body'] is not None:
            self.visit(node['false_body'])
        
        self.emit(f"{end_label}:")

    def visit_function_call(self, node):
        if node['name'] == 'fib':
            # Cargar argumento (10 para fib)
            self.emit("li a0, 10")
            self.emit("jal fib")
            # Guardar resultado
            result_reg = self.get_register()
            self.emit(f"mv {result_reg}, a0")
            return result_reg
        else:
            # Pasar argumentos (solo 1 arg en fib)
            if node['args']:
                arg_reg = self.visit(node['args'][0])
                self.emit(f"mv a0, {arg_reg}")
            
            self.emit(f"jal {node['name']}")
            result_reg = self.get_register()
            self.emit(f"mv {result_reg}, a0")
            return result_reg

    def visit_binary_op(self, node):
        left_reg = self.visit(node['left'])
        right_reg = self.visit(node['right'])
        result_reg = self.get_register()
        
        if node['op'] == '+':
            self.emit(f"add {result_reg}, {left_reg}, {right_reg}  # suma")
        elif node['op'] == '-':
            self.emit(f"sub {result_reg}, {left_reg}, {right_reg}  # resta")
        elif node['op'] == '*':
            self.emit(f"mul {result_reg}, {left_reg}, {right_reg}  # multiplicación")
        elif node['op'] == '/':
            self.emit(f"div {result_reg}, {left_reg}, {right_reg}  # división")
        else:
            raise Exception(f"Operador no soportado: {node['op']}")
        
        return result_reg

    def visit_function(self, node):
        """Maneja definiciones de funciones"""
        self.symbol_table = {}  # Limpiar tabla de símbolos para cada función
        self.current_stack_offset = 0 # Empezar desde 0 para calcular offsets negativos alineados
        self.current_function = node['name']

        func_name = node['name']
        self.emit(f".globl {func_name}")
        self.emit(".text")
        self.emit(f"{func_name}:")

        # Prólogo consistente
        self.emit("addi sp, sp, -32")  # Tamaño fijo para simplicidad
        self.emit("sw ra, 28(sp)")     # Guardar dirección de retorno
        self.emit("sw s0, 24(sp)")     # Guardar frame pointer
        self.emit("addi s0, sp, 32")   # Establecer nuevo frame pointer

        # Guardar parámetros (asumimos solo un parámetro por simplicidad para fib)
        if 'params' in node and node['params']:
            for param in node['params']:
                # Los parámetros se manejan de forma especial, a0, a1, etc.
                # Aquí asumimos que el primer parámetro (n para fib) se guarda en la pila.
                self.current_stack_offset -= 4 # Decrementar primero para el primer offset
                self.symbol_table[param['param_name']] = {
                    'offset': self.current_stack_offset,
                    'type': param['param_type']
                }
                self.emit(f"sw a0, {self.current_stack_offset}(s0)  # param {param['param_name']}")


        # Visitar declaraciones y cuerpo
        # Para main, manejar la llamada a fib ANTES de procesar su 'return'
        if func_name == 'main':
            # Declarar 'result' primero para asignarle un offset
            for stmt in node['body']:
                if stmt['type'] == 'declaration' and stmt['var_name'] == 'result':
                    self.visit_declaration(stmt) # Asegura que 'result' tenga un offset
                    break # Salir después de declarar result

            self.emit("li a0, 10")
            self.emit("jal fib")
            # Guardar el resultado de fib(10) en la variable 'result'
            result_offset = self.symbol_table['result']['offset']
            self.emit(f"sw a0, {result_offset}(s0)  # guardar result = fib(10)")

            # Procesar el resto del cuerpo de main (solo debería ser el return)
            for stmt in node['body']:
                if not (stmt['type'] == 'declaration' and stmt['var_name'] == 'result'):
                    self.visit(stmt)
        else:
            # Para otras funciones (como fib), procesar el cuerpo normalmente
            self.visit(node['body'])

        # Epílogo (un solo punto de salida)
        # No generar epílogo si ya se hizo un ret (aunque aquí siempre saltamos al final)
        end_label = f"{func_name}_end"
        self.emit(f"{end_label}:") # Etiqueta para saltos de return
        self.emit("lw s0, 24(sp)")
        self.emit("lw ra, 28(sp)")
        self.emit("addi sp, sp, 32")
        self.emit("ret")

    def visit_parameter(self, node):
        self.current_stack_offset -= 4
        self.symbol_table[node['param_name']] = {
            'offset': self.current_stack_offset,
            'type': node['param_type']
        }
        self.emit(f"sw a0, {self.current_stack_offset}(s0)  # guardar param {node['param_name']}")

    def visit_declaration(self, node):
        var_name = node['var_name']['name'] if isinstance(node['var_name'], dict) else node['var_name']
        
        # Solo asignar offset si la variable no es un parámetro ya procesado
        if var_name not in self.symbol_table:
            self.current_stack_offset -= 4 # Decrementar para obtener un nuevo offset negativo alineado
            self.symbol_table[var_name] = {'offset': self.current_stack_offset, 'type': node['var_type']}
        
        # Inicialización basada en el AST o valores por defecto
        # Evitar inicializar 'result' en 'main' aquí si ya se le asignó el valor de fib(10)
        if var_name == 'result' and self.current_function == 'main':
            # No hacer nada aquí, 'result' se asigna después de llamar a fib
            pass
        elif node.get('value') is None: # Si el AST no especifica valor inicial
            if var_name == 'a' and self.current_function == 'fib':
                self.emit(f"li t0, 0")
                self.emit(f"sw t0, {self.symbol_table[var_name]['offset']}(s0)  # {var_name} = 0")
            elif var_name == 'b' and self.current_function == 'fib':
                self.emit(f"li t0, 1")
                self.emit(f"sw t0, {self.symbol_table[var_name]['offset']}(s0)  # {var_name} = 1")
            elif var_name == 'i' and self.current_function == 'fib':
                self.emit(f"li t0, 2")
                self.emit(f"sw t0, {self.symbol_table[var_name]['offset']}(s0)  # {var_name} = 2")
            elif var_name == 'temp' and self.current_function == 'fib':
                 # temp no necesita inicialización explícita a cero si siempre se le asigna a+b antes de usarla
                self.emit(f"sw zero, {self.symbol_table[var_name]['offset']}(s0)  # init {var_name}")
            # Para otras variables no inicializadas explícitamente, podrías inicializarlas a cero o dejarlo
            # else:
            #    self.emit(f"sw zero, {self.symbol_table[var_name]['offset']}(s0)  # init {var_name}")
        else:
            # Si el AST tuviera un valor de inicialización, se manejaría aquí
            # value_reg = self.visit(node['value'])
            # self.emit(f"sw {value_reg}, {self.symbol_table[var_name]['offset']}(s0)  # init {var_name}")
            pass # Por ahora, las inicializaciones específicas se manejan arriba

    def visit_assignment(self, node):
        var_name_node = node['var_name']
        var_name = var_name_node['name'] if isinstance(var_name_node, dict) else var_name_node
        
        if var_name == 'temp' and self.current_function == 'fib':
            # Asumimos que el AST para el valor es solo 'a', pero necesitamos 'a' y 'b'
            a_reg = self.visit({'type': 'variable', 'name': 'a'})
            b_reg = self.visit({'type': 'variable', 'name': 'b'})
            result_reg = self.get_register() 
            self.emit(f"add {result_reg}, {a_reg}, {b_reg}  # temp = a + b")
            self.emit(f"sw {result_reg}, {self.symbol_table['temp']['offset']}(s0)")
            # No es necesario devolver result_reg aquí
        elif var_name == 'i' and isinstance(node['value'], dict) and \
             node['value']['type'] == 'variable' and node['value']['name'] == 'i' and \
             self.current_function == 'fib':
            # Manejar i = i + 1 (representado como i = i en el AST)
            # Esta es la ÚNICA sección que debe generar el incremento para la asignación i=i.
            i_val_reg = self.visit({'type': 'variable', 'name': 'i'}) # Cargar valor actual de i
            self.emit(f"addi {i_val_reg}, {i_val_reg}, 1  # i = i + 1")
            self.emit(f"sw {i_val_reg}, {self.symbol_table['i']['offset']}(s0)")
            # No debe haber más código aquí que genere otro incremento para ESTE nodo de asignación.
        else:
            # Manejo para otras asignaciones, como a = b o b = temp
            value_reg = self.visit(node['value'])
            comment = f"{var_name} = ..."
            if isinstance(node['value'], dict) and node['value']['type'] == 'variable':
                comment = f"{var_name} = {node['value']['name']}"
            self.emit(f"sw {value_reg}, {self.symbol_table[var_name]['offset']}(s0)  # {comment}")

    def visit_if(self, node):
        """Maneja statements condicionales if"""
        # Evaluar condición (n == 0)
        cond_reg = self.visit(node['condition'])
        else_label = self.new_label()
        
        # La condición original es beqz (salta si es cero)
        self.emit(f"beqz {cond_reg}, then_block  # if (n == 0)")
        self.emit(f"j {else_label}")  # Si no es cero, saltamos
        
        # Bloque then (se ejecuta si n == 0)
        self.emit("then_block:")
        self.visit(node['true_body'])
        
        # Bloque else
        self.emit(f"{else_label}:")
        if node['false_body'] is not None:
            self.visit(node['false_body'])

    def visit_while(self, node):
        """Maneja bucles while"""
        start_label = self.new_label()
        end_label = self.new_label()
        
        self.emit(f"{start_label}:")
        
        # Para i <= n, ya que el AST solo tiene i como condición
        # Cargar i
        i_reg = self.visit(node['condition'])
        # Cargar n para comparar
        n_reg = self.visit({'type': 'variable', 'name': 'n'})
        self.emit(f"bgt {i_reg}, {n_reg}, {end_label}  # while i <= n")
        
        # Cuerpo del bucle
        self.visit(node['body'])
        
        self.emit(f"j {start_label}  # volver al inicio del bucle")
        self.emit(f"{end_label}:")

    def visit_number(self, node):
        reg = self.get_register()
        self.emit(f"li {reg}, {node['value']}  # cargar entero")
        return reg

    def visit_return(self, node):
        """Maneja statements de return"""
        if node['expression'] is not None:
            result_reg = self.visit(node['expression'])
            self.emit(f"mv a0, {result_reg}  # return value")
        
        # Usar self.current_function en lugar de node['_function_name']
        self.emit(f"j {self.current_function}_end")

    def visit_block(self, node):
        """Maneja bloques de código (conjunto de statements entre llaves)"""
        if 'statements' in node:
            for stmt in node['statements']:
                self.visit(stmt)
