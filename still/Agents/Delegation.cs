namespace Still;

/// A companion helping a teammate (ask_companion, tell_companion) never gets more room than whoever asked it: per site and
/// action, the strictest rule anyone up the chain has wins, and an approval is the user's chat's to give. (Mac: Ai.swift, strictest)
public static class Delegation
{
 static int Rank(string mode) => mode switch { "always" => 0, "chat" => 1, _ => 2 };
 public static string Strictest(IEnumerable<string> modes) => modes.Select(m => m is "always" or "chat" ? m : "ask").MaxBy(Rank) ?? "ask"; // anything unknown asks
}
