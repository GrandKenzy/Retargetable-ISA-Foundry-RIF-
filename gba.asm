::RIF_PCPI SET "build/GBA_ROM_arm7tdmi_little.pcic"
::RIF_PCPI FILL 0 "2E0000EA"
::RIF_PCPI FILL 1 "5249462042414C4C2047424152494631"
::RIF_PCPI FILL 2 "30319600000000000000000000D80000"

; RIF / GBA — ejemplo de la sintaxis cómoda propuesta para ARM7TDMI.
;
; La estructura del target vive en un .rif; este archivo muestra el código
; que escribiría una persona sin pensar en opcodes ni en BX manuales.
;
; Reglas de lectura:
;   - modo solo selecciona el conjunto de instrucciones que se codificará.
;   - desde_thumb genera el interworking ARM <-> Thumb y conserva el retorno.
;   - los nombres en español son reglas de alto nivel del target, no macros C.
;   - los datos binarios viven en un .store separado.

; La imagen PCP-I ya contiene el target GBA, el layout y los campos fijos.
; Las cuatro líneas iniciales son la interfaz real del preprocesador y solo
; rellenan los pits declarados por la imagen compilada.

; cargar dependencias. No debería insertar bytes.
::RIF_STORE AS GBA "build/gba.storage.bin"
GBA.ORDER 1
GBA.ENDIANNESS 1

modo arm

inicio:
    ; Inicializa Mode 3 y apunta a VRAM 0x06000000.
    mover    r0, GBA.MODE_3
    mover    r1, GBA.DIR_VRAM
    guarda16 [r0], GBA.DISPCNT


    ; ARM llama a Thumb. RIF resuelve el BX y la alineación automáticamente.
    desde_thumb actualizar_pelota

    ; El puente vuelve a ARM al terminar actualizar_pelota.
    sumar      r4, r4, #1
    comparar   r4, #60
    salta_si   igual, un_frame
    salto      inicio
    ; NOTE: Revisa hasta aquí


un_frame:
    espera_vblank
    salto inicio

    modo thumb

actualizar_pelota:
    ; Thumb usa las mismas reglas semánticas con un encoding distinto.
    carga   r0, [r1, #0]
    suma    r0, r0, #1
    guarda  [r1, #0], r0
    compara r0, #240
    salta_si mayor_igual, rebota
    retorno

rebota:
    niega   r0, r0
    guarda  [r1, #0], r0
    retorno

    ; Operaciones de memoria legibles, con ancho declarado por la regla:
    ;
    ; carga8    r0, [r1, #1]
    ; carga16   r0, [r1, #2]
    ; carga32   r0, [r1, #4]
    ; guarda8   [r1, #1], r0
    ; guarda16  [r1, #2], r0
    ; guarda32  [r1, #4], r0

    ; El contenedor asociado podría ser gba.store:
    ;
    ; uint32 MODE_3 = 0x04000000
    ; uint32 DIR_VRAM = 0x06000000
    ; uint16 DISPCNT = 0x0403
    ; uint16 ancho = 240
    ; uint16 alto = 160
    ; str titulo = "RIF GBA"
    ; @FILE "assets/ball_palette.bin" AS paleta

