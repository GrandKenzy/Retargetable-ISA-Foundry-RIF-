@echo off
setlocal

rem Keep RIF's project root as the working directory so imports, vnma, and
rem relative project paths work when this launcher is called from elsewhere.
pushd "%~dp0"
if errorlevel 1 (
    echo rif: unable to enter the RIF project directory 1>&2
    exit /b 1
)

call vnma run main.py %*
set "rif_status=%errorlevel%"
popd
exit /b %rif_status%
