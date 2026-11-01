# Lanzamiento de pruebas

La suite rápida se conserva detrás de este directorio para que el comando
convencional siga funcionando:

```powershell
vnma test
```

Las suites completas se ejecutan explícitamente:

```powershell
vnma test test/suite_essencial
vnma test test/suite_aggressive
vnma test test/dedicated_suite
```
