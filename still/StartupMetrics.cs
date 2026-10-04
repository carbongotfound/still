using System.Diagnostics;

namespace Still;

internal static class StartupMetrics
{
#if STILL_QA
 static readonly Stopwatch Clock = Stopwatch.StartNew();
 internal static readonly Dictionary<string, double> Timings = [];
#endif
 [Conditional("STILL_QA")]
 internal static void Mark(string name)
 {
#if STILL_QA
  Timings.TryAdd(name, Math.Round(Clock.Elapsed.TotalSeconds, 3));
#endif
 }
}
