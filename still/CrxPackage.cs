using System.Buffers.Binary;
using System.IO;
using System.Security.Cryptography;

namespace Still;

// CRX format: chromium/components/crx_file/crx3.proto and crx_verifier.cc.
// Retain the signed developer key so unpacked installation keeps the store extension's identity.
internal static class CrxPackage
{
 internal sealed record Verified(int ArchiveOffset, string PublicKey, string Id);
 readonly record struct Field(int Number, ReadOnlyMemory<byte> Data);

 internal static string ExtensionId(ReadOnlySpan<byte> key)
 {
  var hash = SHA256.HashData(key);
  Span<char> id = stackalloc char[32];
  for (int i = 0; i < 16; i++) { id[i * 2] = (char)('a' + (hash[i] >> 4)); id[i * 2 + 1] = (char)('a' + (hash[i] & 15)); }
  return new string(id);
 }

 internal static Verified Verify(ReadOnlyMemory<byte> package, string expectedId)
 {
  if (expectedId.Length != 32 || expectedId.Any(c => c is < 'a' or > 'p')) throw new InvalidDataException("Invalid extension ID.");
  var bytes = package.Span;
  if (bytes.Length < 16 || bytes.Length > 100 * 1024 * 1024 || !bytes[..4].SequenceEqual("Cr24"u8)) throw new InvalidDataException("Invalid extension package.");
  uint version = BinaryPrimitives.ReadUInt32LittleEndian(bytes[4..]);
  try
  {
   if (version == 2)
   {
    uint keySize = BinaryPrimitives.ReadUInt32LittleEndian(bytes[8..]), signatureSize = BinaryPrimitives.ReadUInt32LittleEndian(bytes[12..]);
    long start = 16L + keySize + signatureSize;
    if (keySize is 0 or > 65536 || signatureSize is 0 or > 65536 || start >= bytes.Length) throw new InvalidDataException("Invalid extension header.");
    var key = bytes.Slice(16, (int)keySize);
    if (ExtensionId(key) != expectedId) throw new InvalidDataException("The package belongs to a different extension.");
    using var rsa = RSA.Create(); rsa.ImportSubjectPublicKeyInfo(key, out int read);
    if (read != key.Length || !rsa.VerifyData(bytes[(int)start..], bytes.Slice(16 + (int)keySize, (int)signatureSize), HashAlgorithmName.SHA1, RSASignaturePadding.Pkcs1))
     throw new InvalidDataException("The extension signature is invalid.");
    return new((int)start, Convert.ToBase64String(key), expectedId);
   }
   if (version != 3) throw new InvalidDataException("Unsupported extension package version.");
   uint size = BinaryPrimitives.ReadUInt32LittleEndian(bytes[8..]);
   if (size is 0 or > 1024 * 1024 || 12L + size >= bytes.Length) throw new InvalidDataException("Invalid extension header.");
   int offset = 12 + (int)size;
   var fields = Fields(package.Slice(12, (int)size));
   var signed = One(fields, 10000);
   var signedId = One(Fields(signed), 1).Span;
   if (signedId.Length != 16 || !signedId.SequenceEqual(IdBytes(expectedId))) throw new InvalidDataException("The package belongs to a different extension.");
   using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
   hash.AppendData("CRX3 SignedData\0"u8);
   Span<byte> length = stackalloc byte[4]; BinaryPrimitives.WriteInt32LittleEndian(length, signed.Length);
   hash.AppendData(length); hash.AppendData(signed.Span); hash.AppendData(bytes[offset..]);
   var digest = hash.GetHashAndReset();
   var proofs = fields.Where(f => f.Number is 2 or 3).ToArray();
   if (proofs.Length is 0 or > 32) throw new InvalidDataException("Invalid extension proofs.");
   foreach (var proof in proofs)
   {
    var values = Fields(proof.Data); var key = One(values, 1).Span; var signature = One(values, 2).Span;
    if (key.Length is 0 or > 65536 || signature.Length is 0 or > 65536) throw new InvalidDataException("Invalid extension proof.");
    if (ExtensionId(key) != expectedId) continue;
    bool valid;
    if (proof.Number == 2)
    {
     using var rsa = RSA.Create(); rsa.ImportSubjectPublicKeyInfo(key, out int read);
     valid = read == key.Length && rsa.VerifyHash(digest, signature, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
    }
    else
    {
     using var ec = ECDsa.Create(); ec.ImportSubjectPublicKeyInfo(key, out int read);
     valid = read == key.Length && ec.VerifyHash(digest, signature, DSASignatureFormat.Rfc3279DerSequence);
    }
    if (!valid) throw new InvalidDataException("The extension signature is invalid.");
    return new(offset, Convert.ToBase64String(key), expectedId);
   }
   throw new InvalidDataException("The package has no matching developer signature.");
  }
  catch (CryptographicException ex) { throw new InvalidDataException("The extension signature could not be verified.", ex); }
 }

 static byte[] IdBytes(string id)
 {
  var bytes = new byte[16];
  for (int i = 0; i < 16; i++) bytes[i] = (byte)((id[i * 2] - 'a') * 16 + id[i * 2 + 1] - 'a');
  return bytes;
 }
 static ReadOnlyMemory<byte> One(List<Field> fields, int number)
 {
  var matches = fields.Where(f => f.Number == number).ToArray();
  if (matches.Length != 1) throw new InvalidDataException("Missing or duplicate extension header field.");
  return matches[0].Data;
 }
 static List<Field> Fields(ReadOnlyMemory<byte> data)
 {
  var fields = new List<Field>(); int at = 0;
  while (at < data.Length)
  {
   ulong tag = Varint(data.Span, ref at); ulong number = tag >> 3;
   if (number is 0 or > 536870911 || fields.Count > 1024) throw new InvalidDataException("Invalid extension header field.");
   int length;
   switch (tag & 7)
   {
    case 0: _ = Varint(data.Span, ref at); continue;
    case 1: length = 8; break;
    case 5: length = 4; break;
    case 2:
     ulong size = Varint(data.Span, ref at);
     if (size > (ulong)(data.Length - at)) throw new InvalidDataException("Truncated extension header.");
     length = (int)size; break;
    default: throw new InvalidDataException("Unsupported extension header field.");
   }
   if (length > data.Length - at) throw new InvalidDataException("Truncated extension header.");
   if ((tag & 7) == 2) fields.Add(new((int)number, data.Slice(at, length)));
   at += length;
  }
  return fields;
 }
 static ulong Varint(ReadOnlySpan<byte> bytes, ref int at)
 {
  ulong value = 0;
  for (int shift = 0; shift < 64 && at < bytes.Length; shift += 7)
  {
   byte next = bytes[at++];
   if (shift == 63 && next > 1) break;
   value |= (ulong)(next & 127) << shift;
   if ((next & 128) == 0) return value;
  }
  throw new InvalidDataException("Invalid extension header encoding.");
 }
}
