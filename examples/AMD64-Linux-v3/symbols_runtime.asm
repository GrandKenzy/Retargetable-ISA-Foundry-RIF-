::RIF_INSERT BYTES "7f454c46020101000000000000000000" SECTION text
::RIF_INSERT BYTES "02003e00010000000000000000000000" SECTION text
::RIF_INSERT BYTES "40000000000000000000000000000000" SECTION text
::RIF_INSERT BYTES "00000000400038000100000000000000" SECTION text
::RIF_INSERT BYTES "01000000050000000000000000000000" SECTION text
::RIF_INSERT BYTES "00004000000000000000400000000000" SECTION text
::RIF_INSERT BYTES "00000000000000000000000000000000" SECTION text
::RIF_INSERT BYTES "0010000000000000" SECTION text
::RIF_PATCH 24, 8, #:calc(4194304 + #:qlsize(0, "_start"))
::RIF_PATCH 96, 8, #:qssize(0, "text")
::RIF_PATCH 104, 8, #:calc(#:qvssize(0, "text") - 4194304)
_start
jmp_label begin
mark message
db 72
db 105
db 10
mark begin
mov rax, 1
mov rdi, 1
learip64 rsi, message
mov rdx, 3
syscall
mov rax, 0
mov rbx, 0
cmprr rax, rbx
jcc_label ne, bad
call_label answer
jmp_label finish
mark bad
mov rdi, 99
jmp_label exit_point
mark answer
mov rdi, 42
ret
mark finish
jmp8_label exit_point
mark exit_point
mov rax, 60
syscall
