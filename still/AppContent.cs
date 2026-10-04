using System.IO;
using System.Reflection;

namespace Still;

// The executable carries its UI as resources. Only these small web files need a folder for
// WebView's virtual-host mapping; managed runtime assemblies stay in the single-file bundle.
internal static class AppContent
{
 const string ShellPrefix = "Still.Content.Shell/";
 static readonly Assembly Assembly = typeof(AppContent).Assembly;
 static Task<string>? shellFolder;
 internal static Task<string> ShellFolder => shellFolder ??= Task.Run(MaterializeShell);

 static string MaterializeShell()
 {
  string folder = Path.Combine(App.DataRoot, "Cache", "Shell-" + Assembly.ManifestModule.ModuleVersionId.ToString("N"));
  string boundary = Path.GetFullPath(folder) + Path.DirectorySeparatorChar;
  var resources = Assembly.GetManifestResourceNames().Where(n => n.StartsWith(ShellPrefix, StringComparison.Ordinal)).ToArray();
  if (resources.Length == 0) throw new IOException("Still's interface resources are missing.");
  string ready = Path.Combine(folder, ".complete");
  if (File.Exists(ready) && resources.All(n => File.Exists(Path.Combine(folder, n[ShellPrefix.Length..].Replace('\\', Path.DirectorySeparatorChar))))) return folder;
  Directory.CreateDirectory(folder);
  foreach (string name in resources)
  {
   string relative = name[ShellPrefix.Length..].Replace('\\', Path.DirectorySeparatorChar).Replace('/', Path.DirectorySeparatorChar);
   string destination = Path.GetFullPath(Path.Combine(folder, relative));
   if (!destination.StartsWith(boundary, StringComparison.OrdinalIgnoreCase)) throw new IOException("Invalid interface resource path.");
   Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
   using var source = Assembly.GetManifestResourceStream(name) ?? throw new IOException("A Still interface resource is missing.");
   string temporary = destination + ".tmp";
   using (var output = File.Create(temporary)) source.CopyTo(output);
   File.Move(temporary, destination, true);
  }
  File.WriteAllText(ready, "ready");
  return folder;
 }

 internal static async Task<string> ReadAsset(string name)
 {
  using var stream = Assembly.GetManifestResourceStream("Still.Content.Assets/" + name) ?? throw new IOException("A Still script resource is missing.");
  using var reader = new StreamReader(stream);
  return await reader.ReadToEndAsync();
 }
}
