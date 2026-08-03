// LAPD Records — плагин логирования вызовов (callouts) для LSPDFR.
// Ловит события вызовов и пишет каждый в JSON, который читает наш агент.
//
// Сборка (см. build.bat):
//   csc /target:library /out:DispatchOneCallouts.dll ...ссылки... CalloutLogger.cs
// Установка: положить DispatchOneCallouts.dll в plugins/LSPDFR/

using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
using Rage;
using LSPD_First_Response.Mod.API;

namespace DispatchOneCallouts
{
    public class Main : Plugin
    {
        // Файл, куда пишем вызовы (рядом с pdComp — агент уже смотрит в эту папку)
        private static readonly string OutFile = Path.Combine(
            "plugins", "LSPDFR", "pdComp", "data", "store", "callouts.json");

        private static readonly object Lock = new object();

        public override void Initialize()
        {
            Functions.OnCalloutDisplayed += OnCalloutDisplayed;
            Functions.OnCalloutAccepted += OnCalloutAccepted;
            Functions.OnCalloutFinished += OnCalloutFinished;
            Game.LogTrivial("DispatchOneCallouts: инициализирован, слежу за вызовами.");
        }

        public override void Finally()
        {
            Functions.OnCalloutDisplayed -= OnCalloutDisplayed;
            Functions.OnCalloutAccepted -= OnCalloutAccepted;
            Functions.OnCalloutFinished -= OnCalloutFinished;
            Game.LogTrivial("DispatchOneCallouts: выгружен.");
        }

        // ─── события вызова ───

        private void OnCalloutDisplayed(LHandle callout)
        {
            SafeWrite(callout, "displayed");
        }

        private void OnCalloutAccepted(LHandle callout)
        {
            SafeWrite(callout, "accepted");
        }

        private void OnCalloutFinished(LHandle callout)
        {
            SafeWrite(callout, "finished");
        }

        // ─── запись ───

        private void SafeWrite(LHandle callout, string state)
        {
            try
            {
                string id = GetCalloutId(callout);
                string name = SafeName(callout);
                Vector3 pos = Game.LocalPlayer.Character.Position;
                string street = World.GetStreetName(pos);
                string zone = Functions.GetZoneAtPosition(pos)?.RealAreaName ?? "";
                string when = DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss");

                var rec = new CalloutRecord
                {
                    Id = id,
                    Name = name,
                    State = state,
                    Street = street,
                    Zone = zone,
                    Time = when,
                };

                lock (Lock)
                {
                    var list = LoadExisting();
                    // обновляем существующий по Id или добавляем
                    int idx = list.FindIndex(r => r.Id == id);
                    if (idx >= 0)
                    {
                        // сохраняем самое раннее время, обновляем статус/место
                        rec.Time = list[idx].Time ?? when;
                        if (state == "finished" && string.IsNullOrEmpty(rec.Street))
                            rec.Street = list[idx].Street;
                        list[idx] = rec;
                    }
                    else
                    {
                        list.Add(rec);
                    }
                    // не даём файлу расти бесконечно — последние 200 вызовов
                    if (list.Count > 200) list.RemoveRange(0, list.Count - 200);
                    Save(list);
                }
            }
            catch (Exception e)
            {
                Game.LogTrivial("DispatchOneCallouts: ошибка записи — " + e.Message);
            }
        }

        private string SafeName(LHandle callout)
        {
            try
            {
                string friendly = Functions.GetCalloutFriendlyName(callout);
                if (!string.IsNullOrEmpty(friendly)) return friendly;
            }
            catch { }
            try { return Functions.GetCalloutName(callout); }
            catch { return "Вызов"; }
        }

        private string GetCalloutId(LHandle callout)
        {
            // стабильный идентификатор вызова на основе handle
            try { return "CO-" + callout.Handle.ToString(); }
            catch { return "CO-" + Guid.NewGuid().ToString("N").Substring(0, 8); }
        }

        // ─── очень лёгкий JSON (без внешних библиотек) ───

        private List<CalloutRecord> LoadExisting()
        {
            var list = new List<CalloutRecord>();
            if (!File.Exists(OutFile)) return list;
            try
            {
                string txt = File.ReadAllText(OutFile, Encoding.UTF8);
                foreach (var obj in SplitObjects(txt))
                {
                    var r = new CalloutRecord
                    {
                        Id = JsonGet(obj, "Id"),
                        Name = JsonGet(obj, "Name"),
                        State = JsonGet(obj, "State"),
                        Street = JsonGet(obj, "Street"),
                        Zone = JsonGet(obj, "Zone"),
                        Time = JsonGet(obj, "Time"),
                    };
                    if (!string.IsNullOrEmpty(r.Id)) list.Add(r);
                }
            }
            catch { }
            return list;
        }

        private void Save(List<CalloutRecord> list)
        {
            var sb = new StringBuilder();
            sb.Append("[\n");
            for (int i = 0; i < list.Count; i++)
            {
                var r = list[i];
                sb.Append("  {");
                sb.Append("\"Id\":").Append(JsonStr(r.Id)).Append(",");
                sb.Append("\"Name\":").Append(JsonStr(r.Name)).Append(",");
                sb.Append("\"State\":").Append(JsonStr(r.State)).Append(",");
                sb.Append("\"Street\":").Append(JsonStr(r.Street)).Append(",");
                sb.Append("\"Zone\":").Append(JsonStr(r.Zone)).Append(",");
                sb.Append("\"Time\":").Append(JsonStr(r.Time));
                sb.Append("}");
                if (i < list.Count - 1) sb.Append(",");
                sb.Append("\n");
            }
            sb.Append("]\n");
            var dir = Path.GetDirectoryName(OutFile);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
            File.WriteAllText(OutFile, sb.ToString(), new UTF8Encoding(false));
        }

        private static string JsonStr(string s)
        {
            if (s == null) return "\"\"";
            var sb = new StringBuilder("\"");
            foreach (char c in s)
            {
                if (c == '"' || c == '\\') sb.Append('\\').Append(c);
                else if (c == '\n') sb.Append("\\n");
                else if (c == '\r') { }
                else sb.Append(c);
            }
            sb.Append("\"");
            return sb.ToString();
        }

        private static string JsonGet(string obj, string key)
        {
            string pat = "\"" + key + "\":";
            int i = obj.IndexOf(pat, StringComparison.Ordinal);
            if (i < 0) return "";
            i += pat.Length;
            while (i < obj.Length && obj[i] != '"') i++;
            i++;
            var sb = new StringBuilder();
            while (i < obj.Length && obj[i] != '"')
            {
                if (obj[i] == '\\' && i + 1 < obj.Length) { i++; sb.Append(obj[i]); }
                else sb.Append(obj[i]);
                i++;
            }
            return sb.ToString();
        }

        private static IEnumerable<string> SplitObjects(string txt)
        {
            int depth = 0, start = -1;
            for (int i = 0; i < txt.Length; i++)
            {
                if (txt[i] == '{') { if (depth == 0) start = i; depth++; }
                else if (txt[i] == '}') { depth--; if (depth == 0 && start >= 0) yield return txt.Substring(start, i - start + 1); }
            }
        }

        private class CalloutRecord
        {
            public string Id, Name, State, Street, Zone, Time;
        }
    }
}
