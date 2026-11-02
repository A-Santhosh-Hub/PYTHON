<#
.SYNOPSIS
    Tiny FPS overlay for games. Single file, nothing installed, nothing injected into the game.

.DESCRIPTION
    Windows itself logs an ETW event every time a program presents a frame. This script listens
    to those events (the same technique Microsoft's PresentMon uses) and shows the FPS of the
    window you are using in a small click-through box in the corner of the screen.

    Events used (from this PC's own manifests, `wevtutil gp <provider> /ge /gm`):
      Microsoft-Windows-DXGI    {CA11C036-0102-4A2D-A6AD-F03CFED5D3C9} id 42  Present start, keyword 0x2  (D3D10/11/12)
      Microsoft-Windows-D3D9    {783ACA0A-790E-4D7F-8451-AA850511C6B9} id 1   Present start, keyword 0x2  (D3D9)
      Microsoft-Windows-DxgKrnl {802EC45A-1E99-4B83-9920-87C98277BA9D} id 184 Present,       keyword 0x8000000 (fallback: Vulkan/OpenGL)

    REA + Ghidra evidence (C:\Windows\System32\dxgi.dll, sha256 4225e13f...a528):
      FUN_180018c00 (DXGI's Present wrapper) writes the event-42 descriptor at 0x1800d4a30 just before
      calling the real present, but only when the session enabled keyword bit 0x2 - hence 0x2 below.

    Overhead: the game is never touched; this process only counts events and redraws a label twice
    a second. Use -Console for no overlay at all.

.PARAMETER Corner
    Where the overlay sits: TopCenter (default), TopLeft, TopRight, BottomLeft, BottomRight, BottomCenter.

.PARAMETER Console
    Print readings in this window once a second instead of drawing an overlay.

.PARAMETER SelfTest
    Listen for N seconds, write every process that presented frames to FpsOverlay-selftest.txt, exit.

.NOTES
    Run: right-click the file > "Run with PowerShell" (asks for admin once via UAC - ETW needs it).
    Exit: tray icon > Exit, or Ctrl+Shift+F12.   Hide/show: Ctrl+Shift+F11.
    Move the box while it runs: Ctrl+Shift+Left / Right = left / right side,
    Ctrl+Shift+C = horizontal center, Ctrl+Shift+Up / Down = top / bottom.
    (Horizontal and vertical are independent, e.g. Down then C = bottom center.)
    Extra lines under the FPS (CPU, GPU, RAM, VRAM; on NVIDIA cards also GPU temp, clock, power):
    show/hide them with Ctrl+Shift+F10.
    The overlay shows over borderless/windowed games; exclusive-fullscreen games draw over it.
#>
param(
    [ValidateSet('TopCenter', 'TopLeft', 'TopRight', 'BottomLeft', 'BottomRight', 'BottomCenter')]
    [string]$Corner = 'TopCenter',
    [switch]$Console,
    [int]$SelfTest = 0
)

$ErrorActionPreference = 'Stop'

# The window is minimized or closes on exit, so make failures visible and leave a log behind.
trap {
    $msg = "FpsOverlay failed: $($_.Exception.Message)`r`n$($_.InvocationInfo.PositionMessage)"
    try { $msg | Out-File -FilePath (Join-Path $PSScriptRoot 'FpsOverlay-error.log') -Encoding utf8 } catch {}
    try { [FpsMeter.Etw]::Stop() } catch {}
    if ($SelfTest -le 0) {
        Add-Type -AssemblyName System.Windows.Forms
        [void][System.Windows.Forms.MessageBox]::Show($msg, 'FpsOverlay')
    }
    exit 1
}

$source = @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace FpsMeter
{
    public class Reading
    {
        public bool Ok;
        public int Pid;
        public string Name;
        public string Api;
        public bool Fallback;
        public double Fps;
        public double Low1;
    }

    // Ring buffer of present timestamps (QPC ticks) for one process.
    class Frames
    {
        public const int N = 4096;
        public readonly long[] Ts = new long[N];
        public int Count, Head;
        public long Last;

        public void Add(long ts)
        {
            int i = Head;
            Head = (Head + 1) % N;
            if (Count < N) Count++;
            // Per-CPU ETW buffers can deliver slightly out of order; keep the ring sorted.
            for (int steps = 0; steps < Count - 1 && steps < 64; steps++)
            {
                int p = (i - 1 + N) % N;
                if (Ts[p] <= ts) break;
                Ts[i] = Ts[p];
                i = p;
            }
            Ts[i] = ts;
            if (ts > Last) Last = ts;
        }

        // FPS over the newest second of frames; 1% low over up to the last 10 seconds.
        public bool Compute(long now, out double fps, out double low1)
        {
            fps = 0; low1 = 0;
            long freq = Stopwatch.Frequency;
            if (Count < 2 || now - Last > freq * 5 / 2) return false;
            int idx = (Head - 1 + N) % N;
            long newest = Ts[idx], prev = newest, firstInSec = newest;
            long oneSec = newest - freq, tenSec = newest - 10 * freq;
            int inSec = 0;
            var intervals = new List<long>(Count);
            for (int i = 1; i < Count; i++)
            {
                idx = (idx - 1 + N) % N;
                long t = Ts[idx];
                if (t < tenSec) break;
                intervals.Add(prev - t);
                if (t >= oneSec) { inSec++; firstInSec = t; }
                prev = t;
            }
            if (inSec < 1 || newest == firstInSec) return false;
            fps = inSec * (double)freq / (newest - firstInSec);
            intervals.Sort();
            long p99 = intervals[Math.Max(0, (int)Math.Ceiling(intervals.Count * 0.99) - 1)];
            low1 = p99 > 0 ? freq / (double)p99 : 0;
            return true;
        }
    }

    public static class Etw
    {
        const string SessionName = "FpsOverlayEtwSession";
        static readonly Guid DXGI = new Guid("CA11C036-0102-4A2D-A6AD-F03CFED5D3C9");
        static readonly Guid D3D9 = new Guid("783ACA0A-790E-4D7F-8451-AA850511C6B9");
        static readonly Guid DXGKRNL = new Guid("802EC45A-1E99-4B83-9920-87C98277BA9D");

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        static extern uint StartTraceW(out ulong handle, string name, IntPtr props);
        [DllImport("advapi32.dll", CharSet = CharSet.Unicode)]
        static extern uint ControlTraceW(ulong handle, string name, IntPtr props, uint code);
        [DllImport("advapi32.dll")]
        static extern uint EnableTraceEx2(ulong handle, ref Guid provider, uint code, byte level,
                                          ulong matchAny, ulong matchAll, uint timeout, IntPtr parameters);
        [DllImport("advapi32.dll", SetLastError = true)]
        static extern ulong OpenTraceW(IntPtr logfile);
        [DllImport("advapi32.dll")]
        static extern uint ProcessTrace(ulong[] handles, uint count, IntPtr start, IntPtr end);
        [DllImport("advapi32.dll")]
        static extern uint CloseTrace(ulong handle);

        [UnmanagedFunctionPointer(CallingConvention.StdCall)]
        delegate void EventRecordCallback(IntPtr record);

        const ulong InvalidHandle = ulong.MaxValue;
        const int PropsSize = 120, NameBytes = 1024, LogfileSize = 448;
        static EventRecordCallback callback; // must stay referenced while ProcessTrace runs
        static IntPtr logfile = IntPtr.Zero, loggerName = IntPtr.Zero;
        static ulong session, trace = InvalidHandle;

        static readonly object gate = new object();
        // DirectX presents are kept per swap chain: a game can own more than one (e.g. an in-game overlay),
        // and summing them would double the FPS. The busiest swap chain is the game's frame rate.
        static readonly Dictionary<int, Dictionary<long, Frames>> apiFrames = new Dictionary<int, Dictionary<long, Frames>>();
        static readonly Dictionary<int, Frames> kernelFrames = new Dictionary<int, Frames>();
        static long testPresentsSkipped;
        static readonly Dictionary<int, string> names = new Dictionary<int, string>();
        static readonly int selfPid = Process.GetCurrentProcess().Id;

        static IntPtr Zeroed(int size)
        {
            IntPtr p = Marshal.AllocHGlobal(size);
            for (int i = 0; i < size; i++) Marshal.WriteByte(p, i, 0);
            return p;
        }

        // EVENT_TRACE_PROPERTIES (x64): Wnode 0..47, BufferSize 48, LogFileMode 64, FlushTimer 68,
        // LoggerNameOffset 116; the logger name follows the 120-byte struct.
        static IntPtr NewProperties()
        {
            int total = PropsSize + NameBytes;
            IntPtr p = Zeroed(total);
            Marshal.WriteInt32(p, 0, total);        // Wnode.BufferSize
            Marshal.WriteInt32(p, 40, 1);           // Wnode.ClientContext: QPC timestamps
            Marshal.WriteInt32(p, 44, 0x00020000);  // Wnode.Flags: WNODE_FLAG_TRACED_GUID
            Marshal.WriteInt32(p, 48, 64);          // BufferSize (KB)
            Marshal.WriteInt32(p, 64, 0x00000100);  // EVENT_TRACE_REAL_TIME_MODE
            Marshal.WriteInt32(p, 68, 1);           // FlushTimer (s)
            Marshal.WriteInt32(p, 116, PropsSize);  // LoggerNameOffset
            return p;
        }

        static void StopSession()
        {
            IntPtr p = NewProperties();
            try { ControlTraceW(0, SessionName, p, 1 /* EVENT_TRACE_CONTROL_STOP */); }
            finally { Marshal.FreeHGlobal(p); }
        }

        // Returns 0 on success, otherwise a Win32 error code (5 = needs admin).
        public static uint Start()
        {
            StopSession(); // a crashed earlier run can leave the session behind
            IntPtr p = NewProperties();
            uint rc;
            try { rc = StartTraceW(out session, SessionName, p); }
            finally { Marshal.FreeHGlobal(p); }
            if (rc != 0) return rc;

            Guid g = DXGI;
            rc = EnableTraceEx2(session, ref g, 1, 4, 0x8000000000000002UL, 0, 0, IntPtr.Zero);
            if (rc != 0) { Stop(); return rc; }
            g = D3D9;
            EnableTraceEx2(session, ref g, 1, 4, 0x8000000000000002UL, 0, 0, IntPtr.Zero);
            g = DXGKRNL;
            EnableTraceEx2(session, ref g, 1, 4, 0x8000000UL, 0, 0, IntPtr.Zero);

            // EVENT_TRACE_LOGFILEW (x64): LoggerName 8, ProcessTraceMode 28, EventRecordCallback 424.
            callback = OnEvent;
            logfile = Zeroed(LogfileSize);
            loggerName = Marshal.StringToHGlobalUni(SessionName);
            Marshal.WriteIntPtr(logfile, 8, loggerName);
            Marshal.WriteInt32(logfile, 28, 0x00000100 | 0x10000000); // REAL_TIME | EVENT_RECORD
            Marshal.WriteIntPtr(logfile, 424, Marshal.GetFunctionPointerForDelegate(callback));
            trace = OpenTraceW(logfile);
            if (trace == InvalidHandle)
            {
                rc = (uint)Marshal.GetLastWin32Error();
                Stop();
                return rc == 0 ? 1u : rc;
            }
            var thread = new Thread(() => ProcessTrace(new[] { trace }, 1, IntPtr.Zero, IntPtr.Zero));
            thread.IsBackground = true;
            thread.Start();
            return 0;
        }

        public static void Stop()
        {
            StopSession();
            if (trace != InvalidHandle) { CloseTrace(trace); trace = InvalidHandle; }
        }

        // EVENT_RECORD: EventHeader.ProcessId 12, TimeStamp 16, ProviderId 24, EventDescriptor.Id 40,
        // UserDataLength 86, UserData 96. Present_Start payload (dxgi.dll FUN_180018c00 / d3d9):
        // swap chain pointer (8 bytes), then Flags (4 bytes).
        static void OnEvent(IntPtr record)
        {
            uint provider = (uint)Marshal.ReadInt32(record, 24); // GUID Data1 is unique among our 3 providers
            ushort id = (ushort)Marshal.ReadInt16(record, 40);
            bool dxgi = provider == 0xCA11C036 && id == 42;
            bool d3d9 = provider == 0x783ACA0A && id == 1;
            bool kernel = provider == 0x802EC45A && id == 184;
            if (!dxgi && !d3d9 && !kernel) return;
            int pid = Marshal.ReadInt32(record, 12);
            long ts = Marshal.ReadInt64(record, 16);

            long chain = 0;
            if (!kernel)
            {
                ushort length = (ushort)Marshal.ReadInt16(record, 86);
                IntPtr data = Marshal.ReadIntPtr(record, 96);
                if (length >= 12 && data != IntPtr.Zero)
                {
                    chain = Marshal.ReadInt64(data, 0);
                    // DXGI_PRESENT_TEST only asks "is the window visible?" - no frame is shown.
                    if (dxgi && (Marshal.ReadInt32(data, 8) & 0x1) != 0)
                    {
                        Interlocked.Increment(ref testPresentsSkipped);
                        return;
                    }
                }
            }

            lock (gate)
            {
                Frames f;
                if (kernel)
                {
                    if (!kernelFrames.TryGetValue(pid, out f)) kernelFrames[pid] = f = new Frames();
                }
                else
                {
                    Dictionary<long, Frames> chains;
                    if (!apiFrames.TryGetValue(pid, out chains)) apiFrames[pid] = chains = new Dictionary<long, Frames>();
                    if (!chains.TryGetValue(chain, out f)) chains[chain] = f = new Frames();
                }
                f.Add(ts);
            }
        }

        static bool Busiest(Dictionary<long, Frames> chains, long now, out double fps, out double low1)
        {
            fps = 0; low1 = 0;
            foreach (Frames f in chains.Values)
            {
                double a, b;
                if (f.Compute(now, out a, out b) && a > fps) { fps = a; low1 = b; }
            }
            return fps > 0;
        }

        static string NameOf(int pid)
        {
            string n;
            if (names.TryGetValue(pid, out n)) return n;
            try { n = Process.GetProcessById(pid).ProcessName + ".exe"; }
            catch { n = "pid " + pid; }
            names[pid] = n;
            return n;
        }

        static bool Stale(Frames f, long now) { return now - f.Last > Stopwatch.Frequency * 30; }

        static void Prune(long now)
        {
            var dead = new List<int>();
            foreach (var kv in kernelFrames) if (Stale(kv.Value, now)) dead.Add(kv.Key);
            foreach (int pid in dead) kernelFrames.Remove(pid);
            dead.Clear();
            foreach (var kv in apiFrames)
            {
                var deadChains = new List<long>();
                foreach (var c in kv.Value) if (Stale(c.Value, now)) deadChains.Add(c.Key);
                foreach (long c in deadChains) kv.Value.Remove(c);
                if (kv.Value.Count == 0) dead.Add(kv.Key);
            }
            foreach (int pid in dead) apiFrames.Remove(pid);
            var gone = new List<int>();
            foreach (int pid in names.Keys) if (!apiFrames.ContainsKey(pid) && !kernelFrames.ContainsKey(pid)) gone.Add(pid);
            foreach (int pid in gone) names.Remove(pid);
        }

        // Reading for the preferred (foreground) process; otherwise the busiest DirectX presenter.
        public static Reading Snapshot(int preferPid)
        {
            var r = new Reading();
            long now = Stopwatch.GetTimestamp();
            lock (gate)
            {
                Prune(now);
                Frames f;
                Dictionary<long, Frames> chains;
                double fps, low;
                if (apiFrames.TryGetValue(preferPid, out chains) && Busiest(chains, now, out fps, out low))
                { r.Ok = true; r.Api = "DirectX"; }
                else if (kernelFrames.TryGetValue(preferPid, out f) && f.Compute(now, out fps, out low))
                { r.Ok = true; r.Api = "kernel"; }
                else
                {
                    double best = 0, bestLow = 0;
                    int bestPid = 0;
                    foreach (var kv in apiFrames)
                    {
                        if (kv.Key == selfPid) continue;
                        double a, b;
                        if (Busiest(kv.Value, now, out a, out b) && a > best) { best = a; bestLow = b; bestPid = kv.Key; }
                    }
                    fps = best; low = bestLow;
                    if (bestPid != 0) { r.Ok = true; r.Api = "DirectX"; r.Fallback = true; preferPid = bestPid; }
                }
                if (r.Ok) { r.Pid = preferPid; r.Name = NameOf(preferPid); r.Fps = fps; r.Low1 = low; }
            }
            return r;
        }

        public static string Report()
        {
            var sb = new StringBuilder();
            long now = Stopwatch.GetTimestamp();
            const string row = "  {0,-28} pid {1,-6} {2,-20} frames {3,-5} fps {4,6:0.0}  1% low {5,6:0.0}{6}";
            lock (gate)
            {
                sb.AppendLine("DirectX (DXGI/D3D9), per swap chain: " + apiFrames.Count + " process(es)");
                foreach (var kv in apiFrames)
                    foreach (var c in kv.Value)
                    {
                        double fps, low;
                        bool ok = c.Value.Compute(now, out fps, out low);
                        sb.AppendLine(string.Format(row, NameOf(kv.Key), kv.Key, "chain 0x" + c.Key.ToString("x"),
                            c.Value.Count, fps, low, ok ? "" : "  (idle)"));
                    }
                sb.AppendLine("kernel (DxgKrnl 184): " + kernelFrames.Count + " process(es)");
                foreach (var kv in kernelFrames)
                {
                    double fps, low;
                    bool ok = kv.Value.Compute(now, out fps, out low);
                    sb.AppendLine(string.Format(row, NameOf(kv.Key), kv.Key, "", kv.Value.Count, fps, low, ok ? "" : "  (idle)"));
                }
                sb.AppendLine("DXGI_PRESENT_TEST calls skipped: " + Interlocked.Read(ref testPresentsSkipped));
            }
            return sb.ToString();
        }
    }

    // CPU / RAM / GPU / VRAM readings, refreshed once a second on a background thread.
    // CPU + RAM: kernel32. GPU usage + VRAM: Windows "GPU Engine" / "GPU Adapter Memory" counters.
    // NVIDIA only (optional): nvml.dll gives GPU usage, temperature, clock, power, VRAM total.
    public static class Sys
    {
        [DllImport("kernel32.dll")]
        static extern bool GetSystemTimes(out long idle, out long kernel, out long user);
        [DllImport("kernel32.dll")]
        static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX status);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        static extern IntPtr LoadLibraryW(string file);

        [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int nvmlInit_v2();
        [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int nvmlDeviceGetHandleByIndex_v2(uint index, out IntPtr device);
        [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int nvmlDeviceGetTemperature(IntPtr device, int sensor, out uint temp);
        [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int nvmlDeviceGetUtilizationRates(IntPtr device, out NvmlUtil util);
        [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int nvmlDeviceGetMemoryInfo(IntPtr device, out NvmlMem mem);
        [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int nvmlDeviceGetClockInfo(IntPtr device, int clockType, out uint mhz);
        [DllImport("nvml.dll", CallingConvention = CallingConvention.Cdecl)]
        static extern int nvmlDeviceGetPowerUsage(IntPtr device, out uint milliwatts);

        [StructLayout(LayoutKind.Sequential)]
        public struct MEMORYSTATUSEX
        {
            public uint dwLength;
            public uint dwMemoryLoad;
            public ulong ullTotalPhys;
            public ulong ullAvailPhys;
            public ulong ullTotalPageFile;
            public ulong ullAvailPageFile;
            public ulong ullTotalVirtual;
            public ulong ullAvailVirtual;
            public ulong ullAvailExtendedVirtual;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct NvmlUtil
        {
            public uint gpu;
            public uint memory;
        }

        [StructLayout(LayoutKind.Sequential)]
        public struct NvmlMem
        {
            public ulong total;
            public ulong free;
            public ulong used;
        }

        static readonly object gate = new object();
        static bool started;
        static volatile bool nvml;
        static IntPtr nvDev;
        static double cpu = -1, gpuCounter = -1, vramCounter = -1;
        static double ramUsed, ramTotal, ramPct;
        static double nvUtil = -1, nvTemp = -1, nvVramUsed = -1, nvVramTotal = -1, nvClock = -1, nvPower = -1;

        public static bool HasNvml { get { return nvml; } }

        public static void Start()
        {
            lock (gate)
            {
                if (started) return;
                started = true;
            }
            var t = new Thread(Loop);
            t.IsBackground = true;
            t.Start();
        }

        static void InitNvml()
        {
            try
            {
                if (LoadLibraryW("nvml.dll") == IntPtr.Zero)
                    LoadLibraryW(@"C:\Program Files\NVIDIA Corporation\NVSMI\nvml.dll");
                if (nvmlInit_v2() != 0) return;
                if (nvmlDeviceGetHandleByIndex_v2(0, out nvDev) != 0) return;
                nvml = true;
            }
            catch (Exception) { nvml = false; }
        }

        static void Loop()
        {
            long pi, pk, pu;
            GetSystemTimes(out pi, out pk, out pu);
            PerformanceCounterCategory gpuCat = null, memCat = null;
            try { if (PerformanceCounterCategory.Exists("GPU Engine")) gpuCat = new PerformanceCounterCategory("GPU Engine"); }
            catch (Exception) { }
            try { if (PerformanceCounterCategory.Exists("GPU Adapter Memory")) memCat = new PerformanceCounterCategory("GPU Adapter Memory"); }
            catch (Exception) { }
            InitNvml();
            var prevEng = new Dictionary<string, CounterSample>();

            while (true)
            {
                // CPU: share of non-idle time since the last pass (kernel time includes idle time).
                try
                {
                    long ci, ck, cu;
                    if (GetSystemTimes(out ci, out ck, out cu))
                    {
                        long dIdle = ci - pi;
                        long dTotal = (ck - pk) + (cu - pu);
                        if (dTotal > 0)
                        {
                            double c = 100.0 * (dTotal - dIdle) / dTotal;
                            lock (gate) cpu = Math.Max(0.0, Math.Min(100.0, c));
                        }
                        pi = ci; pk = ck; pu = cu;
                    }
                }
                catch (Exception) { }

                // RAM
                try
                {
                    var ms = new MEMORYSTATUSEX();
                    ms.dwLength = (uint)Marshal.SizeOf(typeof(MEMORYSTATUSEX));
                    if (GlobalMemoryStatusEx(ref ms))
                    {
                        lock (gate)
                        {
                            ramTotal = ms.ullTotalPhys / 1073741824.0;
                            ramUsed = (ms.ullTotalPhys - ms.ullAvailPhys) / 1073741824.0;
                            ramPct = ms.dwMemoryLoad;
                        }
                    }
                }
                catch (Exception) { }

                // GPU usage from Windows counters: sum the processes on each engine, take the busiest engine.
                try
                {
                    if (gpuCat != null)
                    {
                        InstanceDataCollectionCollection all = gpuCat.ReadCategory();
                        if (all.Contains("Utilization Percentage"))
                        {
                            var cur = new Dictionary<string, CounterSample>();
                            var sums = new Dictionary<string, double>();
                            foreach (InstanceData inst in all["Utilization Percentage"].Values)
                            {
                                string name = inst.InstanceName;
                                cur[name] = inst.Sample;
                                CounterSample old;
                                if (!prevEng.TryGetValue(name, out old)) continue;
                                int k = name.IndexOf("luid_", StringComparison.Ordinal);
                                if (k < 0) continue;
                                string key = name.Substring(k);
                                double v = 0;
                                try { v = CounterSample.Calculate(old, inst.Sample); }
                                catch (Exception) { continue; }
                                double prevSum;
                                sums.TryGetValue(key, out prevSum);
                                sums[key] = prevSum + v;
                            }
                            double best = 0;
                            foreach (double engineTotal in sums.Values) if (engineTotal > best) best = engineTotal;
                            prevEng = cur;
                            lock (gate) gpuCounter = Math.Min(100.0, best);
                        }
                    }
                }
                catch (Exception) { }

                // VRAM in use from Windows counters (largest adapter).
                try
                {
                    if (memCat != null)
                    {
                        InstanceDataCollectionCollection mem = memCat.ReadCategory();
                        if (mem.Contains("Dedicated Usage"))
                        {
                            double maxGb = -1;
                            foreach (InstanceData inst in mem["Dedicated Usage"].Values)
                            {
                                double gb = inst.Sample.RawValue / 1073741824.0;
                                if (gb > maxGb) maxGb = gb;
                            }
                            lock (gate) vramCounter = maxGb;
                        }
                    }
                }
                catch (Exception) { }

                // NVIDIA extras
                try
                {
                    if (nvml)
                    {
                        double aTemp = -1, aUtil = -1, aUsed = -1, aTotal = -1, aClock = -1, aPower = -1;
                        uint t, clk, pw;
                        NvmlUtil u;
                        NvmlMem m;
                        if (nvmlDeviceGetTemperature(nvDev, 0, out t) == 0) aTemp = t;
                        if (nvmlDeviceGetUtilizationRates(nvDev, out u) == 0) aUtil = u.gpu;
                        if (nvmlDeviceGetMemoryInfo(nvDev, out m) == 0)
                        {
                            aUsed = m.used / 1073741824.0;
                            aTotal = m.total / 1073741824.0;
                        }
                        if (nvmlDeviceGetClockInfo(nvDev, 0, out clk) == 0) aClock = clk;
                        if (nvmlDeviceGetPowerUsage(nvDev, out pw) == 0) aPower = pw / 1000.0;
                        lock (gate)
                        {
                            nvTemp = aTemp; nvUtil = aUtil; nvVramUsed = aUsed;
                            nvVramTotal = aTotal; nvClock = aClock; nvPower = aPower;
                        }
                    }
                }
                catch (Exception) { }

                Thread.Sleep(1000);
            }
        }

        static string Pct(double v)
        {
            return v < 0 ? " --%" : string.Format("{0,3:0}%", v);
        }

        public static string Line1()
        {
            lock (gate)
            {
                double gpu = nvUtil >= 0 ? nvUtil : gpuCounter;
                string s = "CPU " + Pct(cpu) + "  GPU " + Pct(gpu);
                if (nvTemp >= 0) s += "  " + nvTemp.ToString("0") + "C";
                return s;
            }
        }

        public static string Line2()
        {
            lock (gate)
            {
                string s = string.Format("RAM {0:0.0}/{1:0.0}G {2:0}%", ramUsed, ramTotal, ramPct);
                double vram = nvVramUsed >= 0 ? nvVramUsed : vramCounter;
                if (vram >= 0)
                {
                    s += "  VRAM " + vram.ToString("0.0");
                    if (nvVramTotal > 0) s += "/" + nvVramTotal.ToString("0.0");
                    s += "G";
                }
                return s;
            }
        }

        public static string Line3()
        {
            lock (gate)
            {
                if (!nvml) return "";
                string s = "";
                if (nvClock >= 0) s += "CLK " + nvClock.ToString("0") + "MHz";
                if (nvPower >= 0) s += "  PWR " + nvPower.ToString("0") + "W";
                return s.Trim();
            }
        }
    }

    public class Overlay : Form
    {
        [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hwnd, out int pid);
        [DllImport("user32.dll")] static extern bool RegisterHotKey(IntPtr hwnd, int id, uint mods, uint vk);
        [DllImport("user32.dll")] static extern bool UnregisterHotKey(IntPtr hwnd, int id);
        [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int cx, int cy, uint flags);

        const int HotkeyExit = 1, HotkeyToggle = 2, HotkeyLeft = 3, HotkeyRight = 4,
                  HotkeyUp = 5, HotkeyDown = 6, HotkeyCenter = 7, HotkeyStats = 8;
        readonly Label big, small, statsA, statsB, statsC;
        readonly NotifyIcon tray;
        readonly System.Windows.Forms.Timer timer;
        string corner;
        bool hidden;
        bool showStats = true;

        public Overlay(string corner)
        {
            this.corner = corner;
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            TopMost = true;
            StartPosition = FormStartPosition.Manual;
            BackColor = Color.Black;
            Opacity = 0.8;
            ClientSize = new Size(230, 84);

            big = new Label { ForeColor = Color.Lime, Font = new Font("Consolas", 20f, FontStyle.Bold),
                              Bounds = new Rectangle(6, 2, 224, 30), Text = "-- FPS" };
            small = new Label { ForeColor = Color.Gainsboro, Font = new Font("Consolas", 8.25f),
                                Bounds = new Rectangle(8, 33, 222, 16), Text = "waiting for frames" };
            Controls.Add(big);
            Controls.Add(small);
            statsA = new Label { ForeColor = Color.Gainsboro, Font = new Font("Consolas", 8.25f),
                                 Bounds = new Rectangle(8, 50, 222, 16), Text = "CPU  --%  GPU  --%" };
            statsB = new Label { ForeColor = Color.Gainsboro, Font = new Font("Consolas", 8.25f),
                                 Bounds = new Rectangle(8, 66, 222, 16), Text = "RAM --" };
            statsC = new Label { ForeColor = Color.Gainsboro, Font = new Font("Consolas", 8.25f),
                                 Bounds = new Rectangle(8, 82, 222, 16), Text = "" };
            Controls.Add(statsA);
            Controls.Add(statsB);
            Controls.Add(statsC);
            Sys.Start();

            var menu = new ContextMenu();
            menu.MenuItems.Add("Hide / show  (Ctrl+Shift+F11)", (s, e) => Toggle());
            menu.MenuItems.Add("Exit  (Ctrl+Shift+F12)", (s, e) => Close());
            tray = new NotifyIcon { Icon = SystemIcons.Information, Text = "FPS overlay", Visible = true, ContextMenu = menu };

            timer = new System.Windows.Forms.Timer { Interval = 500 };
            timer.Tick += (s, e) => Tick();
            timer.Start();
        }

        // Layered, click-through, no taskbar button, never takes focus from the game.
        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000 | 0x00000008;
                return cp;
            }
        }

        protected override bool ShowWithoutActivation { get { return true; } }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            RegisterHotKey(Handle, HotkeyExit, 0x2 | 0x4 | 0x4000, (uint)Keys.F12);   // Ctrl+Shift, no repeat
            RegisterHotKey(Handle, HotkeyToggle, 0x2 | 0x4 | 0x4000, (uint)Keys.F11);
            RegisterHotKey(Handle, HotkeyLeft,   0x2 | 0x4 | 0x4000, (uint)Keys.Left);
            RegisterHotKey(Handle, HotkeyRight,  0x2 | 0x4 | 0x4000, (uint)Keys.Right);
            RegisterHotKey(Handle, HotkeyUp,     0x2 | 0x4 | 0x4000, (uint)Keys.Up);
            RegisterHotKey(Handle, HotkeyDown,   0x2 | 0x4 | 0x4000, (uint)Keys.Down);
            RegisterHotKey(Handle, HotkeyCenter, 0x2 | 0x4 | 0x4000, (uint)Keys.C);
            RegisterHotKey(Handle, HotkeyStats,  0x2 | 0x4 | 0x4000, (uint)Keys.F10);
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == 0x0312) // WM_HOTKEY
            {
                if (m.WParam.ToInt32() == HotkeyExit) { Close(); return; }
                if (m.WParam.ToInt32() == HotkeyToggle) { Toggle(); return; }
                int id = m.WParam.ToInt32();
                if (id == HotkeyStats) { showStats = !showStats; Tick(); return; }
                if (id >= HotkeyLeft && id <= HotkeyCenter) { ShiftBox(id); return; }
            }
            base.WndProc(ref m);
        }

        public static int ForegroundPid()
        {
            int pid;
            GetWindowThreadProcessId(GetForegroundWindow(), out pid);
            return pid;
        }

        // Horizontal (Left/Center/Right) and vertical (Top/Bottom) are changed independently.
        void ShiftBox(int id)
        {
            string v = corner.StartsWith("Bottom") ? "Bottom" : "Top";
            string h = corner.EndsWith("Right") ? "Right" : corner.EndsWith("Center") ? "Center" : "Left";
            if (id == HotkeyLeft) h = "Left";
            else if (id == HotkeyRight) h = "Right";
            else if (id == HotkeyCenter) h = "Center";
            else if (id == HotkeyUp) v = "Top";
            else if (id == HotkeyDown) v = "Bottom";
            corner = v + h;
            Tick();
        }

        void Toggle()
        {
            hidden = !hidden;
            if (hidden) Hide(); else Show();
        }

        void Tick()
        {
            if (hidden) return;
            IntPtr fg = GetForegroundWindow();
            int pid;
            GetWindowThreadProcessId(fg, out pid);
            Reading r = Etw.Snapshot(pid);
            if (r.Ok)
            {
                big.Text = string.Format("{0,4:0} FPS", r.Fps);
                big.ForeColor = r.Fps >= 60 ? Color.Lime : r.Fps >= 30 ? Color.Gold : Color.OrangeRed;
                string name = r.Name.Length > 14 ? r.Name.Substring(0, 14) : r.Name;
                small.Text = string.Format("{0:0.0}ms 1%:{1:0} {2}{3}", 1000.0 / r.Fps, r.Low1, name, r.Fallback ? "*" : "");
            }
            else
            {
                big.Text = "  -- FPS";
                big.ForeColor = Color.Gray;
                small.Text = "no frames from this app";
            }

            statsA.Visible = statsB.Visible = showStats;
            statsC.Visible = showStats && Sys.HasNvml;
            if (showStats)
            {
                statsA.Text = Sys.Line1();
                statsB.Text = Sys.Line2();
                statsC.Text = Sys.Line3();
            }
            int want = !showStats ? 52 : (Sys.HasNvml ? 100 : 84);
            if (ClientSize.Height != want) ClientSize = new Size(230, want);

            Rectangle area = Screen.FromHandle(fg).Bounds;
            int x = corner.EndsWith("Right") ? area.Right - Width - 10
                  : corner.EndsWith("Center") ? area.Left + (area.Width - Width) / 2
                  : area.Left + 10;
            int y = corner.StartsWith("Bottom") ? area.Bottom - Height - 10 : area.Top + 10;
            // Re-assert topmost each tick; games that go topmost would otherwise cover the box.
            SetWindowPos(Handle, new IntPtr(-1), x, y, 0, 0, 0x0001 | 0x0010); // NOSIZE | NOACTIVATE
        }

        protected override void OnFormClosed(FormClosedEventArgs e)
        {
            timer.Stop();
            tray.Visible = false;
            UnregisterHotKey(Handle, HotkeyExit);
            UnregisterHotKey(Handle, HotkeyToggle);
            for (int k = HotkeyLeft; k <= HotkeyCenter; k++) UnregisterHotKey(Handle, k);
            UnregisterHotKey(Handle, HotkeyStats);
            base.OnFormClosed(e);
        }
    }
}
'@

Add-Type -TypeDefinition $source -ReferencedAssemblies System.Windows.Forms, System.Drawing

$rc = [FpsMeter.Etw]::Start()
if ($rc -eq 5) {
    # ETW sessions need admin (or membership of "Performance Log Users"): relaunch elevated once.
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) { throw 'Access denied starting the ETW session even as administrator.' }
    $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"", '-Corner', $Corner)
    if ($Console) { $argList += '-Console' }
    if ($SelfTest -gt 0) { $argList += @('-SelfTest', $SelfTest) }
    $style = if ($Console) { 'Normal' } else { 'Minimized' }
    $proc = Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -WindowStyle $style -PassThru
    if ($SelfTest -gt 0) { $proc.WaitForExit() }
    return
}
if ($rc -ne 0) { throw "Could not start the ETW session (Win32 error $rc)." }

try {
    if ($SelfTest -gt 0) {
        $started = Get-Date
        $perSecond = New-Object System.Collections.Generic.List[string]
        for ($i = 1; $i -le $SelfTest; $i++) {
            Start-Sleep -Seconds 1
            $r = [FpsMeter.Etw]::Snapshot([FpsMeter.Overlay]::ForegroundPid())
            if ($r.Ok) {
                $perSecond.Add(('{0,4}s  {1,6:0.0} FPS  1% low {2,5:0.0}  {3}{4}' -f $i, $r.Fps, $r.Low1, $r.Name,
                    $(if ($r.Fallback) { '*' } else { '' })))
            }
            else { $perSecond.Add(('{0,4}s  no frames from the foreground app' -f $i)) }
        }
        $log = Join-Path $PSScriptRoot 'FpsOverlay-selftest.txt'
        "FpsOverlay self-test $(Get-Date $started -Format s), listened ${SelfTest}s`r`n" + [FpsMeter.Etw]::Report() +
            "`r`nPer second (foreground app):`r`n" + ($perSecond -join "`r`n") |
            Out-File -FilePath $log -Encoding utf8
    }
    elseif ($Console) {
        Write-Host 'Showing FPS of the foreground window (* = busiest DirectX app instead). Ctrl+C to stop.'
        [FpsMeter.Sys]::Start()
        while ($true) {
            Start-Sleep -Seconds 1
            $r = [FpsMeter.Etw]::Snapshot([FpsMeter.Overlay]::ForegroundPid())
            if ($r.Ok) {
                ('{0:HH:mm:ss}  {1,6:0.0} FPS  {2,5:0.0} ms  1% low {3,5:0}  {4}{5} [{6}]' -f (Get-Date), $r.Fps,
                    (1000 / $r.Fps), $r.Low1, $r.Name, $(if ($r.Fallback) { '*' } else { '' }), $r.Api) +
                    '  | ' + [FpsMeter.Sys]::Line1() + '  | ' + [FpsMeter.Sys]::Line2()
            }
            else { '{0:HH:mm:ss}  no frames from the foreground app' -f (Get-Date) }
        }
    }
    else {
        [System.Windows.Forms.Application]::Run((New-Object FpsMeter.Overlay $Corner))
    }
}
finally {
    [FpsMeter.Etw]::Stop()
}
