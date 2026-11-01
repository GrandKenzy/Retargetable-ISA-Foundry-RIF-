; ELF64 Linux with RX .text, RW .data and a virtual-only allocation.
::RIF_SECTION data
mark counter
dq 0
mark message
db 72
db 105
db 10
mark scratch
virtual_scratch
::RIF_SECTION text
_start
mov rax, 42
storerip64 rax, counter
loadrip64 r10, counter
mov rax, 1
mov rdi, 1
learip64 rsi, message
mov rdx, 3
syscall
movrr rdi, r10
mov rax, 60
syscall
