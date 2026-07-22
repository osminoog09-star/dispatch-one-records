using System;
using Rage;

namespace DispatchOne.Career
{
    /// <summary>
    /// Жизненный цикл смены: старт (номер, тип по игровому времени), стоп (длительность, отчёт, сохранение).
    /// Веха 1: считаем смены, дни, стаж, тип смены. Статистика внутри смены — Веха 2 (poll-движок).
    /// </summary>
    public class ShiftManager
    {
        private readonly CareerProfile _profile;
        private readonly CareerConfig _config;

        private DateTime _shiftStartUtc;
        private ShiftRecord _current;

        public bool IsOnShift => _current != null;

        public ShiftManager(CareerProfile profile, CareerConfig config)
        {
            _profile = profile;
            _config = config;
        }

        public void StartShift()
        {
            if (IsOnShift) return;

            _shiftStartUtc = DateTime.UtcNow;
            int number = _profile.Totals.Shifts + 1;
            string type = DetermineShiftType();

            _current = new ShiftRecord
            {
                Number = number,
                Type = type,
                Started = _shiftStartUtc.ToString("o")
            };

            string typeRu = ShiftTypeRu(type);
            Game.LogTrivial($"[DispatchOne.Career] Начата смена №{number} ({typeRu}). Звание: {_profile.Rank.Name}.");
            Notify($"~b~Dispatch One~w~~n~Смена №{number} · {typeRu}~n~{_profile.Rank.Name}");
        }

        public void EndShift()
        {
            if (!IsOnShift) return;

            int minutes = (int)Math.Max(0, (DateTime.UtcNow - _shiftStartUtc).TotalMinutes);
            _current.DurationMinutes = minutes;

            // Итоги смены (в Вехе 1 статистика нулевая; заполнится в Вехе 2)
            _profile.Totals.Shifts += 1;
            _profile.Totals.DaysWorked += 1;
            _profile.Totals.SecondsOnDuty += minutes * 60L;

            _profile.History.Add(_current);
            TrimHistory();
            _profile.Save();

            Game.LogTrivial(
                $"[DispatchOne.Career] Смена №{_current.Number} завершена. " +
                $"Длительность: {minutes} мин. Всего смен: {_profile.Totals.Shifts}.");
            Notify($"~b~Dispatch One~w~~n~Смена №{_current.Number} завершена~n~{minutes} мин · всего смен: {_profile.Totals.Shifts}");

            _current = null;
        }

        private string DetermineShiftType()
        {
            int hour;
            try { hour = (int)World.TimeOfDay.Hours; }   // игровое время
            catch { hour = DateTime.Now.Hour; }          // на всякий случай — реальное

            if (hour >= _config.NightStart || hour < _config.DayStart) return "night";
            if (hour >= _config.EveningStart) return "evening";
            return "day";
        }

        private static string ShiftTypeRu(string type)
        {
            switch (type)
            {
                case "night": return "ночная";
                case "evening": return "вечерняя";
                default: return "дневная";
            }
        }

        private void TrimHistory(int keep = 30)
        {
            if (_profile.History.Count > keep)
                _profile.History.RemoveRange(0, _profile.History.Count - keep);
        }

        private void Notify(string msg)
        {
            if (!_config.ShowNotifications) return;
            try { Game.DisplayNotification(msg); } catch { /* HUD может быть недоступен */ }
        }
    }
}
