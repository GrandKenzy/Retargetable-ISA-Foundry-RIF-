# Reference source for the fixed boot-stage bytes emitted by boot_stage_mouse in
# rules.rif. It is intentionally 16-bit: the cursor uses the Bochs VBE banked
# window and a polled PS/2 mouse, so no kernel or protected mode is required.
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

    # Keep the cursor state in low conventional RAM, outside the boot image.
    # x=313 and y=229 center a 14x22 cursor in the 640x480 mode.
    mov word ptr [0x0600], 313
    mov word ptr [0x0602], 229
    mov dword ptr [0x0604], 0x0008f6e4

    # Enable the auxiliary PS/2 device and mouse data reporting.
    mov dx, 0x0064
flush_controller:
    in al, dx
    test al, 1
    jz flush_done
    in al, 0x60
    jmp flush_controller
flush_done:
    call wait_input
    mov al, 0xa8
    out dx, al
    call wait_input
    mov al, 0xd4
    out dx, al
    call wait_input
    mov al, 0xf4
    out 0x60, al
wait_ack:
    in al, dx
    test al, 1
    jz wait_ack
    in al, 0x60
    cmp al, 0xfa
    jne wait_ack

    mov bl, 1
    call draw_cursor

mouse_packet:
    mov dx, 0x0064
    call read_mouse_byte
    test al, 8
    jz mouse_packet
    mov byte ptr [0x0608], al
    call read_mouse_byte
    mov byte ptr [0x0609], al
    call read_mouse_byte
    mov byte ptr [0x060a], al
    test byte ptr [0x0608], 0xc0
    jnz mouse_packet

    xor bl, bl
    call draw_cursor

    # Apply signed packet deltas and clamp to the visible cursor rectangle.
    mov al, byte ptr [0x0609]
    cbw
    add word ptr [0x0600], ax
    cmp word ptr [0x0600], 0
    jge x_upper
    mov word ptr [0x0600], 0
x_upper:
    cmp word ptr [0x0600], 626
    jle y_delta
    mov word ptr [0x0600], 626
y_delta:
    mov al, byte ptr [0x060a]
    cbw
    neg ax
    add word ptr [0x0602], ax
    cmp word ptr [0x0602], 0
    jge y_upper
    mov word ptr [0x0602], 0
y_upper:
    cmp word ptr [0x0602], 458
    jle update_offset
    mov word ptr [0x0602], 458

update_offset:
    movzx eax, word ptr [0x0602]
    imul eax, eax, 2560
    movzx ebx, word ptr [0x0600]
    shl ebx, 2
    add eax, ebx
    mov dword ptr [0x0604], eax
    mov bl, 1
    call draw_cursor
    jmp mouse_packet

wait_input:
    in al, dx
    test al, 2
    jnz wait_input
    ret

read_mouse_byte:
read_mouse_wait:
    in al, dx
    test al, 1
    jz read_mouse_wait
    test al, 0x20
    jz read_mouse_wait
    in al, 0x60
    ret

# Draw or clear the 14x22 cursor. BL=0 clears to black; BL=1 copies the
# BGRX payload at 0000:7e00. Each row is split if it crosses a 64 KiB bank.
draw_cursor:
    mov byte ptr [0x060b], bl
    mov ax, 0xa000
    mov es, ax
    mov eax, dword ptr [0x0604]
    mov dword ptr [0x060c], eax
    mov word ptr [0x0610], 0
    mov word ptr [0x0612], 0x7e00
draw_row:
    mov eax, dword ptr [0x060c]
    mov si, ax
    shr eax, 16
    mov word ptr [0x0614], ax
    call set_bank
    mov di, si
    mov si, word ptr [0x0612]
    mov cx, 14
    mov ax, di
    add ax, 56
    jnc draw_full_row
    mov ax, di
    neg ax
    shr ax, 2
    mov word ptr [0x0616], ax
    mov cx, ax
    call emit_cursor_chunk
    mov ax, word ptr [0x0616]
    shl ax, 2
    add si, ax
    inc word ptr [0x0614]
    call set_bank
    xor di, di
    mov cx, 14
    sub cx, word ptr [0x0616]
    call emit_cursor_chunk
    jmp draw_next_row
draw_full_row:
    call emit_cursor_chunk
draw_next_row:
    mov eax, dword ptr [0x060c]
    add eax, 2560
    mov dword ptr [0x060c], eax
    add word ptr [0x0612], 56
    inc word ptr [0x0610]
    cmp word ptr [0x0610], 22
    jb draw_row
    ret

set_bank:
    mov ax, 0x4f05
    xor bx, bx
    mov dx, word ptr [0x0614]
    int 0x10
    ret

emit_cursor_chunk:
    cmp byte ptr [0x060b], 0
    je emit_black
    .byte 0x66, 0xf3, 0xa5    # rep movsd
    ret
emit_black:
    xor eax, eax
    .byte 0x66, 0xf3, 0xab    # rep stosd
    ret

fail:
    cli
    hlt
    jmp fail
.org 510
.byte 0x55, 0xaa
