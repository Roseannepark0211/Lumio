; ============================================================
; NSIS 自定义脚本 — 安装/卸载前杀进程
; ============================================================
; 问题背景：
;   - 升级安装时，旧版 Lumio.exe 可能正在运行，导致覆盖文件报"文件被占用"
;   - 卸载时，Lumio.exe + LumioAPI.exe 子进程可能仍在后台运行
;     （FastAPI 子进程不一定随主进程退出），导致卸载后残留进程 + 文件删不掉
;
; 解决方案：
;   - PREINSTALL: 安装前（含升级）杀掉所有 Lumio.exe + LumioAPI.exe 进程
;   - PREUNINSTALL: 卸载前杀掉所有 Lumio.exe + LumioAPI.exe 进程
;
; taskkill 参数：
;   /F = 强制结束（不发 WM_CLOSE，直接 TerminateProcess）
;   /IM = 按进程名匹配
;   /T = 递归杀子进程（LumioAPI.exe 是 Lumio.exe spawn 的子进程）
;
; 退出码：
;   0   = 成功杀死
;   128 = 进程未运行（正常情况，忽略）
;   其他 = 错误（忽略，不阻塞安装/卸载）
; ============================================================

!macro NSIS_HOOK_PREINSTALL
  ; 安装前（含升级）杀掉运行中的 Lumio，避免文件占用
  nsExec::Exec 'taskkill /F /IM Lumio.exe /T'
  Pop $0
  nsExec::Exec 'taskkill /F /IM LumioAPI.exe /T'
  Pop $0
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  ; 卸载前杀掉运行中的 Lumio + FastAPI 子进程
  nsExec::Exec 'taskkill /F /IM Lumio.exe /T'
  Pop $0
  nsExec::Exec 'taskkill /F /IM LumioAPI.exe /T'
  Pop $0
!macroend
