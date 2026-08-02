using System;
using System.IO;
using System.Reflection;

class Dump {
  const string GDIR = @"C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy";

  static Assembly Resolve(object s, ResolveEventArgs e) {
    string n = new AssemblyName(e.Name).Name;
    string[] cands = {
      Path.Combine(GDIR, n + ".exe"),
      Path.Combine(GDIR, n + ".dll"),
      Path.Combine(GDIR, "plugins", n + ".dll"),
      Path.Combine(GDIR, "plugins", "LSPDFR", n + ".dll")
    };
    foreach (var p in cands) if (File.Exists(p)) return Assembly.LoadFrom(p);
    return null;
  }

  static void Main() {
    AppDomain.CurrentDomain.AssemblyResolve += Resolve;
    var lspdfr = Assembly.LoadFrom(Path.Combine(GDIR, "plugins", "LSPD First Response.dll"));
    var fn = lspdfr.GetType("LSPD_First_Response.Mod.API.Functions");

    Console.WriteLine("=== ALL events on Functions ===");
    foreach (var e in fn.GetEvents(BindingFlags.Public|BindingFlags.Static))
      Console.WriteLine("  " + e.Name + " : " + e.EventHandlerType.Name);

    Console.WriteLine("=== Zone/Location methods ===");
    foreach (var m in fn.GetMethods(BindingFlags.Public|BindingFlags.Static)) {
      if (m.Name.Contains("Zone") || m.Name.Contains("Street") || m.Name.Contains("Area")
          || m.Name.Contains("Region") || m.Name.Contains("Location"))
        Console.WriteLine("  " + m.ReturnType.Name + " " + m.Name);
    }
  }
}
