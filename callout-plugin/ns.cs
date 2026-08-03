using System;
using System.IO;
using System.Reflection;
using System.Linq;

class NS {
  const string G = @"C:\Program Files\Rockstar Games\Grand Theft Auto V Legacy";

  static Assembly Res(object s, ResolveEventArgs e) {
    string n = new AssemblyName(e.Name).Name;
    foreach (var p in new[] { Path.Combine(G, n + ".exe"), Path.Combine(G, n + ".dll"),
                              Path.Combine(G, "plugins", n + ".dll") })
      if (File.Exists(p)) return Assembly.LoadFrom(p);
    return null;
  }

  static void Main() {
    AppDomain.CurrentDomain.AssemblyResolve += Res;
    var a = Assembly.LoadFrom(Path.Combine(G, "RAGEPluginHook.exe"));
    Type[] types;
    try { types = a.GetExportedTypes(); }
    catch (ReflectionTypeLoadException ex) { types = ex.Types.Where(t => t != null).ToArray(); }
    var rage = types.Where(t => t != null && t.Namespace == "Rage").Select(t => t.Name).OrderBy(x => x).ToList();
    Console.WriteLine("публичных типов в namespace Rage: " + rage.Count);
    foreach (var n in rage.Take(40)) Console.WriteLine("  " + n);
    Console.WriteLine("Game есть: " + rage.Contains("Game"));
    Console.WriteLine("World есть: " + rage.Contains("World"));
    Console.WriteLine("LHandle есть: " + rage.Contains("LHandle"));
    Console.WriteLine("Vector3 есть: " + rage.Contains("Vector3"));
  }
}
