using System;
using System.Collections.Generic;
using System.IO;
using Rage;

namespace DispatchOne.Career
{
    /// <summary>
    /// Чтение настроек из plugins\LSPDFR\DispatchOne.Career.ini.
    /// Свой минимальный INI-парсер — чтобы не зависеть от версий API чтения конфигов.
    /// </summary>
    public class CareerConfig
    {
        public string Profile = "Officer_1";
        public int DayStart = 6;      // час начала «дневной» смены
        public int EveningStart = 18; // час начала «вечерней»
        public int NightStart = 23;   // час начала «ночной»
        public bool ShowNotifications = true;

        private const string RelPath = @"plugins\LSPDFR\DispatchOne.Career.ini";

        public static CareerConfig Load()
        {
            var cfg = new CareerConfig();
            try
            {
                if (File.Exists(RelPath))
                {
                    var ini = ParseIni(RelPath);
                    cfg.Profile = GetString(ini, "Career", "Profile", cfg.Profile);
                    cfg.DayStart = GetInt(ini, "Career", "ShiftDayStart", cfg.DayStart);
                    cfg.EveningStart = GetInt(ini, "Career", "ShiftEveningStart", cfg.EveningStart);
                    cfg.NightStart = GetInt(ini, "Career", "ShiftNightStart", cfg.NightStart);
                    cfg.ShowNotifications = GetBool(ini, "UI", "ShowNotifications", cfg.ShowNotifications);
                }
                else
                {
                    Game.LogTrivial("[DispatchOne.Career] INI не найден, используются значения по умолчанию.");
                }
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[DispatchOne.Career] Ошибка чтения INI: " + ex.Message);
            }
            return cfg;
        }

        // section -> (key -> value)
        private static Dictionary<string, Dictionary<string, string>> ParseIni(string path)
        {
            var data = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
            string section = "";
            data[section] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

            foreach (var raw in File.ReadAllLines(path))
            {
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith(";") || line.StartsWith("//") || line.StartsWith("#"))
                    continue;

                if (line.StartsWith("[") && line.EndsWith("]"))
                {
                    section = line.Substring(1, line.Length - 2).Trim();
                    if (!data.ContainsKey(section))
                        data[section] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                    continue;
                }

                int eq = line.IndexOf('=');
                if (eq <= 0) continue;
                string key = line.Substring(0, eq).Trim();
                string val = line.Substring(eq + 1).Trim().Trim('"');
                data[section][key] = val;
            }
            return data;
        }

        private static string GetString(Dictionary<string, Dictionary<string, string>> d, string sec, string key, string def)
            => d.TryGetValue(sec, out var s) && s.TryGetValue(key, out var v) ? v : def;

        private static int GetInt(Dictionary<string, Dictionary<string, string>> d, string sec, string key, int def)
            => int.TryParse(GetString(d, sec, key, def.ToString()), out var v) ? v : def;

        private static bool GetBool(Dictionary<string, Dictionary<string, string>> d, string sec, string key, bool def)
            => bool.TryParse(GetString(d, sec, key, def.ToString()), out var v) ? v : def;
    }
}
