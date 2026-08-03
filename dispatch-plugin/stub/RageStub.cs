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
