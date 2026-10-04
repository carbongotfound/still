using System.Buffers.Binary;
using System.IO.Compression;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;
using Still;

int passed = 0;
void Check(bool result, string name) { if (!result) throw new Exception("FAIL: " + name); Console.WriteLine("PASS: " + name); passed++; }
void Reject(byte[] data, string id, string name) { try { CrxPackage.Verify(data, id); } catch (InvalidDataException) { Check(true, name); return; } throw new Exception("FAIL: " + name); }
byte[] Varint(ulong n) { var bytes = new List<byte>(); do { byte next = (byte)(n & 127); n >>= 7; bytes.Add((byte)(next | (n == 0 ? 0 : 128))); } while(n != 0); return bytes.ToArray(); }
byte[] Field(int number, byte[] bytes) => [..Varint((ulong)((number << 3) | 2)), ..Varint((ulong)bytes.Length), ..bytes];
byte[] Size(int n) { byte[] bytes = new byte[4]; BinaryPrimitives.WriteInt32LittleEndian(bytes, n); return bytes; }
byte[] Archive()
{
 using var output = new MemoryStream();
 using (var zip = new ZipArchive(output, ZipArchiveMode.Create, true))
 using (var writer = new StreamWriter(zip.CreateEntry("manifest.json").Open())) writer.Write("{\"name\":\"Fixture\",\"manifest_version\":3,\"version\":\"1.0\"}");
 return output.ToArray();
}
using var rsa = RSA.Create(2048);
byte[] publicKey = rsa.ExportSubjectPublicKeyInfo();
string id = CrxPackage.ExtensionId(publicKey);
byte[] zip = Archive();
byte[] signed = Field(1, SHA256.HashData(publicKey)[..16]);
byte[] body = [.."CRX3 SignedData\0"u8, ..Size(signed.Length), ..signed, ..zip];
byte[] proof = [..Field(1, publicKey), ..Field(2, rsa.SignData(body, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1))];
byte[] header = [..Field(2, proof), ..Field(10000, signed)];
byte[] package = [.."Cr24"u8, ..Size(3), ..Size(header.Length), ..header, ..zip];
var verified = CrxPackage.Verify(package, id);
Check(verified.Id == id && verified.PublicKey == Convert.ToBase64String(publicKey), "RSA package retains developer identity");
Check(package.AsSpan(verified.ArchiveOffset).SequenceEqual(zip), "Archive offset is exact");
Reject(package, new string(id[0] == 'a' ? 'b' : 'a', 32), "Wrong store ID refused");
var changed = package.ToArray(); changed[^1] ^= 1; Reject(changed, id, "Changed archive refused");
changed = package.ToArray(); changed[14] ^= 1; Reject(changed, id, "Changed public key refused");
changed = package.ToArray(); BinaryPrimitives.WriteUInt32LittleEndian(changed.AsSpan(8), uint.MaxValue); Reject(changed, id, "Oversized header refused");
Reject(package[..20], id, "Truncated header refused");
Reject([.."Cr24"u8, ..Size(3), ..Size(2), 0x12, 0xff, 0], id, "Malformed protobuf refused");
Reject(package, "../outside", "Invalid expected ID refused");
header = [..Field(2, proof), ..Field(10000, signed), ..Field(10000, signed)];
Reject([.."Cr24"u8, ..Size(3), ..Size(header.Length), ..header, ..zip], id, "Duplicate signed headers refused");
using var ec = ECDsa.Create(ECCurve.NamedCurves.nistP256);
byte[] ecKey = ec.ExportSubjectPublicKeyInfo(); string ecId = CrxPackage.ExtensionId(ecKey);
signed = Field(1, SHA256.HashData(ecKey)[..16]); body = [.."CRX3 SignedData\0"u8, ..Size(signed.Length), ..signed, ..zip];
proof = [..Field(1, ecKey), ..Field(2, ec.SignData(body, HashAlgorithmName.SHA256, DSASignatureFormat.Rfc3279DerSequence))];
header = [..Field(3, proof), ..Field(10000, signed)];
Check(CrxPackage.Verify((byte[])[.."Cr24"u8, ..Size(3), ..Size(header.Length), ..header, ..zip], ecId).Id == ecId, "ECDSA developer proof supported");
var signature = rsa.SignData(zip, HashAlgorithmName.SHA1, RSASignaturePadding.Pkcs1);
Check(CrxPackage.Verify((byte[])[.."Cr24"u8, ..Size(2), ..Size(publicKey.Length), ..Size(signature.Length), ..publicKey, ..signature, ..zip], id).Id == id, "CRX2 identity retained");
if (args.Length == 2)
{
 var store = CrxPackage.Verify(File.ReadAllBytes(args[0]), args[1]);
 Check(store.Id == args[1], "Official downloaded store package signature and ID verified");
}
Check(BrowserRegistration.UrlFromArgs(["--profile", "https://wrong.example/", "--profiles-root", "https://also-wrong.example/", "https://right.example/"]) == "https://right.example/", "Profile arguments are never treated as launch URLs");
Check(BrowserRegistration.UrlFromArgs(["javascript:alert(1)","data:text/html,test"]) == null, "Executable URL schemes are refused");
string instance = "Local\\Still-check-" + Guid.NewGuid().ToString("N");
var received = new System.Collections.Concurrent.ConcurrentQueue<string>();
using (BrowserRegistration.Listen(instance, received.Enqueue))
{
 Check(BrowserRegistration.Forward(instance,"https://example.com/first"), "First pipe accepts a link immediately");
 async Task Until(Func<bool> condition) { var end = DateTime.UtcNow.AddSeconds(6); while(!condition() && DateTime.UtcNow < end) await Task.Delay(20); if(!condition())throw new Exception("Pipe timeout"); }
 await Until(()=>received.Count==1);
 Check(received.TryDequeue(out var link) && link=="https://example.com/first", "Link is delivered exactly once");
 Check(BrowserRegistration.Forward(instance,"javascript:alert(1)"), "Invalid URL can be submitted for rejection");
 Check(BrowserRegistration.Forward(instance,"https://example.com/"+new string('x',20000)), "Oversized request can be submitted for rejection");
 Check(BrowserRegistration.Forward(instance,"https://example.com/after-rejection"), "Pipe survives rejected requests");
 await Until(()=>received.Count>=1);
 Check(received.TryDequeue(out link) && link=="https://example.com/after-rejection" && received.IsEmpty, "Invalid and oversized links are never opened");
 using(var stalled = new NamedPipeClientStream(".",instance.Replace("Local\\","")+"-open",PipeDirection.Out,PipeOptions.CurrentUserOnly))
 {
  stalled.Connect(3000);
  await Task.Delay(3400);
  Check(BrowserRegistration.Forward(instance,"https://example.com/after-timeout"), "A stalled sender cannot keep link handling blocked");
  await Until(()=>received.Count==1);
 }
}
Console.WriteLine($"{passed} checks passed.");
