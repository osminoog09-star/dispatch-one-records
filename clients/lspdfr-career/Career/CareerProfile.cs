using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json;
using Rage;

namespace DispatchOne.Career
{
    /// <summary>Профиль карьеры офицера. Сохраняется в %APPDATA%\DispatchOne\career\profiles\.</summary>
    public class CareerProfile
    {
        public string Name = "Officer_1";
        public string Agency = "lspd";
        public string Created = DateTime.UtcNow.ToString("o");

        public RankState Rank = new RankState();
        public CareerTotals Totals = new CareerTotals();
        public List<ShiftRecord> History = new List<ShiftRecord>();

        [JsonIgnore]
        public string FilePath { get; private set; }

        public static string ProfilesDir =>
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                         "DispatchOne", "career", "profiles");

        public static CareerProfile LoadOrCreate(string profileName)
        {
            string dir = ProfilesDir;
            Directory.CreateDirectory(dir);
            string path = Path.Combine(dir, profileName + ".json");

            CareerProfile profile;
            if (File.Exists(path))
            {
                try
                {
                    profile = JsonConvert.DeserializeObject<CareerProfile>(File.ReadAllText(path))
                              ?? new CareerProfile { Name = profileName };
                }
                catch (Exception ex)
                {
                    Game.LogTrivial("[DispatchOne.Career] Профиль повреждён, создаю новый: " + ex.Message);
                    profile = new CareerProfile { Name = profileName };
                }
            }
            else
            {
                profile = new CareerProfile { Name = profileName };
            }

            profile.FilePath = path;
            profile.Save();
            return profile;
        }

        public void Save()
        {
            try
            {
                if (string.IsNullOrEmpty(FilePath))
                    FilePath = Path.Combine(ProfilesDir, Name + ".json");
                Directory.CreateDirectory(Path.GetDirectoryName(FilePath));
                File.WriteAllText(FilePath, JsonConvert.SerializeObject(this, Formatting.Indented));
            }
            catch (Exception ex)
            {
                Game.LogTrivial("[DispatchOne.Career] Ошибка сохранения профиля: " + ex.Message);
            }
        }
    }

    public class RankState
    {
        public int Id = 1;
        public string Name = "Кадет";
        public long Xp = 0;
    }

    public class CareerTotals
    {
        public int Shifts = 0;
        public int DaysWorked = 0;
        public long SecondsOnDuty = 0;
        public int Arrests = 0;
        public int TrafficStops = 0;
        public int CalloutsCompleted = 0;
        public int Pursuits = 0;
    }

    public class ShiftRecord
    {
        public int Number;
        public string Type;         // day | evening | night
        public string Started;      // ISO-время
        public int DurationMinutes;
        public int Arrests;
        public int Stops;
        public int Callouts;
        public int Pursuits;
        public long XpGained;
    }
}
