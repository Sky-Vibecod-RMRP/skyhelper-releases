@echo off
title sky-grafana.rmrp - ustanovka domena
net session >nul 2>&1
if errorlevel 1 goto :need_admin

set "HOSTS=%SystemRoot%\System32\drivers\etc\hosts"
findstr /c:"sky-grafana.rmrp" "%HOSTS%" >nul 2>&1
if not errorlevel 1 goto :already

echo 127.0.0.1 sky-grafana.rmrp>>"%HOSTS%"
if errorlevel 1 goto :fail

echo.
echo  Готово! Домен sky-grafana.rmrp прописан.
echo  Теперь включи сам сайт: Настройки -^> вкладка "Сайт" -^> включить.
echo  После этого открывай  http://sky-grafana.rmrp/
echo.
pause
exit /b 0

:need_admin
echo.
echo  Нужны права администратора.
echo  Закрой это окно, щёлкни по файлу ПРАВОЙ кнопкой мыши
echo  и выбери "Запуск от имени администратора".
echo.
pause
exit /b 1

:already
echo.
echo  Домен уже прописан - ничего делать не надо.
echo  Открывай http://sky-grafana.rmrp/
echo.
pause
exit /b 0

:fail
echo.
echo  Не получилось записать в hosts. Проверь антивирус и права.
echo.
pause
exit /b 1
