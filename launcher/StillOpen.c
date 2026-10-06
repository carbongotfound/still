// Tiny link handler: Windows starts this instead of the 160 MB Still.exe when a link is clicked in another app.
// If Still is open it hands the link over a pipe and exits in milliseconds; otherwise it starts Still.exe.
#include <windows.h>
#include <shellapi.h>
#include <shlwapi.h>

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR cmd, int show)
{
 int argc; LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
 if (argv && argc == 2 && (!_wcsnicmp(argv[1], L"http://", 7) || !_wcsnicmp(argv[1], L"https://", 8))) {
  WCHAR user[257], pipe[320]; DWORD n = 257;
  if (GetUserNameW(user, &n)) {
   wsprintfW(pipe, L"\\\\.\\pipe\\Still-links-%s", user);
   for (int i = 0; i < 5; i++) { // a few quick retries: the listener re-opens the pipe between links
    HANDLE f = CreateFileW(pipe, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (f != INVALID_HANDLE_VALUE) {
     static char buf[16384]; DWORD wrote;
     int len = WideCharToMultiByte(CP_UTF8, 0, argv[1], -1, buf, sizeof buf, NULL, NULL);
     AllowSetForegroundWindow(ASFW_ANY); // let the open window come to the front
     BOOL ok = len > 1 && WriteFile(f, buf, len - 1, &wrote, NULL);
     CloseHandle(f);
     if (ok) return 0;
     break;
    }
    if (GetLastError() == ERROR_PIPE_BUSY) WaitNamedPipeW(pipe, 1000); else Sleep(15);
   }
  }
 }
 // Still isn't open (or this isn't a web link): start Still.exe with the same arguments.
 static WCHAR exe[MAX_PATH], line[32768];
 GetModuleFileNameW(NULL, exe, MAX_PATH); PathRemoveFileSpecW(exe); PathAppendW(exe, L"Still.exe");
 wsprintfW(line, L"\"%s\" ", exe); lstrcatW(line, PathGetArgsW(GetCommandLineW()));
 STARTUPINFOW si = { sizeof si }; PROCESS_INFORMATION pi;
 if (!CreateProcessW(exe, line, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) return 1;
 AllowSetForegroundWindow(pi.dwProcessId);
 CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
 return 0;
}
