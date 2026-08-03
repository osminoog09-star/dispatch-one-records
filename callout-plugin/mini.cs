using System;
using LSPD_First_Response.Mod.API;
using Rage;

namespace DispatchOneCallouts
{
    public class MiniTest : Plugin
    {
        public override void Initialize()
        {
            Functions.OnCalloutDisplayed += c => { var n = Functions.GetCalloutName(c); };
        }
        public override void Finally() { }
    }
}
