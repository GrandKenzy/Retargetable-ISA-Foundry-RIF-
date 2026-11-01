# Reference source for the fixed boot-stage bytes emitted by boot_stage in
# rules.rif. It is intentionally 16-bit: the first checkpoint uses the
# Bochs VBE banked window and does not require protected mode or paging.
#
# This file is a verification aid, not a build-time dependency. The target
# emits the resulting bytes through RIF so the .pack + .mir path remains the
# canonical build path.

.intel_syntax noprefix
.code16
.section .text
.global _start

_start:
    cli
    xor ax, ax
    mov ds, ax
    mov ss, ax
    mov sp, 0x7c00
    sti

    # Bochs/QEMU VBE mode 0x118: 640x480x32, banked window.
    mov ax, 0x4f02
    mov bx, 0x0118
    int 0x10
    cmp ax, 0x004f
    jne fail

    # First cursor row begins in bank 8 at window offset 0xf6e4.
    mov ax, 0x4f05
    xor bx, bx
    mov dx, 8
    int 0x10
    mov ax, 0xa000
    mov es, ax
    mov si, 0x7e00
    mov di, 0xf6e4
    mov cx, 14
    .byte 0x66, 0xf3, 0xa5    # rep movsd, 14 BGRX pixels

    # Remaining 21 rows are in bank 9. Each row advances by 2560 bytes.
    mov ax, 0x4f05
    xor bx, bx
    mov dx, 9
    int 0x10
    mov ax, 0xa000
    mov es, ax
    mov si, 0x7e38
    mov di, 0x00e4
    mov bp, 21
draw_row:
    mov cx, 14
    .byte 0x66, 0xf3, 0xa5
    add di, 0x09c8          # 2560 - (14 * 4)
    dec bp
    jnz draw_row

halt:
    cli
    hlt
    jmp halt

fail:
    cli
    hlt
    jmp fail

.org 510
.byte 0x55, 0xaa
