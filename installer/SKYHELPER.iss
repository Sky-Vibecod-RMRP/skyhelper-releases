; ============================================================================
; SKY HELPER — установщик для админов.
;
; Сборка:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\SKYHELPER.iss
; Результат: dist\SKYHELPER_Setup.exe
;
; Решения, принятые сознательно:
;   • PrivilegesRequired=lowest — установка в профиль пользователя, БЕЗ UAC:
;     админ ставит на свой ПК даже без прав администратора Windows;
;     данные и так лежат в %APPDATA%\SKYHELPER.
;   • Программа и данные при переустановке НЕ удаляются — активация
;     лицензии и статистика переживают обновление.
;   • Автозапуск — ключ в HKCU\...\Run с флагом --minimized (см. README).
;   • «От администратора» — запись в AppCompatFlags\Layers: нужно, если
;     игра запущена от администратора, иначе горячие клавиши не работают.
;   • Ребрендинг 1.0.7: файл программы теперь SKYHELPER.exe (был
;     RMRPAdminTracker.exe). Переход со старых версий закрыт в [Code]:
;     taskkill убивает ОБА имени, автозагрузка/слой/ярлыки переводятся
;     на новое имя, старый exe удаляется после копирования.
; Записи секций должны быть ОДНОСТРОЧНЫМИ — Inno не умеет продолжения строки.
; ============================================================================
#define MyAppName "SKY HELPER"
#define MyAppVersion "1.0.11"
#define MyAppPublisher "RMRP Staff"
#define MyAppExeName "SKYHELPER.exe"
#define MyAppOldExeName "RMRPAdminTracker.exe"

[Setup]
AppId={{4E9B7A62-3C51-4D8E-9F20-534B5948454C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SKY HELPER
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SKYHELPER_Setup
SetupIconFile=..\assets\SKYHELPER.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=yes
SetupLogging=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductTextVersion={#MyAppVersion}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"; Flags: checkedonce
Name: "autostart"; Description: "Запускать при входе в Windows (сворачивать в трей)"; GroupDescription: "Дополнительно:"; Flags: unchecked
Name: "runasadmin"; Description: "Запускать от имени администратора (если игра запущена от администратора)"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "..\dist\SKYHELPER.exe"; DestDir: "{app}"; Flags: ignoreversion
; Ярлык локального сайта статистики: адрес http://sky-grafana.rmrp/
; (домен прописывает сама программа при запуске — см. app/hosts.py).
Source: "..\sky-grafana.rmrp.url"; DestDir: "{userdesktop}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SKY HELPER"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart
Root: HKCU; Subkey: "Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"; ValueType: string; ValueName: "{app}\{#MyAppExeName}"; ValueData: "RUNASADMIN"; Flags: uninsdeletevalue; Tasks: runasadmin

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

; программа пишет журнал рядом с собой — его тоже убираем при удалении
[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"

[Code]
// Флаг перехода со старой версии (ребрендинг): старый exe был на месте.
var
  gOldExeExisted: Boolean;

// SKY HELPER по дизайну не выходит по крестику — окно лишь прячется в трей,
// а процесс продолжает жить. Restart Manager (CloseApplications) такое закрыть
// не может, и ручная установка поверх работающей программы упиралась в ошибку
// «Программе установки не удалось автоматически закрыть все приложения».
// Гасим принудительно в самом начале — InitializeSetup идёт раньше всех
// страниц и раньше проверки занятых файлов. В тихом автообновлении программа
// к этому моменту завершается сама: taskkill лишь добивает остатки (второй
// процесс-распаковщик onefile) и убирает гонку при копировании.
// Имя убиваемого: ОБА — новое (SKYHELPER.exe) и старое (RMRPAdminTracker.exe),
// пока на машинах живут версии до ребрендинга 1.0.7.
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  Exec('taskkill.exe', '/IM {#MyAppExeName} /F /T', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
  Exec('taskkill.exe', '/IM {#MyAppOldExeName} /F /T', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
end;

// --- Ребрендинг: всё, что привязано к старому имени exe, переводится ------
// на новое. Вызывается на ssInstall — {app} уже окончательный, а файлы ещё
// не скопированы (значения реестра и цели ярлыков правим до подмены exe).

function ReplaceStr(const S, FromR, ToR: String): String;
var
  P: Integer;
begin
  Result := '';
  P := Pos(FromR, S);
  while P > 0 do
  begin
    Result := Result + Copy(S, 1, P - 1) + ToR;
    Delete(S, 1, P + Length(FromR) - 1);
    P := Pos(FromR, S);
  end;
  Result := Result + S;
end;

// Ярлык (рабочий стол или меню «Пуск»): цель указывает на старый файл —
// переставляем на новый. Имя файла совпадает с {#MyAppName}.lnk, поэтому
// при первой установке просто нет файла — выходим молча.
procedure RetargetLnk(const FolderPath: String);
var
  Shell, Folder, Item, Link: Variant;
begin
  if not FileExists(AddBackslash(FolderPath) + '{#MyAppName}.lnk') then
    Exit;
  try
    Shell := CreateOleObject('Shell.Application');
    Folder := Shell.Namespace(FolderPath);
    Item := Folder.ParseName('{#MyAppName}.lnk');
    Link := Item.GetLink;
    Link.Path := ExpandConstant('{app}\{#MyAppExeName}');
    Link.WorkingDirectory := ExpandConstant('{app}');
    Link.Save;
  except
    // не вышло — не мешаем установке; худший случай: старый ярлык останется
  end;
end;

procedure MigrateOldName();
var
  OldExe, NewExe, Value: String;
begin
  OldExe := ExpandConstant('{app}\{#MyAppOldExeName}');
  NewExe := ExpandConstant('{app}\{#MyAppExeName}');

  // 1) Автозапуск: значение HKCU\...\Run вело на старое имя файла.
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run',
                         'SKY HELPER', Value) then
    if Pos('{#MyAppOldExeName}', Value) > 0 then
      RegWriteStringValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run',
                          'SKY HELPER',
                          ReplaceStr(Value, '{#MyAppOldExeName}', '{#MyAppExeName}'));

  // 2) Слой «Запуск от администратора»: записан на старый путь — копируем
  //    на новый и убираем старую (иначе RUNASADMIN пропадёт после обновления,
  //    а задача runasadmin в тихом обновлении может не выполняться).
  if RegQueryStringValue(HKCU,
         'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers',
         OldExe, Value) then
  begin
    RegWriteStringValue(HKCU,
      'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers',
      NewExe, Value);
    RegDeleteValue(HKCU,
      'Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers',
      OldExe);
  end;

  // 3) Ярлыки: цель на старый файл — переставляем на новый.
  RetargetLnk(ExpandConstant('{userdesktop}'));
  RetargetLnk(ExpandConstant('{userprograms}\{#MyAppName}'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssInstall then
  begin
    gOldExeExisted := FileExists(ExpandConstant('{app}\{#MyAppOldExeName}'));
    MigrateOldName();
  end;
  if CurStep = ssPostInstall then
  begin
    if gOldExeExisted then
    begin
      DeleteFile(ExpandConstant('{app}\{#MyAppOldExeName}'));
      // Переход со старой версии в тихом автообновлении: перезапуск у 1.0.6
      // вёл на удалённый старый exe (start молча упадёт) — поднимаем новую
      // копию сами. В не тихом режиме это делает страница [Run], и здесь
      // стартовать нельзя — иначе запустятся ДВЕ копии (счётчики удвоятся).
      if WizardSilent() then
        Exec(ExpandConstant('{app}\{#MyAppExeName}'), '',
             ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, ResultCode);
    end;
  end;
end;
