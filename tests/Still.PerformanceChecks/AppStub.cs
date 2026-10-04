namespace Still;
// The pipe/parser checks have no WPF window, profile writes or browser-registration side effects.
internal static class App
{
 internal static bool IsQa => true;
 internal static void Log(Exception error) { }
}
