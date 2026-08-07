// Компиляционная заглушка RagePluginHook — ТОЛЬКО поверхность, которую мы вызываем.
// В игре подменяется настоящей сборкой (имя сборки должно быть RagePluginHook).
// Типы Ped/Vehicle/Entity нужны, чтобы компилятор смог загрузить метаданные
// CalloutInterface (PedRecord : EntityRecord<Rage.Ped> и т.д.).
using System;

namespace Rage
{
    public abstract class Plugin
    {
        public virtual void Initialize() { }
        public virtual void Finally() { }
    }

    public static class Game
    {
        public static void LogTrivial(string message) { }
        public static void DisplayNotification(string text) { }
    }

    public static class World
    {
        public static TimeSpan TimeOfDay { get; set; }
    }

    public class Entity { }
    public class Ped : Entity { }
    public class Vehicle : Entity { }

    public struct Vector3 { public float X, Y, Z; }
    public enum LicensePlateStyle { }
}

namespace Rage.Attributes
{
    // Атрибут сборки-плагина RagePluginHook. В игре подменяется настоящим типом.
    [AttributeUsage(AttributeTargets.Assembly, AllowMultiple = false)]
    public sealed class PluginAttribute : Attribute
    {
        public PluginAttribute(string name) { Name = name; }
        public string Name { get; private set; }
        public string Description { get; set; }
        public string Author { get; set; }
        public bool PrefersRawInput { get; set; }
        public bool ShouldTickInPauseMenu { get; set; }
        public bool ShouldTickInEntryPoint { get; set; }
        public string SupportUrl { get; set; }
    }
}
