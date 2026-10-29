using System.Runtime.InteropServices;
namespace Still;
/// Windows Hello (face, fingerprint or PIN) before a saved password is shown, copied, edited or exported. It calls
/// UserConsentVerifier through its desktop interop, so Still needs no WinRT projection for one dialog.
static class OsAuth
{
 public enum Answer { Verified, Unavailable, Declined }
 static Guid Interop = new("39E050C3-4E74-441A-8DC0-B81104DF949C"); // IUserConsentVerifierInterop
 static Guid Operation = new("FD596FFD-2318-558F-9DBE-D21DF43764A5"); // IAsyncOperation<UserConsentVerificationResult>
 static Guid AsyncInfo = new("00000036-0000-0000-C000-000000000046");
 [DllImport("combase.dll", CharSet = CharSet.Unicode)] static extern int WindowsCreateString(string text, int length, out IntPtr hstring);
 [DllImport("combase.dll")] static extern int WindowsDeleteString(IntPtr hstring);
 [DllImport("combase.dll")] static extern int RoGetActivationFactory(IntPtr classId, ref Guid iid, out IntPtr factory);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int Request(IntPtr self, IntPtr window, IntPtr message, ref Guid iid, out IntPtr operation);
 [UnmanagedFunctionPointer(CallingConvention.StdCall)] delegate int ReadInt(IntPtr self, out int value);
 static T Slot<T>(IntPtr com, int index) where T : Delegate => Marshal.GetDelegateForFunctionPointer<T>(Marshal.ReadIntPtr(Marshal.ReadIntPtr(com), index * IntPtr.Size));

 public static async Task<Answer> Verify(IntPtr window, string message)
 {
  IntPtr name = IntPtr.Zero, text = IntPtr.Zero, factory = IntPtr.Zero, operation = IntPtr.Zero, info = IntPtr.Zero;
  try {
   const string id = "Windows.Security.Credentials.UI.UserConsentVerifier";
   Marshal.ThrowExceptionForHR(WindowsCreateString(id, id.Length, out name));
   Marshal.ThrowExceptionForHR(WindowsCreateString(message, message.Length, out text));
   Marshal.ThrowExceptionForHR(RoGetActivationFactory(name, ref Interop, out factory));
   // IInspectable's 6 slots, then RequestVerificationForWindowAsync.
   Marshal.ThrowExceptionForHR(Slot<Request>(factory, 6)(factory, window, text, ref Operation, out operation));
   Marshal.ThrowExceptionForHR(Marshal.QueryInterface(operation, in AsyncInfo, out info));
   int status;
   while (Slot<ReadInt>(info, 7)(info, out status) >= 0 && status == 0) await Task.Delay(100); // IAsyncInfo.Status: Started
   if (status != 1) return Answer.Declined; // Canceled or Error
   Marshal.ThrowExceptionForHR(Slot<ReadInt>(operation, 8)(operation, out int result)); // IAsyncOperation.GetResults
   // Verified, DeviceNotPresent, NotConfiguredForUser, DisabledByPolicy, DeviceBusy, RetriesExhausted, Canceled
   return result == 0 ? Answer.Verified : result is 1 or 2 or 3 ? Answer.Unavailable : Answer.Declined;
  } catch (Exception ex) when (ex is COMException or EntryPointNotFoundException or DllNotFoundException) {
   App.Log(ex); return Answer.Unavailable;
  } finally {
   foreach (var com in new[] { info, operation, factory }) if (com != IntPtr.Zero) Marshal.Release(com);
   if (text != IntPtr.Zero) WindowsDeleteString(text);
   if (name != IntPtr.Zero) WindowsDeleteString(name);
  }
 }
}
