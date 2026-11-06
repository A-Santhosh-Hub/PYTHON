// Screen Dimmer: darkens the screen below the hardware brightness minimum.
// Written for the C# 5 compiler that ships with Windows (csc.exe v4).
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

namespace ScreenDimmer
{
    internal static class Native
    {
        public const int WM_HOTKEY = 0x0312;
        public const int WM_APP = 0x8000;
        public const int WM_SET_LEVEL = WM_APP + 1;   // wParam = level 0-100
        public const int WM_SHOW_SLIDER = WM_APP + 2;
        public const int WM_QUIT_APP = WM_APP + 3;
        public const int WM_GET_LEVEL = WM_APP + 4;   // returns the level
        public const int WM_GET_ENGINE = WM_APP + 5;  // returns 1 filter, 2 overlay
        public const int WM_SET_ENGINE = WM_APP + 6;  // wParam = 1 filter, 2 overlay

        public const uint MOD_ALT = 0x0001, MOD_CONTROL = 0x0002, MOD_NOREPEAT = 0x4000;
        public const uint VK_PRIOR = 0x21, VK_NEXT = 0x22, VK_HOME = 0x24;

        public const int WS_POPUP = unchecked((int)0x80000000);
        public const int WS_EX_TOPMOST = 0x00000008, WS_EX_TRANSPARENT = 0x00000020,
                         WS_EX_TOOLWINDOW = 0x00000080, WS_EX_LAYERED = 0x00080000,
                         WS_EX_NOACTIVATE = 0x08000000;
        public const uint LWA_ALPHA = 0x2;
        public const uint SWP_NOACTIVATE = 0x0010, SWP_SHOWWINDOW = 0x0040;
        public const int SM_XVIRTUALSCREEN = 76, SM_YVIRTUALSCREEN = 77,
                         SM_CXVIRTUALSCREEN = 78, SM_CYVIRTUALSCREEN = 79;
        public static readonly IntPtr HWND_TOPMOST = new IntPtr(-1);

        [DllImport("user32.dll")] public static extern bool RegisterHotKey(IntPtr hWnd, int id, uint mods, uint vk);
        [DllImport("user32.dll")] public static extern bool UnregisterHotKey(IntPtr hWnd, int id);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
        [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] public static extern bool SetLayeredWindowAttributes(IntPtr h, uint key, byte alpha, uint flags);
        [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
        [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
        [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr h);
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
        [DllImport("user32.dll")] public static extern bool AllowSetForegroundWindow(int processId);

        [DllImport("Magnification.dll")] public static extern bool MagInitialize();
        [DllImport("Magnification.dll")] public static extern bool MagUninitialize();
        [DllImport("Magnification.dll")] public static extern bool MagSetFullscreenColorEffect([In] float[] matrix);
    }

    // ---- Dimming engines ------------------------------------------------

    internal interface IEngine : IDisposable
    {
        bool Apply(int level);
    }

    // Main mode: scales the color of the whole desktop.
    internal sealed class FilterEngine : IEngine
    {
        private bool ready;

        public FilterEngine()
        {
            try { ready = Native.MagInitialize(); }
            catch (DllNotFoundException) { ready = false; }
            catch (EntryPointNotFoundException) { ready = false; }
        }

        public bool Apply(int level)
        {
            if (!ready) return false;
            float k = 1f - level / 100f;
            float[] m = {
                k, 0, 0, 0, 0,
                0, k, 0, 0, 0,
                0, 0, k, 0, 0,
                0, 0, 0, 1, 0,
                0, 0, 0, 0, 1
            };
            return Native.MagSetFullscreenColorEffect(m);
        }

        public void Dispose()
        {
            if (!ready) return;
            Apply(0);
            Native.MagUninitialize();
            ready = false;
        }
    }

    // Backup mode: a click-through black window above everything else.
    internal sealed class OverlayEngine : NativeWindow, IEngine
    {
        public OverlayEngine()
        {
            CreateParams cp = new CreateParams();
            cp.Caption = "ScreenDimmerOverlay";
            cp.Style = Native.WS_POPUP;
            cp.ExStyle = Native.WS_EX_LAYERED | Native.WS_EX_TRANSPARENT | Native.WS_EX_TOPMOST
                       | Native.WS_EX_TOOLWINDOW | Native.WS_EX_NOACTIVATE;
            // The stock black brush paints the window black.
            cp.ClassStyle = 0;
            CreateHandle(cp);
        }

        public bool Apply(int level)
        {
            byte alpha = (byte)Math.Round(level * 255 / 100.0);
            Native.SetLayeredWindowAttributes(Handle, 0, alpha, Native.LWA_ALPHA);
            Refit();
            return true;
        }

        // Covers every monitor, and goes back on top of other topmost windows.
        public void Refit()
        {
            Native.SetWindowPos(Handle, Native.HWND_TOPMOST,
                Native.GetSystemMetrics(Native.SM_XVIRTUALSCREEN),
                Native.GetSystemMetrics(Native.SM_YVIRTUALSCREEN),
                Native.GetSystemMetrics(Native.SM_CXVIRTUALSCREEN),
                Native.GetSystemMetrics(Native.SM_CYVIRTUALSCREEN),
                Native.SWP_NOACTIVATE | Native.SWP_SHOWWINDOW);
        }

        protected override void WndProc(ref Message m)
        {
            const int WM_ERASEBKGND = 0x0014, WM_PAINT = 0x000F;
            if (m.Msg == WM_ERASEBKGND || m.Msg == WM_PAINT)
            {
                using (Graphics g = m.Msg == WM_PAINT ? Graphics.FromHwnd(Handle) : Graphics.FromHdc(m.WParam))
                    g.Clear(Color.Black);
                if (m.Msg == WM_ERASEBKGND) { m.Result = new IntPtr(1); return; }
            }
            base.WndProc(ref m);
        }

        public void Dispose()
        {
            DestroyHandle();
        }
    }

    // ---- Saved settings -------------------------------------------------

    internal static class Settings
    {
        private const string Key = @"Software\ScreenDimmer";
        private const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        public const int StartupCap = 90;

        public static int Level
        {
            get { return Read("Level", 40); }
            set { Write("Level", value); }
        }

        public static bool UseOverlay
        {
            get { return Read("UseOverlay", 0) != 0; }
            set { Write("UseOverlay", value ? 1 : 0); }
        }

        public static bool StartWithWindows
        {
            get
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(RunKey))
                    return k != null && k.GetValue("ScreenDimmer") != null;
            }
            set
            {
                using (RegistryKey k = Registry.CurrentUser.CreateSubKey(RunKey))
                {
                    if (value) k.SetValue("ScreenDimmer", "\"" + Application.ExecutablePath + "\"");
                    else k.DeleteValue("ScreenDimmer", false);
                }
            }
        }

        private static int Read(string name, int fallback)
        {
            using (RegistryKey k = Registry.CurrentUser.OpenSubKey(Key))
            {
                object v = k == null ? null : k.GetValue(name);
                return v is int ? (int)v : fallback;
            }
        }

        private static void Write(string name, int value)
        {
            using (RegistryKey k = Registry.CurrentUser.CreateSubKey(Key))
                k.SetValue(name, value, RegistryValueKind.DWord);
        }
    }

    // ---- Slider popup ---------------------------------------------------

    internal sealed class SliderForm : Form
    {
        private readonly TrackBar bar = new TrackBar();
        private readonly Label label = new Label();
        private readonly Action<int> onChange;
        private readonly System.Windows.Forms.Timer autoHide = new System.Windows.Forms.Timer();
        private bool updating;
        private bool hadFocus;
        private readonly int margin;

        public SliderForm(Action<int> onChange)
        {
            this.onChange = onChange;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            float dpi;
            using (Graphics g = CreateGraphics()) dpi = g.DpiX / 96f;
            Func<int, int> px = delegate(int v) { return (int)Math.Round(v * dpi); };
            margin = px(12);
            ClientSize = new Size(px(320), px(96));
            BackColor = Color.FromArgb(32, 32, 32);
            ForeColor = Color.White;

            label.SetBounds(px(12), px(10), px(296), px(24));
            label.Font = new Font("Segoe UI", 10f);
            label.TextAlign = ContentAlignment.MiddleLeft;

            bar.SetBounds(px(8), px(40), px(304), px(45));
            bar.Minimum = 0;
            bar.Maximum = 100;
            bar.TickFrequency = 10;
            bar.SmallChange = 1;
            bar.LargeChange = 5;
            bar.BackColor = BackColor;
            bar.ValueChanged += delegate
            {
                ShowValue();
                if (!updating) this.onChange(bar.Value);
            };

            Controls.Add(label);
            Controls.Add(bar);

            // Windows can refuse to give this popup focus. It then closes on a
            // timer, not on losing focus, so it can't vanish before you see it.
            Activated += delegate { hadFocus = true; autoHide.Stop(); };
            Deactivate += delegate { if (hadFocus) Hide(); };
            autoHide.Interval = 6000;
            autoHide.Tick += delegate { autoHide.Stop(); Hide(); };

            KeyPreview = true;
            KeyDown += delegate(object s, KeyEventArgs e)
            {
                if (e.KeyCode == Keys.Escape) Hide();
            };
        }

        public void SetValue(int level)
        {
            updating = true;
            bar.Value = level;
            updating = false;
            ShowValue();
        }

        public void Popup()
        {
            // Sits above the tray, in the bottom right corner of the main screen.
            Rectangle area = Screen.PrimaryScreen.WorkingArea;
            Location = new Point(area.Right - Width - margin, area.Bottom - Height - margin);
            hadFocus = false;
            autoHide.Stop();
            autoHide.Start();
            Show();
            Activate();
            Native.SetForegroundWindow(Handle);
            bar.Focus();
        }

        private void ShowValue()
        {
            label.Text = "Extra dimming: " + bar.Value + "%";
        }

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= Native.WS_EX_TOOLWINDOW;
                return cp;
            }
        }
    }

    // ---- Tray app -------------------------------------------------------

    internal sealed class App : NativeWindow, IDisposable
    {
        public const string WindowTitle = "ScreenDimmerControlWindow";
        private const int HotDarker = 1, HotBrighter = 2, HotOff = 3;

        private readonly NotifyIcon tray = new NotifyIcon();
        private readonly SliderForm slider;
        private readonly System.Windows.Forms.Timer keepOnTop = new System.Windows.Forms.Timer();
        private readonly ContextMenuStrip menu = new ContextMenuStrip();
        private ToolStripMenuItem filterItem, overlayItem, startupItem;
        private IEngine engine;
        private IntPtr iconHandle = IntPtr.Zero;
        private int level;
        private int lastNonZero = 40;

        public App(int startLevel)
        {
            CreateParams cp = new CreateParams();
            cp.Caption = WindowTitle;
            CreateHandle(cp);

            slider = new SliderForm(SetLevel);
            BuildMenu();

            tray.ContextMenuStrip = menu;
            UpdateTray();
            tray.Visible = true;
            tray.MouseClick += delegate(object s, MouseEventArgs e)
            {
                if (e.Button == MouseButtons.Left) ShowSlider();
            };

            UseEngine(Settings.UseOverlay);
            SetLevel(startLevel);

            RegisterHotkeys();

            keepOnTop.Interval = 1500;
            keepOnTop.Tick += delegate
            {
                OverlayEngine o = engine as OverlayEngine;
                if (o != null && level > 0) o.Refit();
            };
            keepOnTop.Start();

            SystemEvents.DisplaySettingsChanged += OnSystemChange;
            SystemEvents.SessionSwitch += OnSessionSwitch;
        }

        private void RegisterHotkeys()
        {
            uint mods = Native.MOD_CONTROL | Native.MOD_ALT | Native.MOD_NOREPEAT;
            bool ok = Native.RegisterHotKey(Handle, HotDarker, Native.MOD_CONTROL | Native.MOD_ALT, Native.VK_NEXT);
            ok &= Native.RegisterHotKey(Handle, HotBrighter, Native.MOD_CONTROL | Native.MOD_ALT, Native.VK_PRIOR);
            ok &= Native.RegisterHotKey(Handle, HotOff, mods, Native.VK_HOME);
            if (!ok)
            {
                tray.ShowBalloonTip(5000, "Screen Dimmer",
                    "Another app is using one of the Ctrl+Alt hotkeys. Use the tray icon instead.",
                    ToolTipIcon.Warning);
            }
        }

        private void BuildMenu()
        {
            foreach (int v in new int[] { 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100 })
            {
                int value = v;
                string text = v == 0 ? "Off (0%)" : v == 100 ? "100% (black screen)" : v + "%";
                menu.Items.Add(text, null, delegate { SetLevel(value); });
            }
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Open slider...", null, delegate { ShowSlider(); });
            menu.Items.Add(new ToolStripSeparator());

            filterItem = new ToolStripMenuItem("Mode: full-screen filter", null, delegate { SwitchEngine(false); });
            overlayItem = new ToolStripMenuItem("Mode: overlay window", null, delegate { SwitchEngine(true); });
            startupItem = new ToolStripMenuItem("Start with Windows", null, delegate
            {
                Settings.StartWithWindows = !Settings.StartWithWindows;
                startupItem.Checked = Settings.StartWithWindows;
            });
            startupItem.Checked = Settings.StartWithWindows;
            menu.Items.Add(filterItem);
            menu.Items.Add(overlayItem);
            menu.Items.Add(startupItem);
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("Exit", null, delegate { Application.Exit(); });
        }

        private void ShowSlider()
        {
            slider.SetValue(level);
            slider.Popup();
        }

        private void SwitchEngine(bool overlay)
        {
            UseEngine(overlay);
            engine.Apply(level);
        }

        private void UseEngine(bool overlay)
        {
            if (engine != null) { engine.Dispose(); engine = null; }

            if (!overlay)
            {
                FilterEngine f = new FilterEngine();
                if (f.Apply(0))
                {
                    engine = f;
                }
                else
                {
                    // Falls back when the color filter is unavailable.
                    f.Dispose();
                    overlay = true;
                    tray.ShowBalloonTip(5000, "Screen Dimmer",
                        "The full-screen filter is not available, so overlay mode is on.",
                        ToolTipIcon.Info);
                }
            }
            if (overlay) engine = new OverlayEngine();

            Settings.UseOverlay = overlay;
            filterItem.Checked = !overlay;
            overlayItem.Checked = overlay;
        }

        public void SetLevel(int value)
        {
            level = Math.Max(0, Math.Min(100, value));
            if (level > 0) lastNonZero = level;
            engine.Apply(level);
            Settings.Level = level;
            slider.SetValue(level);
            UpdateTray();
        }

        private void UpdateTray()
        {
            tray.Text = level == 0 ? "Screen Dimmer: off" : "Screen Dimmer: " + level + "% darker";
            int size = Math.Max(16, SystemInformation.SmallIconSize.Width);
            Bitmap bmp = new Bitmap(size, size);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.ScaleTransform(size / 32f, size / 32f);
                g.Clear(Color.Transparent);
                using (Pen pen = new Pen(Color.White, 2.5f))
                {
                    g.DrawEllipse(pen, 5, 5, 22, 22);
                    using (Brush fill = new SolidBrush(Color.White))
                    {
                        // The filled part of the circle shows how bright the screen is.
                        int bright = (100 - level) * 22 / 100;
                        GraphicsState state = g.Save();
                        g.SetClip(new Rectangle(5, 27 - bright, 22, bright));
                        g.FillEllipse(fill, 5, 5, 22, 22);
                        g.Restore(state);
                    }
                }
            }
            IntPtr h = bmp.GetHicon();
            bmp.Dispose();
            tray.Icon = Icon.FromHandle(h);
            if (iconHandle != IntPtr.Zero) Native.DestroyIcon(iconHandle);
            iconHandle = h;
        }

        private static int Step(int current, bool darker)
        {
            // Finer steps at the dark end, where small changes are easier to see.
            bool fine = darker ? current >= 90 : current > 90;
            int step = fine ? 2 : 5;
            return darker ? current + step : current - step;
        }

        protected override void WndProc(ref Message m)
        {
            switch (m.Msg)
            {
                case Native.WM_HOTKEY:
                    int id = m.WParam.ToInt32();
                    if (id == HotDarker) SetLevel(Step(level, true));
                    else if (id == HotBrighter) SetLevel(Step(level, false));
                    else if (id == HotOff) SetLevel(level > 0 ? 0 : Math.Min(lastNonZero, Settings.StartupCap));
                    return;
                case Native.WM_SET_LEVEL:
                    SetLevel(m.WParam.ToInt32());
                    return;
                case Native.WM_SHOW_SLIDER:
                    ShowSlider();
                    return;
                case Native.WM_QUIT_APP:
                    Application.Exit();
                    return;
                case Native.WM_GET_LEVEL:
                    m.Result = new IntPtr(level);
                    return;
                case Native.WM_GET_ENGINE:
                    m.Result = new IntPtr(engine is OverlayEngine ? 2 : 1);
                    return;
                case Native.WM_SET_ENGINE:
                    SwitchEngine(m.WParam.ToInt32() == 2);
                    return;
            }
            base.WndProc(ref m);
        }

        private void OnSystemChange(object sender, EventArgs e)
        {
            if (engine != null) engine.Apply(level);
        }

        private void OnSessionSwitch(object sender, SessionSwitchEventArgs e)
        {
            if (e.Reason == SessionSwitchReason.SessionUnlock && engine != null) engine.Apply(level);
        }

        public void Dispose()
        {
            keepOnTop.Stop();
            SystemEvents.DisplaySettingsChanged -= OnSystemChange;
            SystemEvents.SessionSwitch -= OnSessionSwitch;
            Native.UnregisterHotKey(Handle, HotDarker);
            Native.UnregisterHotKey(Handle, HotBrighter);
            Native.UnregisterHotKey(Handle, HotOff);
            if (engine != null) engine.Dispose();
            tray.Visible = false;
            tray.Dispose();
            slider.Dispose();
            menu.Dispose();
            if (iconHandle != IntPtr.Zero) Native.DestroyIcon(iconHandle);
            DestroyHandle();
        }
    }

    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            string cmd = args.Length > 0 ? args[0].Trim().ToLowerInvariant().TrimEnd('%') : "";
            int requested = -1;

            if (cmd == "off") requested = 0;
            else if (cmd != "" && cmd != "exit" && cmd != "status" && cmd != "overlay" && cmd != "filter")
            {
                if (!int.TryParse(cmd, NumberStyles.Integer, CultureInfo.InvariantCulture, out requested)
                    || requested < 0 || requested > 100)
                {
                    MessageBox.Show("Usage: ScreenDimmer.exe [0-100 | off | overlay | filter | exit]",
                        "Screen Dimmer");
                    return 2;
                }
            }

            bool isFirst;
            using (Mutex mutex = new Mutex(true, @"Local\ScreenDimmerSingleInstance", out isFirst))
            {
                if (!isFirst) return SendToRunning(cmd, requested);
                if (cmd == "exit" || cmd == "status") return 0;

                // Sharp on high-DPI screens. The slider scales itself to match.
                Native.SetProcessDPIAware();

                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);

                if (cmd == "overlay") Settings.UseOverlay = true;
                if (cmd == "filter") Settings.UseOverlay = false;

                // A saved level is capped so a restart can never open on a black screen.
                int start = requested >= 0 ? requested : Math.Min(Settings.Level, Settings.StartupCap);

                using (App app = new App(start))
                {
                    Application.Run();
                }
                GC.KeepAlive(mutex);
            }
            return 0;
        }

        private static int SendToRunning(string cmd, int requested)
        {
            IntPtr h = IntPtr.Zero;
            for (int i = 0; i < 20 && h == IntPtr.Zero; i++)
            {
                h = Native.FindWindow(null, App.WindowTitle);
                if (h == IntPtr.Zero) Thread.Sleep(100);
            }
            if (h == IntPtr.Zero) return 1;

            if (cmd == "exit") Native.SendMessage(h, Native.WM_QUIT_APP, IntPtr.Zero, IntPtr.Zero);
            else if (cmd == "overlay") Native.SendMessage(h, Native.WM_SET_ENGINE, new IntPtr(2), IntPtr.Zero);
            else if (cmd == "filter") Native.SendMessage(h, Native.WM_SET_ENGINE, new IntPtr(1), IntPtr.Zero);
            else if (cmd == "status")
            {
                int level = Native.SendMessage(h, Native.WM_GET_LEVEL, IntPtr.Zero, IntPtr.Zero).ToInt32();
                int engine = Native.SendMessage(h, Native.WM_GET_ENGINE, IntPtr.Zero, IntPtr.Zero).ToInt32();
                return 1000 * engine + level;
            }
            else if (requested >= 0) Native.SendMessage(h, Native.WM_SET_LEVEL, new IntPtr(requested), IntPtr.Zero);
            else
            {
                // Passes this process's foreground right on to the running copy.
                Native.AllowSetForegroundWindow(-1);
                Native.SendMessage(h, Native.WM_SHOW_SLIDER, IntPtr.Zero, IntPtr.Zero);
            }
            return 0;
        }
    }
}
