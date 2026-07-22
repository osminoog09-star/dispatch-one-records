using System;
using Rage;
using LSPD_First_Response.Mod.API;

namespace DispatchOne.Career
{
    /// <summary>
    /// Точка входа плагина Dispatch One — Career.
    /// RagePluginHook находит класс, унаследованный от Rage.Plugin, и вызывает Initialize().
    /// Веха 1: грузимся, ловим выход/сход со смены, ведём профиль (номер смены, тип, стаж).
    /// </summary>
    public class EntryPoint : Rage.Plugin
    {
        private static CareerConfig _config;
        private static CareerProfile _profile;
        private static ShiftManager _shift;

        public override void Initialize()
        {
            try
            {
                _config = CareerConfig.Load();
                _profile = CareerProfile.LoadOrCreate(_config.Profile);
                _shift = new ShiftManager(_profile, _config);

                Functions.OnOnDutyStateChanged += OnDutyStateChanged;

                Game.LogTrivial(
                    $"[DispatchOne.Career] Загружен. Профиль='{_profile.Name}' " +
                    $"Звание='{_profile.Rank.Name}' XP={_profile.Rank.Xp} " +
                    $"Смен отработано={_profile.Totals.Shifts}");
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[DispatchOne.Career] Ошибка Initialize: " + ex);
            }
        }

        public override void Finally()
        {
            try
            {
                Functions.OnOnDutyStateChanged -= OnDutyStateChanged;
                if (_shift != null && _shift.IsOnShift)
                    _shift.EndShift();
                Game.LogTrivial("[DispatchOne.Career] Выгружен.");
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[DispatchOne.Career] Ошибка Finally: " + ex);
            }
        }

        private static void OnDutyStateChanged(bool onDuty)
        {
            try
            {
                if (onDuty) _shift.StartShift();
                else _shift.EndShift();
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[DispatchOne.Career] Ошибка OnDuty: " + ex);
            }
        }
    }
}
