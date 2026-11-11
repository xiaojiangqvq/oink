; Standard NSIS MUI2 wizard. Windows Installer owns all product mutations.
Unicode true
!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
!include "WordFunc.nsh"
!insertmacro VersionCompare

!define OINK_UPGRADE_CODE "{4D39E4BE-6792-4CD6-B344-A5E95A270EA6}"
!define WEBVIEW_KEY "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
Name "Oink"
Caption "Oink 安装"
OutFile "${OUTPUT_EXE}"
Icon "${APP_ICON}"
BrandingText "Oink · 指针尾迹增强版"
CRCCheck force
SetCompressor /SOLID lzma
SetCompressorDictSize 32
ShowInstDetails nevershow
AutoCloseWindow true
!ifdef QA_PREVIEW
  RequestExecutionLevel user
!else
  RequestExecutionLevel admin
!endif
VIProductVersion "0.3.4.110"
VIAddVersionKey /LANG=2052 "ProductName" "Oink 指针尾迹增强版"
VIAddVersionKey /LANG=2052 "FileDescription" "Oink 安装程序（第三方修改版）"
VIAddVersionKey /LANG=2052 "FileVersion" "${DISPLAY_VERSION}"
VIAddVersionKey /LANG=2052 "LegalCopyright" "Oink contributors; third-party modifications"

Var ExistingProduct
Var ExistingVersion
Var ExistingCount
Var Mode
Var ModeDialog
Var OverlayRadio
Var RemoveRadio
Var CleanRadio
Var RuntimePresent
Var RuntimeAccepted
Var LogDir
Var LastResult
Var FinishText
Var MutexHandle

!define MUI_ICON "${APP_ICON}"
!define MUI_ABORTWARNING
Page custom ModePage ModeLeave
!define MUI_PAGE_CUSTOMFUNCTION_PRE LicensePre
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE LicenseLeave
!define MUI_LICENSEPAGE_TEXT_TOP "此电脑需要 Microsoft WebView2 运行时。请阅读微软许可。"
!define MUI_LICENSEPAGE_CHECKBOX
!define MUI_LICENSEPAGE_CHECKBOX_TEXT "我接受 Microsoft WebView2 许可条款"
!insertmacro MUI_PAGE_LICENSE "${SUPPORT_DIR}\license.txt"
!define MUI_PAGE_CUSTOMFUNCTION_PRE InstallPagePre
!insertmacro MUI_PAGE_INSTFILES
Page custom FinishPage
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  StrCpy $Mode "overlay"
  StrCpy $RuntimeAccepted 0
  StrCpy $FinishText "安装完成。请从开始菜单打开 Oink。"
  ; Silent mode cannot express the required license and destructive-action consent.
  IfSilent 0 +3
    SetErrorLevel 87
    Quit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "此安装程序需要 64 位 Windows。"
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "此安装程序需要 Windows 10 或更新版本。"
    Abort
  ${EndIf}
  SetRegView 64
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuildNumber"
  ${If} $0 < 17763
    MessageBox MB_ICONSTOP "此安装程序需要 Windows 10 1809 或更新版本。"
    Abort
  ${EndIf}
  !ifndef QA_PREVIEW
    System::Call 'kernel32::CreateMutexW(p 0, i 0, w "Global\OinkPointerTrailSetup") p.r0 ?e'
    Pop $1
    StrCpy $MutexHandle $0
    ${If} $0 = 0
    ${OrIf} $1 = 183
      MessageBox MB_ICONSTOP "另一个 Oink 安装程序正在运行。"
      Abort
    ${EndIf}
  !endif
  Call DetectProduct
  Call DetectRuntime
FunctionEnd

; Only a related product registered in the per-machine Windows Installer context
; may be repaired or removed. Registry display names and executable paths are not trusted.
Function DetectProduct
  StrCpy $ExistingProduct ""
  StrCpy $ExistingVersion ""
  StrCpy $ExistingCount 0
  StrCpy $4 0
  product_loop:
    System::Call 'msi::MsiEnumRelatedProductsW(w "${OINK_UPGRADE_CODE}", i 0, i r4, w .r0) i.r1'
    ${If} $1 = 259
      Goto product_done
    ${EndIf}
    ${If} $1 != 0
      MessageBox MB_ICONSTOP "无法读取 Oink 的安装信息，请稍后重试。"
      Abort
    ${EndIf}
    StrCpy $3 ${NSIS_MAX_STRLEN}
    System::Call 'msi::MsiGetProductInfoExW(w r0, p 0, i 4, w "VersionString", w .r2, *i r3) i.r1'
    ${If} $1 = 0
      IntOp $ExistingCount $ExistingCount + 1
      StrCpy $ExistingProduct $0
      StrCpy $ExistingVersion $2
    ${ElseIf} $1 != 1605
      MessageBox MB_ICONSTOP "无法读取 Oink 的安装版本，请先修复现有安装。"
      Abort
    ${EndIf}
    IntOp $4 $4 + 1
    Goto product_loop
  product_done:
  ${If} $ExistingCount > 1
    MessageBox MB_ICONSTOP "检测到多个 Oink 安装记录，请先在 Windows 设置中修复。"
    Abort
  ${EndIf}
FunctionEnd

Function DetectRuntime
  StrCpy $RuntimePresent 0
  SetRegView 32
  ReadRegStr $0 HKLM "${WEBVIEW_KEY}" "pv"
  ${If} $0 != ""
  ${AndIf} $0 != "0.0.0.0"
    StrCpy $RuntimePresent 1
  ${EndIf}
  SetRegView 64
FunctionEnd

Function ModePage
  !insertmacro MUI_HEADER_TEXT "安装 Oink" "指针尾迹增强版 ${DISPLAY_VERSION} · 第三方修改版"
  nsDialogs::Create 1018
  Pop $ModeDialog
  ${If} $ModeDialog == error
    Abort
  ${EndIf}
  ${If} $ExistingProduct == ""
    ${NSD_CreateLabel} 12u 16u 270u 32u "此电脑未安装 Oink。$\r$\n单击“下一步”继续安装。"
    Pop $0
    nsDialogs::Show
    Return
  ${EndIf}
  ${NSD_CreateRadioButton} 12u 16u 270u 16u "覆盖安装（保留设置和配对）"
  Pop $OverlayRadio
  ${NSD_CreateRadioButton} 12u 48u 270u 16u "卸载 Oink"
  Pop $RemoveRadio
  ${NSD_CreateRadioButton} 12u 80u 270u 16u "全新安装（删除原有设置和配对）"
  Pop $CleanRadio
  ${If} $Mode == "remove"
    ${NSD_Check} $RemoveRadio
  ${ElseIf} $Mode == "clean"
    ${NSD_Check} $CleanRadio
  ${Else}
    ${NSD_Check} $OverlayRadio
  ${EndIf}
  nsDialogs::Show
FunctionEnd

Function ModeLeave
  ${If} $ExistingProduct == ""
    Return
  ${EndIf}
  ${NSD_GetState} $OverlayRadio $0
  ${If} $0 = ${BST_CHECKED}
    StrCpy $Mode "overlay"
  ${Else}
    ${NSD_GetState} $RemoveRadio $0
    ${If} $0 = ${BST_CHECKED}
      StrCpy $Mode "remove"
    ${Else}
      StrCpy $Mode "clean"
    ${EndIf}
    MessageBox MB_YESNO|MB_ICONEXCLAMATION|MB_DEFBUTTON2 "此操作将删除 Oink 的本地设置和配对记录。确定继续？" IDYES +2
      Abort
  ${EndIf}
  Call CheckInstallVersion
FunctionEnd

Function CheckInstallVersion
  ${If} $Mode != "overlay"
  ${OrIf} $ExistingProduct == ""
    Return
  ${EndIf}
  ${VersionCompare} "$ExistingVersion" "${MSI_VERSION}" $0
  ${If} $0 = 1
    MessageBox MB_ICONSTOP "此电脑已安装更新版本的 Oink，无法安装较旧版本。"
    Abort
  ${EndIf}
  ${If} $0 = 0
  ${AndIf} $ExistingProduct != "${PRODUCT_CODE}"
    MessageBox MB_ICONSTOP "相同版本号的不同发行版不能相互覆盖，请使用更新版本。"
    Abort
  ${EndIf}
FunctionEnd

Function LicensePre
  ${If} $Mode == "remove"
  ${OrIf} $RuntimePresent = 1
    Abort
  ${EndIf}
FunctionEnd

Function LicenseLeave
  StrCpy $RuntimeAccepted 1
FunctionEnd

Function InstallPagePre
  Call CheckInstallVersion
FunctionEnd

Function FinishPage
  !insertmacro MUI_HEADER_TEXT "操作完成" "Oink · 指针尾迹增强版"
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 12u 20u 270u 80u "$FinishText"
  Pop $0
  GetDlgItem $0 $HWNDPARENT 1
  SendMessage $0 ${WM_SETTEXT} 0 "STR:完成"
  GetDlgItem $0 $HWNDPARENT 3
  EnableWindow $0 0
  GetDlgItem $0 $HWNDPARENT 2
  ShowWindow $0 ${SW_HIDE}
  nsDialogs::Show
FunctionEnd

; A unique, protected directory holds persistent MSI logs. CreateDirectory uses
; the restrictive descriptor at creation, never alters an existing directory ACL.
Function CreateLogDirectory
  System::Alloc 16
  Pop $0
  System::Call 'ole32::CoCreateGuid(p r0) i.r1'
  ${If} $1 != 0
    System::Free $0
    Goto log_failed
  ${EndIf}
  System::Call 'ole32::StringFromGUID2(p r0, w .r2, i ${NSIS_MAX_STRLEN}) i.r1'
  System::Free $0
  ${If} $1 = 0
    Goto log_failed
  ${EndIf}
  ; CSIDL_COMMON_APPDATA is resolved by Windows, not an environment variable.
  System::Call 'shell32::SHGetFolderPathW(p 0, i 0x23, p 0, i 0, w .r3) i.r1'
  ${If} $1 != 0
  ${OrIf} $3 == ""
    Goto log_failed
  ${EndIf}
  StrCpy $LogDir "$3\Oink-Setup-$2"
  System::Call 'advapi32::ConvertStringSecurityDescriptorToSecurityDescriptorW(w "O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)", i 1, *p .r0, p 0) i.r1'
  ${If} $1 = 0
    Goto log_failed
  ${EndIf}
  System::Call '*(i 12, p r0, i 0) p.r2'
  System::Call 'kernel32::CreateDirectoryW(w "$LogDir", p r2) i.r1'
  System::Free $2
  System::Call 'kernel32::LocalFree(p r0)'
  ${If} $1 = 0
    Goto log_failed
  ${EndIf}
  Return
  log_failed:
    SetErrorLevel 5
    MessageBox MB_ICONSTOP "无法创建安装日志目录，请检查磁盘空间和管理员权限。"
    Abort
FunctionEnd

Function CheckResult
  ${If} $LastResult = 3010
    SetRebootFlag true
    Return
  ${EndIf}
  ${If} $LastResult = 0
    Return
  ${EndIf}
  DetailPrint "操作未完成。日志：$LogDir"
  SetErrorLevel $LastResult
  MessageBox MB_ICONSTOP "操作未完成。请关闭其他安装程序后重试。$\r$\n安装日志：$LogDir"
  Abort
FunctionEnd

Section "Oink"
  !ifdef QA_PREVIEW
    ; This binary is incapable of executing payloads, removing products, or changing settings.
    DetailPrint "界面预览：没有执行安装、卸载或运行时安装。"
    StrCpy $FinishText "界面预览已完成。未安装或卸载任何内容。"
    SetErrorLevel 0
  !else
    Call CreateLogDirectory
    InitPluginsDir
    ; NSIS 3.11+ creates $PLUGINSDIR with restricted permissions when elevated.
    ; CRCCheck force verifies the embedded stream before any executable is extracted.
    SetOutPath "$PLUGINSDIR\Support"
    File /r "${SUPPORT_DIR}\*"
    ${If} $Mode != "remove"
      SetOutPath "$PLUGINSDIR\payload"
      File /oname=Oink.msi "${BUNDLE_DIR}\payload\Oink.msi"
      ${If} $RuntimePresent = 0
        File /oname=MicrosoftEdgeWebView2RuntimeInstallerX64.exe "${BUNDLE_DIR}\payload\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
      ${EndIf}
    ${EndIf}
    ; Recheck the MSI registration just before acting; other installers can run
    ; while the user is reading wizard pages.
    StrCpy $5 $ExistingProduct
    StrCpy $6 $ExistingVersion
    Call DetectProduct
    ${If} $ExistingProduct != $5
    ${OrIf} $ExistingVersion != $6
      MessageBox MB_ICONSTOP "Oink 的安装状态已改变，请重新打开此安装程序。"
      SetErrorLevel 1618
      Abort
    ${EndIf}
    Call CheckInstallVersion
    ; Recheck prerequisite consent before a selected clean removal begins.
    Call DetectRuntime
    ${If} $Mode != "remove"
    ${AndIf} $RuntimePresent = 0
    ${AndIf} $RuntimeAccepted != 1
      MessageBox MB_ICONSTOP "WebView2 状态已改变，请重新运行安装程序并阅读运行时许可。"
      SetErrorLevel 1602
      Abort
    ${EndIf}
    ${If} $Mode == "remove"
    ${OrIf} $Mode == "clean"
      DetailPrint "正在卸载 Oink…"
      StrCpy $LastResult 1603
      ExecWait '"$SYSDIR\msiexec.exe" /x $ExistingProduct /qn /norestart /l*v "$LogDir\uninstall.log"' $LastResult
      Call CheckResult
      ${If} $Mode == "remove"
        StrCpy $FinishText "Oink 已卸载。"
        Goto operation_done
      ${EndIf}
      ; An uninstall that requires reboot must complete before a fresh install.
      ${If} $LastResult = 3010
        StrCpy $FinishText "旧版已卸载。请重新启动 Windows，然后再次运行此安装程序。"
        Goto operation_done
      ${EndIf}
      StrCpy $ExistingProduct ""
    ${EndIf}
    Call DetectRuntime
    ${If} $RuntimePresent = 0
      ${If} $RuntimeAccepted != 1
        MessageBox MB_ICONSTOP "WebView2 状态已改变，请重新运行安装程序并阅读运行时许可。"
        SetErrorLevel 1602
        Abort
      ${EndIf}
      DetailPrint "正在安装 Microsoft WebView2…"
      StrCpy $LastResult 1603
      ExecWait '"$PLUGINSDIR\payload\MicrosoftEdgeWebView2RuntimeInstallerX64.exe" /silent /install' $LastResult
      Call CheckResult
      Call DetectRuntime
      ${If} $RuntimePresent != 1
        MessageBox MB_ICONSTOP "WebView2 尚未准备就绪。请重新启动 Windows 后重试。"
        SetErrorLevel 1603
        Abort
      ${EndIf}
    ${EndIf}
    DetailPrint "正在安装 Oink…"
    StrCpy $LastResult 1603
    ${If} $ExistingProduct == "${PRODUCT_CODE}"
      ExecWait '"$SYSDIR\msiexec.exe" /i "$PLUGINSDIR\payload\Oink.msi" REINSTALL=ALL REINSTALLMODE=amus /qn /norestart /l*v "$LogDir\install.log"' $LastResult
    ${Else}
      ExecWait '"$SYSDIR\msiexec.exe" /i "$PLUGINSDIR\payload\Oink.msi" /qn /norestart /l*v "$LogDir\install.log"' $LastResult
    ${EndIf}
    Call CheckResult
    StrCpy $FinishText "安装完成。请从开始菜单打开 Oink。"
    operation_done:
    IfRebootFlag 0 operation_no_reboot
      StrCpy $FinishText "$FinishText$\r$\n$\r$\n请重新启动 Windows，以完成更改。"
      SetErrorLevel 3010
      Goto operation_exit
    operation_no_reboot:
      SetErrorLevel 0
    operation_exit:
  !endif
SectionEnd
