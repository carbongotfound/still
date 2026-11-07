// Tiny link handler: Windows starts this instead of the 160 MB Still.exe when a link is clicked in another app.
// If Still is open it hands the link over a pipe and exits in milliseconds; otherwise it starts Still.exe.
#include <windows.h>
#include <wchar.h>
#include <shellapi.h>
#include <shlwapi.h>

#ifndef LINK_PIPE
#define LINK_PIPE L"\\\\.\\pipe\\Still-links-%s"
#endif

static BOOL UserOf(HANDLE process, BYTE *out, DWORD size)
{
 HANDLE token; DWORD got; BOOL ok;
 if (!OpenProcessToken(process, TOKEN_QUERY, &token)) return FALSE;
 ok = GetTokenInformation(token, TokenUser, out, size, &got);
 CloseHandle(token);
 return ok;
}

// Anyone can name a pipe, so a link goes only to a process of this same user.
static BOOL OwnedByMe(HANDLE pipe, ULONG *pid)
{
 BYTE mine[256], theirs[256]; HANDLE server; BOOL same;
 if (!GetNamedPipeServerProcessId(pipe, pid)) return FALSE;
 if (!(server = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, *pid))) return FALSE;
 same = UserOf(server, theirs, sizeof theirs) && UserOf(GetCurrentProcess(), mine, sizeof mine)
  && EqualSid(((TOKEN_USER *)mine)->User.Sid, ((TOKEN_USER *)theirs)->User.Sid);
 CloseHandle(server);
 return same;
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR cmd, int show)
{
 int argc; LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);
 if (argv && argc == 2 && (!_wcsnicmp(argv[1], L"http://", 7) || !_wcsnicmp(argv[1], L"https://", 8))) {
  WCHAR user[257], pipe[320]; DWORD n = 257;
  if (GetUserNameW(user, &n)) {
   wsprintfW(pipe, LINK_PIPE, user);
   for (int i = 0; i < 5; i++) { // a few quick retries: the listener re-opens the pipe between links
    HANDLE f = CreateFileW(pipe, GENERIC_WRITE, 0, NULL, OPEN_EXISTING, SECURITY_SQOS_PRESENT | SECURITY_IDENTIFICATION, NULL);
    if (f != INVALID_HANDLE_VALUE) {
     ULONG owner = 0;
     if (!OwnedByMe(f, &owner)) { CloseHandle(f); break; } // someone else holds the name: start Still instead
     static char buf[16384]; DWORD wrote;
     int len = WideCharToMultiByte(CP_UTF8, 0, argv[1], -1, buf, sizeof buf, NULL, NULL);
     AllowSetForegroundWindow(owner); // let the open window come to the front
     BOOL ok = len > 1 && WriteFile(f, buf, len - 1, &wrote, NULL);
     CloseHandle(f);
     if (ok) return 0;
     break;
    }
    if (GetLastError() == ERROR_PIPE_BUSY) WaitNamedPipeW(pipe, 1000); else Sleep(15);
   }
  }
 }
 // Still isn't open (or this isn't a web link): start Still.exe. Windows passes a link as one quoted argument, so anything
 // else came from inside a link, and Still gets none of it.
 static WCHAR exe[MAX_PATH], line[32768];
 GetModuleFileNameW(NULL, exe, MAX_PATH); PathRemoveFileSpecW(exe); PathAppendW(exe, L"Still.exe");
 lstrcpyW(line, L"\""); lstrcatW(line, exe); lstrcatW(line, L"\"");
 if (argv && argc == 2 && !wcschr(argv[1], L'"') && lstrlenW(argv[1]) < 30000) { lstrcatW(line, L" --link \""); lstrcatW(line, argv[1]); lstrcatW(line, L"\""); }
 STARTUPINFOW si = { sizeof si }; PROCESS_INFORMATION pi;
 if (!CreateProcessW(exe, line, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) return 1;
 AllowSetForegroundWindow(pi.dwProcessId);
 CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
 return 0;
}
