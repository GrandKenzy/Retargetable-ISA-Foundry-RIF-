# Que es RIF

RIF es un generador retargetable para definir ensambladores, empaquetadores y linkers mediante paquetes y plugins.

El core no debe contener reglas especificas de una arquitectura. El core lee estructuras, ejecuta instrucciones comunes, resuelve placeholders, arma secciones y delega semantica concreta a plugins.

Un paquete RIF describe:

- mundo y configuracion
- tipos y tablas
- reglas de instrucciones
- memoria, headers y secciones
- plugins disponibles

La meta es que una arquitectura nueva pueda agregarse con paquetes y plugins sin modificar el motor interno.
