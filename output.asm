.globl fib
.text
fib:
addi sp, sp, -32
sw ra, 28(sp)
sw s0, 24(sp)
addi s0, sp, 32
sw a0, -4(s0)  # param n
li t0, 0
sw t0, -8(s0)  # a = 0
li t0, 1
sw t0, -12(s0)  # b = 1
sw zero, -16(s0)  # init temp
lw x5, -4(s0)  # cargar variable n
beqz x5, then_block  # if (n == 0)
j L1
then_block:
lw x6, -8(s0)  # cargar variable a
mv a0, x6  # return value
j fib_end
L1:
li t0, 2
sw t0, -20(s0)  # i = 2
L2:
lw x7, -20(s0)  # cargar variable i
lw x8, -4(s0)  # cargar variable n
bgt x7, x8, L3  # while i <= n
lw x9, -8(s0)  # cargar variable a
lw x5, -12(s0)  # cargar variable b
add x6, x9, x5  # temp = a + b
sw x6, -16(s0)
lw x7, -12(s0)  # cargar variable b
sw x7, -8(s0)  # a = b
lw x8, -16(s0)  # cargar variable temp
sw x8, -12(s0)  # b = temp
lw x9, -20(s0)  # cargar variable i
addi x9, x9, 1  # i = i + 1
sw x9, -20(s0)
j L2  # volver al inicio del bucle
L3:
lw x5, -12(s0)  # cargar variable b
mv a0, x5  # return value
j fib_end
fib_end:
lw s0, 24(sp)
lw ra, 28(sp)
addi sp, sp, 32
ret
.globl main
.text
main:
addi sp, sp, -32
sw ra, 28(sp)
sw s0, 24(sp)
addi s0, sp, 32
li a0, 10
jal fib
sw a0, -4(s0)  # guardar result = fib(10)
lw x6, -4(s0)  # cargar variable result
mv a0, x6  # return value
j main_end
main_end:
lw s0, 24(sp)
lw ra, 28(sp)
addi sp, sp, 32
ret