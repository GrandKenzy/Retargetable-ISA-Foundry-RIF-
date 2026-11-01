# Lanzamiento de pruebas

La suite rápida se conserva detrás de este directorio para que el comando
convencional siga funcionando:

```powershell
vnma test
```

Las suites completas se ejecutan explícitamente:

```powershell
vnma test tests/suite_essencial
vnma test tests/suite_aggressive
vnma test tests/dedicated_suite
```
