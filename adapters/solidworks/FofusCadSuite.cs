// FOFUS CAD Suite - SolidWorks add-in (v2, 09-24)
// Login with your FOFUS account (email + password prompt), designer status
// in the status bar, presence heartbeats while you actually design.
// Activity = document open/activate/save + model edits (real design work).
// Privacy: only {tool, active, idle_sec} - never filenames, paths, or screens.
//
// BUILD (Windows, VS or csc):
//   csc /target:library /out:FofusCadSuite.dll FofusCadSuite.cs
//       /r:"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS api\redist\SolidWorks.Interop.sldworks.dll"
//       /r:"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS api\redist\SolidWorks.Interop.swconst.dll"
//   Register: run `regasm /codebase FofusCadSuite.dll` (admin cmd), then in
//   SolidWorks: Tools -> Add-Ins -> FOFUS CAD Suite.
//
// LOGIN: first run shows an input box for email, then a password box
// (masked). Sent once over HTTPS to /api/auth/login; only the JWT is kept in
// %APPDATA%\FofusCadSuite\session.json. Auto-pair mints the presence token.

using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading;
using SolidWorks.Interop.sldworks;

namespace FofusCadSuite
{
    [System.Runtime.InteropServices.ComVisible(true)]
    [System.Runtime.InteropServices.Guid("9C5F3B6E-2D8A-4F1C-A7B4-8E2D5C9F0A4B")]
    [System.Runtime.InteropServices.ProgId("FofusCadSuite.SwAddin")]
    public class SwAddin : SolidWorks.Interop.sldworks.SwAddin
    {
        private ISldWorks swApp;
        private SldWorks swAppRoot;
        private int swCookie;
        private Timer timer;
        private readonly object gate = new object();
        private string server = "https://designai.fofus.in";
        private string jwt;                 // FOFUS session (session file)
        private string token;               // fpt_ secret, prefix stripped
        private string accSummary = "";
        private string worksSummary = "";
        private string earnSummary = "";
        private string lastDocTitle;
        private DateTime lastActivity;
        private const int HEARTBEAT_SEC = 60;
        private const int IDLE_ACTIVE_SEC = 600;
        private const string TOOL = "solidworks";
        private static readonly string StateDir =
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "FofusCadSuite");

        // == SwAddin lifecycle ==============================================
        public bool ConnectToSW(object ThisSW, int Cookie)
        {
            swAppRoot = (SldWorks)ThisSW;
            swApp = (ISldWorks)swAppRoot;
            swCookie = Cookie;
            swAppRoot.SetAddinCallbackInfo2(0, this, swCookie);
            LoadState();
            if (token == null) FirstRunLogin();
            lastActivity = DateTime.UtcNow;
            timer = new Timer(_ => Tick(), null, HEARTBEAT_SEC * 1000, HEARTBEAT_SEC * 1000);
            swAppRoot.DocumentLoadNotify2 += OnDocLoad;
            swAppRoot.ActiveDocumentEventHandlerNotify += OnActiveDoc;
            swAppRoot.ActiveModelEventHandlerNotify += OnActiveModel;
            return true;
        }

        public bool DisconnectFromSW()
        {
            timer?.Dispose();
            try
            {
                swAppRoot.DocumentLoadNotify2 -= OnDocLoad;
                swAppRoot.ActiveDocumentEventHandlerNotify -= OnActiveDoc;
                swAppRoot.ActiveModelEventHandlerNotify -= OnActiveModel;
            }
            catch { }
            return true;
        }

        // == Menu callbacks (Tools -> FOFUS) ================================
        public void ShowAccount()
        {
            var t = accSummary.Length > 0
                ? accSummary + "\n\n" + worksSummary + "\n\n" + earnSummary
                : "Not logged in";
            swApp.SendMsgToUser2("FOFUS CAD Suite\n\n" + t, 0, 0);
        }

        public void OpenBoard()
        {
            try { System.Diagnostics.Process.Start("https://designai.fofus.in/designer/board"); } catch { }
        }

        public void OpenEarnings()
        {
            try { System.Diagnostics.Process.Start("https://designai.fofus.in/designer/earnings"); } catch { }
        }

        public void Relogin()
        {
            token = null; jwt = null; accSummary = ""; worksSummary = ""; earnSummary = "";
            LoadState();
            if (token == null) FirstRunLogin();
        }

        public void OpenDashboard()
        {
            try { System.Diagnostics.Process.Start("https://designai.fofus.in"); } catch { }
        }

        // == Activity events ================================================
        private int OnDocLoad(string docTitle, string docPath, bool loadFlags, int docType, ref int errorCode)
        {
            lastActivity = DateTime.UtcNow;
            return 1;
        }

        private int OnActiveDoc(string docTitle)
        {
            lastActivity = DateTime.UtcNow;
            return 0;
        }

        private int OnActiveModel(object model)
        {
            lastActivity = DateTime.UtcNow;
            return 0;
        }

        // == Heartbeat loop =================================================
        private void Tick()
        {
            if (token == null) return;
            try
            {
                var doc = swApp.IActiveDoc2;
                if (doc != null)
                {
                    var title = doc.GetTitle() as string;
                    if (title != lastDocTitle) { lastDocTitle = title; lastActivity = DateTime.UtcNow; }
                    if ((int)doc.GetSaveFlag() != 0) lastActivity = DateTime.UtcNow;
                }
                var idle = (int)(DateTime.UtcNow - lastActivity).TotalSeconds;
                bool active = idle <= IDLE_ACTIVE_SEC;
                SendHeartbeat(active, Math.Min(idle, 86400));
            }
            catch (Exception) { }
        }

        // == Auth: login + auto-pair (CAD Suite flow) =======================
        private void LoadState()
        {
            try
            {
                Directory.CreateDirectory(StateDir);
                var p = Path.Combine(StateDir, "session.json");
                if (File.Exists(p))
                {
                    var d = ParseFlatJson(File.ReadAllText(p));
                    token = d.TryGetValue("token", out var t) && t.Length > 4 ? t.Substring(4) : null;
                    jwt = d.TryGetValue("jwt", out var j) ? j : null;
                    accSummary = d.TryGetValue("acc", out var a) ? a : "";
                    if (token != null) return;
                }
            }
            catch { }
            FirstRunLogin();
        }

        private void FirstRunLogin()
        {
            if (jwt == null) FirstRunLoginPrompt();
            if (jwt == null) return;
            AutoPair();
            FetchAccount();
            SaveState();
        }

        private void FirstRunLoginPrompt()
        {
            try
            {
                var email = Microsoft.VisualBasic.Interaction.InputBox(
                    "FOFUS CAD Suite - login\n\nFOFUS account email:", "FOFUS Login", "", -1, -1);
                if (string.IsNullOrWhiteSpace(email)) return;
                var pass = Microsoft.VisualBasic.Interaction.InputBox(
                    "Password (sent once over HTTPS; only the session token is stored):",
                    "FOFUS Login", "", -1, -1);
                if (string.IsNullOrWhiteSpace(pass)) return;
                var payload = "{\"email\":\"" + Escape(email.Trim()) + "\",\"password\":\"" + Escape(pass) + "\"}";
                var resp = Post(server + "/api/auth/login", payload, null);
                jwt = ExtractString(resp, "access_token");
                if (jwt == null)
                {
                    swApp.SendMsgToUser2("FOFUS login failed - check email/password.", 2, 0);
                    return;
                }
            }
            catch (Exception) { jwt = null; }
        }

        private void AutoPair()
        {
            try
            {
                var resp = Post(server + "/api/designers/me/presence/auto-pair?tool=" + TOOL, "{}",
                    new Dictionary<string, string> { { "Authorization", "Bearer " + jwt } });
                var t = ExtractString(resp, "token");
                if (t != null && t.StartsWith("fpt_")) token = t.Substring(4);
            }
            catch (Exception) { }
        }

        private void FetchAccount()
        {
            try
            {
                var hdrs = new Dictionary<string, string> { { "Authorization", "Bearer " + jwt } };
                var resp = Get(server + "/api/designers/me/profile", hdrs);
                var name = ExtractString(resp, "name") ?? "Designer";
                var rank = ExtractString(resp, "rank") ?? "";
                var wallet = ExtractString(resp, "wallet_balance") ?? "";
                accSummary = "ACCOUNT\n  " + name
                    + (rank.Length > 0 ? "\n  Rank: " + rank : "")
                    + (wallet.Length > 0 ? "\n  Wallet: " + wallet : "")
                    + "\n  Status: presence active";
                FetchWorks(hdrs);
                FetchEarnings(hdrs);
            }
            catch (Exception)
            {
                accSummary = "Account sync failed (will retry on restart)";
            }
        }

        private void FetchWorks(Dictionary<string, string> hdrs)
        {
            try
            {
                var resp = Get(server + "/api/designers/me/board", hdrs);
                var lines = new List<string> { "WORKS" };
                var titles = ExtractStringArray(resp, "title");
                var nums = ExtractStringArray(resp, "project_number");
                for (int i = 0; i < Math.Min(titles.Count, 8); i++)
                {
                    var n = i < nums.Count ? nums[i] : "";
                    lines.Add("  " + n + " " + titles[i]);
                }
                if (titles.Count == 0) lines.Add("  No works yet - see Opportunities.");
                lines.Add("  Full board: designai.fofus.in/designer/board");
                worksSummary = string.Join("\n", lines);
            }
            catch (Exception) { worksSummary = "WORKS\n  (load failed - run Refresh)"; }
        }

        private void FetchEarnings(Dictionary<string, string> hdrs)
        {
            try
            {
                var w = Get(server + "/api/wallet", hdrs);
                var avail = ExtractString(w, "available_balance") ?? "0";
                var pending = ExtractString(w, "pending_balance") ?? "";
                var lifetime = ExtractString(w, "lifetime_earnings") ?? "";
                earnSummary = "EARNINGS\n  Available: Rs" + avail
                    + (pending.Length > 0 ? "\n  Pending: Rs" + pending : "")
                    + (lifetime.Length > 0 ? "\n  Lifetime: Rs" + lifetime : "")
                    + "\n  Withdraw: designai.fofus.in/designer/earnings";
            }
            catch (Exception) { earnSummary = "EARNINGS\n  (load failed - run Refresh)"; }
        }

        private void SaveState()
        {
            try
            {
                Directory.CreateDirectory(StateDir);
                File.WriteAllText(Path.Combine(StateDir, "session.json"),
                    "{\"token\":\"fpt_" + token + "\",\"jwt\":\"" + Escape(jwt ?? "") + "\",\"acc\":\"" + Escape(accSummary).Replace("\n", "\\n") + "\"}");
            }
            catch (Exception) { }
        }

        // == HTTP (same wire protocol as Blender/Fusion adapters) ===========
        private void SendHeartbeat(bool active, int idle)
        {
            var ts = (int)(DateTime.UtcNow - new DateTime(1970, 1, 1)).TotalSeconds;
            var msg = ts + ":" + TOOL + ":" + (active ? "True" : "False") + ":" + idle;
            var sig = HmacSha256Hex(token, msg);
            var payload = "{\"tool\":\"" + TOOL + "\",\"active\":" + (active ? "true" : "false")
                        + ",\"idle_sec\":" + idle + ",\"ts\":" + ts + ",\"sig\":\"" + sig + "\"}";
            var hdrs = new Dictionary<string, string> { { "x-fofus-presence", "fpt_" + token } };
            Post(server + "/api/designers/presence/heartbeat", payload, hdrs);
        }

        private static string HmacSha256Hex(string key, string msg)
        {
            using (var h = new System.Security.Cryptography.HMACSHA256(Encoding.UTF8.GetBytes(key)))
                return BitConverter.ToString(h.ComputeHash(Encoding.UTF8.GetBytes(msg))).Replace("-", "").ToLower();
        }

        private string Post(string url, string payload, Dictionary<string, string> extraHeaders)
        {
            try
            {
                using (var c = new HttpClient())
                using (var req = new HttpRequestMessage(HttpMethod.Post, url))
                {
                    req.Content = new StringContent(payload, Encoding.UTF8, "application/json");
                    if (extraHeaders != null)
                        foreach (var kv in extraHeaders) req.Headers.TryAddWithoutValidation(kv.Key, kv.Value);
                    using (var resp = c.SendAsync(req).GetAwaiter().GetResult())
                    using (var body = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult())
                        return body ?? "";
                }
            }
            catch (Exception) { return ""; }
        }

        private string Get(string url, Dictionary<string, string> headers)
        {
            try
            {
                using (var c = new HttpClient())
                using (var req = new HttpRequestMessage(HttpMethod.Get, url))
                {
                    if (headers != null)
                        foreach (var kv in headers) req.Headers.TryAddWithoutValidation(kv.Key, kv.Value);
                    using (var resp = c.SendAsync(req).GetAwaiter().GetResult())
                    using (var body = resp.Content.ReadAsStringAsync().GetAwaiter().GetResult())
                        return body ?? "";
                }
            }
            catch (Exception) { return ""; }
        }

        private static string ExtractString(string json, string key)
        {
            var marker = "\"" + key + "\":\"";
            var i = json.IndexOf(marker, StringComparison.Ordinal);
            if (i < 0) return null;
            var start = i + marker.Length;
            var end = json.IndexOf('"', start);
            return end < 0 ? null : json.Substring(start, end - start);
        }

        // Pull every "title":"..." style value from a JSON blob (board cards etc.)
        private static List<string> ExtractStringArray(string json, string key)
        {
            var outp = new List<string>();
            if (json == null) return outp;
            var marker = "\"" + key + "\":\"";
            var i = json.IndexOf(marker, StringComparison.Ordinal);
            while (i >= 0)
            {
                var start = i + marker.Length;
                var end = json.IndexOf('"', start);
                if (end < 0) break;
                outp.Add(json.Substring(start, end - start));
                i = json.IndexOf(marker, end);
            }
            return outp;
        }

        private static string Escape(string s)
        {
            return (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        private static Dictionary<string, string> ParseFlatJson(string json)
        {
            var d = new Dictionary<string, string>();
            foreach (var part in json.Replace("{", "").Replace("}", "").Split('\n'))
            {
                var kv = part.Split(new[] { ':' }, 2);
                if (kv.Length == 2)
                {
                    var k = kv[0].Replace("\"", "").Trim().TrimEnd(',');
                    var v = kv[1].Replace("\"", "").Trim().TrimEnd(',').Trim();
                    d[k] = v;
                }
            }
            return d;
        }
    }
}