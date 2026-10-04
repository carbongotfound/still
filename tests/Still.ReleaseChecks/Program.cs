using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;

if (args.Length != 2) throw new ArgumentException("Pass the production Still.dll and repository root.");
using var file = File.OpenRead(args[0]);
using var pe = new PEReader(file);
var metadata = pe.GetMetadataReader();
var types = metadata.TypeDefinitions.Select(h => metadata.GetTypeDefinition(h)).ToArray();
bool HasMethod(string type, string method) => types.Where(t => metadata.GetString(t.Name) == type)
 .Any(t => t.GetMethods().Any(h => metadata.GetString(metadata.GetMethodDefinition(h).Name) == method));
void Check(bool ok, string name) { if (!ok) throw new Exception("FAIL: " + name); Console.WriteLine("PASS: " + name); }
Check(!HasMethod("MainWindow", "StartQa"), "Production omits the QA automation server");
Check(!types.Where(t => metadata.GetString(t.Name) == "StartupMetrics").Any(t =>
 t.GetFields().Any(h => metadata.GetString(metadata.GetFieldDefinition(h).Name) == "Timings")), "Production omits QA timing data");

const string prefix = "Still.Content.";
var directory = pe.PEHeaders.CorHeader!.ResourcesDirectory;
var resourceData = pe.GetSectionData(directory.RelativeVirtualAddress);
var content = metadata.ManifestResources.Select(h => metadata.GetManifestResource(h))
 .Where(r => metadata.GetString(r.Name).StartsWith(prefix, StringComparison.Ordinal)).ToArray();
int expected = Directory.GetFiles(Path.Combine(args[1], "still", "Shell"), "*", SearchOption.AllDirectories).Length + 2;
Check(content.Length == expected, "Every interface file and both browser scripts are embedded");
foreach (var resource in content)
{
 string relative = metadata.GetString(resource.Name)[prefix.Length..].Replace('/', Path.DirectorySeparatorChar).Replace('\\', Path.DirectorySeparatorChar);
 var reader = resourceData.GetReader((int)resource.Offset, directory.Size - (int)resource.Offset);
 int size = reader.ReadInt32();
 var bytes = reader.ReadBytes(size);
 Check(bytes.AsSpan().SequenceEqual(File.ReadAllBytes(Path.Combine(args[1], "still", relative))), "Embedded content matches source: " + relative);
}
