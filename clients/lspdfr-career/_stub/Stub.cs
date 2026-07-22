// Компиляционная заглушка API RagePluginHook — ТОЛЬКО для проверки сборки нашего кода.
// В игре используется настоящая сборка. Здесь лишь поверхность, которую мы вызываем.
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
}
