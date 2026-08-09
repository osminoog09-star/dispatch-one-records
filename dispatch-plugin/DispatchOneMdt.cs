// DispatchOne MDT bridge — плагин RagePluginHook/LSPDFR.
// Ловит РАНТАЙМ-данные, которых нет в файлах игры:
//   * проверку человека (OnPedCheck)  -> документ NPC
//   * проверку машины (OnPlateCheck)  -> транспорт (какую проверял/за какой гнался)
//   * статус смены (OnOnDutyStateChanged) -> смена по диспетчеру
// Пишет строки JSONL в <LSPDFR>\DispatchOne\mdt.jsonl (append — без гонок).
// Агент pdcomp_sync читает их и шлёт на сайт.
using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using Rage;
using LSPD_First_Response.Mod.API;   // Functions (статус смены)
using CI = CalloutInterfaceAPI;       // CI.Events (проверки ped/plate)
using CalloutInterfaceAPI.Records;    // PedRecord, VehicleRecord

// RagePluginHook распознаёт сборку-плагин по этому атрибуту (как у рабочих плагинов LSPDFR).
[assembly: Rage.Attributes.Plugin("DispatchOne MDT",
    Description = "Синхронизация проверок ped/plate и статуса смены для LAPD Records.",
    Author = "LAPD Records")]

namespace DispatchOne
{
    // ВАЖНО: базовый класс — LSPDFR-шный Plugin, НЕ Rage.Plugin (тот в реальном RPH sealed,
    // от него нельзя наследоваться → плагин не грузился, TypeLoadException).
    public class DispatchOneMdt : LSPD_First_Response.Mod.API.Plugin
    {
        private static string _outFile;

        public override void Initialize()
        {
            try
            {
                string dir = Path.Combine(PluginFolder(), "DispatchOne");
                Directory.CreateDirectory(dir);
                _outFile = Path.Combine(dir, "mdt.jsonl");

                CI.Events.OnPedCheck += OnPedCheck;
                CI.Events.OnPlateCheck += OnPlateCheck;
                Functions.OnOnDutyStateChanged += OnDutyStateChanged;

                Write("{\"type\":\"boot\",\"ts\":\"" + NowIso() + "\"}");
                Game.LogTrivial("[DispatchOne.MDT] Загружен. Пишу в: " + _outFile);
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[DispatchOne.MDT] Ошибка Initialize: " + ex);
            }
        }

        public override void Finally()
        {
            try
            {
                CI.Events.OnPedCheck -= OnPedCheck;
                CI.Events.OnPlateCheck -= OnPlateCheck;
                Functions.OnOnDutyStateChanged -= OnDutyStateChanged;
                Game.LogTrivial("[DispatchOne.MDT] Выгружен.");
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[DispatchOne.MDT] Ошибка Finally: " + ex);
            }
        }

        // --- проверка человека: документ NPC ---
        private static void OnPedCheck(PedRecord r, string source)
        {
            try
            {
                var sb = new StringBuilder();
                sb.Append("{\"type\":\"ped\",\"ts\":\"").Append(NowIso()).Append("\"");
                J(sb, "source", source);
                J(sb, "first", r.First);
                J(sb, "last", r.Last);
                J(sb, "dob", r.Birthday.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
                Jb(sb, "male", r.IsMale);
                Jb(sb, "wanted", r.IsWanted);
                J(sb, "license", r.LicenseState.ToString());
                Ji(sb, "citations", r.Citations);
                J(sb, "advisory", r.Advisory);
                sb.Append("}");
                Write(sb.ToString());
                Game.LogTrivial("[DispatchOne.MDT] ped: " + r.First + " " + r.Last);
            }
            catch (Exception ex) { Game.LogTrivial("[DispatchOne.MDT] ped err: " + ex.Message); }
        }

        // --- проверка машины: транспорт ---
        private static void OnPlateCheck(VehicleRecord r, string source)
        {
            try
            {
                var sb = new StringBuilder();
                sb.Append("{\"type\":\"plate\",\"ts\":\"").Append(NowIso()).Append("\"");
                J(sb, "source", source);
                J(sb, "plate", r.LicensePlate);
                J(sb, "make", r.Make);
                J(sb, "model", r.Model);
                J(sb, "color", r.Color);
                J(sb, "class", r.Class);
                J(sb, "owner", r.OwnerName);
                J(sb, "insurance", r.InsuranceStatus.ToString());
                J(sb, "registration", r.RegistrationStatus.ToString());
                sb.Append("}");
                Write(sb.ToString());
                Game.LogTrivial("[DispatchOne.MDT] plate: " + r.LicensePlate);
            }
            catch (Exception ex) { Game.LogTrivial("[DispatchOne.MDT] plate err: " + ex.Message); }
        }

        // --- статус смены ---
        private static void OnDutyStateChanged(bool onDuty)
        {
            try
            {
                Write("{\"type\":\"duty\",\"onDuty\":" + (onDuty ? "true" : "false") +
                      ",\"ts\":\"" + NowIso() + "\"}");
                Game.LogTrivial("[DispatchOne.MDT] duty: " + (onDuty ? "НА СМЕНЕ" : "сошёл со смены"));
            }
            catch (Exception ex) { Game.LogTrivial("[DispatchOne.MDT] duty err: " + ex.Message); }
        }

        // --- утилиты ---
        private static void Write(string line)
        {
            if (_outFile == null) return;
            File.AppendAllText(_outFile, line + "\n", new UTF8Encoding(false));
        }

        private static string PluginFolder()
        {
            // LSPDFR грузит плагин ИЗ ПАМЯТИ, поэтому Assembly.Location пустой
            // (и Path.GetDirectoryName падал с ArgumentException). Пишем в
            // <корень игры>\plugins\LSPDFR — рабочая папка процесса = корень GTA V.
            string baseDir = Directory.GetCurrentDirectory();
            string p = Path.Combine(baseDir, "plugins", "LSPDFR");
            if (!Directory.Exists(p))
            {
                // запасной вариант: рядом со сборкой, если Location всё же доступен
                try
                {
                    string loc = Assembly.GetExecutingAssembly().Location;
                    if (!string.IsNullOrEmpty(loc))
                        return Path.GetDirectoryName(loc);
                }
                catch { }
            }
            return p;
        }

        private static string NowIso()
        {
            return DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);
        }

        private static void J(StringBuilder sb, string k, string v)
        {
            sb.Append(",\"").Append(k).Append("\":\"").Append(Esc(v)).Append("\"");
        }
        private static void Jb(StringBuilder sb, string k, bool v)
        {
            sb.Append(",\"").Append(k).Append("\":").Append(v ? "true" : "false");
        }
        private static void Ji(StringBuilder sb, string k, int v)
        {
            sb.Append(",\"").Append(k).Append("\":").Append(v.ToString(CultureInfo.InvariantCulture));
        }
        private static string Esc(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length + 8);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                        else sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }
    }
}
