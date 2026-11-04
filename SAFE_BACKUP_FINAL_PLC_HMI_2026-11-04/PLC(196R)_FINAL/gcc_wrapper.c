
#include <windows.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    if (GetFileAttributesA("ladder_patched.c") != INVALID_FILE_ATTRIBUTES) {
        CopyFileA("ladder_patched.c", "ladder.c", FALSE);
    }
    LPSTR origCmd = GetCommandLineA();
    char cmdLine[32768];
    strncpy(cmdLine, origCmd, sizeof(cmdLine) - 1);
    cmdLine[sizeof(cmdLine) - 1] = '\0';

    char modPath[MAX_PATH];
    GetModuleFileNameA(NULL, modPath, MAX_PATH);
    char *lastSlash = strrchr(modPath, '\\');
    if (lastSlash) *(lastSlash + 1) = '\0';
    char realExe[MAX_PATH];
    snprintf(realExe, sizeof(realExe), "%sarm-none-eabi-gcc-real.exe", modPath);

    STARTUPINFOA si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessA(realExe, cmdLine, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        return 1;
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exitCode = 0;
    GetExitCodeProcess(pi.hProcess, &exitCode);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return (int)exitCode;
}
