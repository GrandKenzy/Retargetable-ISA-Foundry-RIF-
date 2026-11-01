# Instrucciones del proyecto

## Contexto del asistente

Antes de trabajar en RIF, lee primero el contenido relevante de `.ia/`,
comenzando por `.ia/map/README.md`. El mapa sirve para orientarse y localizar
componentes; el código y las pruebas siguen siendo la fuente de verdad.
Evita releer archivos que no hayan cambiado salvo que necesites verificar un
detalle.

## Criterios de trabajo

- Evalúa el alcance antes de editar. Si el cambio cruza sintaxis, semántica,
  MIR, backend o artefactos, comunica un plan breve y verifica cada frontera.
- Comunica antes de proponer una alternativa cualquier restricción del lexer,
  parser, combinadores o API que pueda invalidarla. Incluye la evidencia
  concreta (por ejemplo, cómo se tokeniza una entrada) y distingue entre una
  solución válida para Python y una compatible con AOT/C.
- Sigue el recorrido real de RIF: gramática en `Frontend/syntax/`, despacho
  semántico en `Frontend/processor/`, estado compilado en `Frontend/globals.py`
  y `MIR/`, y emisión o ejecución en los módulos de memoria, runtime y
  `Backend/` cuando aplique.
- La sintaxis genérica `@block nombre:` ... `@end` es la forma canónica para
  bloques de datos. Las cabeceras y directivas legacy retiradas no deben
  volver como alias de compatibilidad.
- Cada línea de un bloque genérico contiene un nombre y como máximo dos valores.
  Los bloques conocidos (`config` y `linker`) deben materializar su semántica
  desde `BlockData`; los bloques desconocidos deben conservarse para
  consumidores especializados.
- Registra decisiones arquitectónicas relevantes en `.ia/map/README.md` y los
  cambios de producto importantes en `changelog/`.
- Añade comentarios solo cuando documenten un invariante, una limitación o un
  riesgo concreto. Usa `# PENDIENTE:`, `# CUIDADO:` o `# NOTA:` cuando ayude a
  localizar información funcional.

## Pruebas y ejecución

- Ejecuta la aplicación con `vnma run` y las pruebas con `vnma test`.
- Durante la iteración, ejecuta primero las pruebas relacionadas con el cambio
  y amplía la verificación cuando se modifique el parser, el estado compilado,
  los paquetes o la salida binaria.
- Las pruebas rápidas viven en `tests/`. Si aparece una prueba costosa de
  integración, generación de ejecutables, ensamblado o bare metal, colócala en
  `tests_aggressive/` y ejecútala explícitamente.
- Informa siempre qué pruebas se ejecutaron y qué comprobaciones relevantes
  quedaron pendientes.

## Ramas, checkpoints y workspace

- Para cambios importantes usa una rama `codex/<tarea>` cuando sea factible y
  crea checkpoints locales con alcance claro.
- Conserva cambios ajenos del workspace. No modifiques `_handlecheck/`,
  `.vscode/` ni salidas locales salvo que la tarea lo requiera.
- No uses operaciones destructivas como `git reset --hard` o `git checkout --`
  para resolver conflictos sin autorización explícita.
- Antes de entregar, revisa `git diff`, el estado de la rama y los artefactos
  generados. No hagas `push` ni fusiones remotas salvo petición del usuario.
