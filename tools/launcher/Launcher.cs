// UOC2 存档修改器 —— 启动器（Launcher）
//
// 为什么要有它：成品包是「一个目录 + 一个 exe」⇒ 用户只点这一个 exe。
// 它做四件事：
//   ① 找到随包的 python\python.exe，起本地服务（不拉窗口）；
//   ② 从服务的 stdout 里读出带 token 的地址；
//   ③ 用 Edge 的 --app 模式开一个独立窗口（**没有 Edge 就退回默认浏览器**）；
//   ④ 窗口关掉 ⇒ 服务一起退（跟原来 run_web.bat 的行为一致）。
//
// 另外：**已经在跑**就只把窗口叫出来（单实例），不重复起服务。
//
// ⚠️ 只用 .NET Framework 4.x 自带的东西（System.Windows.Forms 只是为了弹错误框），
//    **零第三方依赖** ⇒ 编译用系统自带的 csc.exe 即可（见 tools/build_launcher.py）。
//
// 作者：烟柳边城 misprit

using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("统一指挥 2 存档修改器")]
[assembly: AssemblyDescription("《统一指挥 2》存档修改器 —— 启动器")]
[assembly: AssemblyProduct("UOC2 Save Modifier")]
[assembly: AssemblyCompany("烟柳边城 misprit")]
[assembly: AssemblyCopyright("Copyright © 烟柳边城 misprit")]
[assembly: AssemblyVersion("1.1.1.0")]
[assembly: AssemblyFileVersion("1.1.1.0")]

internal static class Launcher
{
    private const string TITLE = "统一指挥 2 存档修改器";

    private static string Root
    {
        get { return AppDomain.CurrentDomain.BaseDirectory; }
    }

    /// <summary>游戏数据目录（配置 / 存档 / 日志都在这儿；**不在程序目录里**）。</summary>
    private static string AppData
    {
        get
        {
            string env = Environment.GetEnvironmentVariable("UOC2_APPDATA");
            if (!string.IsNullOrEmpty(env))
                return env;
            return Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                ".uoc2");
        }
    }

    [STAThread]
    private static int Main()
    {
        try
        {
            return Run();
        }
        catch (Exception ex)
        {
            Fail("启动失败：" + ex.Message);
            return 1;
        }
    }

    private static int Run()
    {
        string py = Path.Combine(Root, "python", "python.exe");
        if (!File.Exists(py))
        {
            Fail("找不到 python\\python.exe\r\n\r\n"
               + "这个压缩包不完整，请重新解压整个包再运行。");
            return 1;
        }

        string urlFile = Path.Combine(AppData, "server.url");

        // ① 已经在跑？⇒ 只把窗口叫出来
        string old = ReadAll(urlFile);
        if (old != null && Alive(old))
        {
            OpenDefault(old);
            return 0;
        }

        // ② 起服务（**不拉窗口** —— 浏览器归本启动器管）
        ProcessStartInfo psi = new ProcessStartInfo(
            py, "-u -m save_modifier_web.server --serve --no-browser");
        psi.WorkingDirectory = Root;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        Process proc = Process.Start(psi);
        if (proc == null)
        {
            Fail("起不来服务。");
            return 1;
        }

        // stderr 也要抽走（管道满了服务会卡住）
        Thread errThread = new Thread(delegate() { Drain(proc.StandardError); });
        errThread.IsBackground = true;
        errThread.Start();

        string url = null;
        Thread reader = new Thread(delegate() { url = WaitUrl(proc); });
        reader.IsBackground = true;
        reader.Start();

        DateTime deadline = DateTime.Now.AddSeconds(60);
        while (url == null && DateTime.Now < deadline && !proc.HasExited)
            Thread.Sleep(120);

        if (url == null)
        {
            Kill(proc);
            Fail("服务没能启动（60 秒内没拿到地址）。\r\n\r\n日志在：\r\n"
               + Path.Combine(AppData, "modifier.log"));
            return 1;
        }
        WriteAll(urlFile, url);

        // ③ 开窗口
        string edge = FindEdge();
        if (edge != null)
        {
            Process browser = LaunchEdge(edge, url);
            if (browser != null)
            {
                browser.WaitForExit();       // 关掉窗口 ⇒ 服务一起退
                Kill(proc);
                TryDelete(urlFile);
                return 0;
            }
        }

        // 没有 Edge ⇒ 退回默认浏览器；提示用完关掉
        OpenDefault(url);
        MessageBox.Show(
            "界面已在默认浏览器中打开。\r\n\r\n用完请点「确定」，修改器会随之退出。",
            TITLE, MessageBoxButtons.OK, MessageBoxIcon.Information);
        Kill(proc);
        TryDelete(urlFile);
        return 0;
    }

    // ---------------------------------------------------------------- 小工具

    /// <summary>从服务的 stdout 里读出「http://…」（那行前面有中文提示，无所谓）。</summary>
    private static string WaitUrl(Process proc)
    {
        string line;
        while ((line = proc.StandardOutput.ReadLine()) != null)
        {
            int i = line.IndexOf("http://", StringComparison.Ordinal);
            if (i < 0)
                continue;
            int end = i;
            while (end < line.Length && !char.IsWhiteSpace(line[end]))
                end++;
            return line.Substring(i, end - i);
        }
        return null;
    }

    private static void Drain(StreamReader r)
    {
        try
        {
            while (r.ReadLine() != null) { }
        }
        catch { }
    }

    private static string FindEdge()
    {
        string[] paths = new string[]
        {
            @"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            @"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            @"C:\Program Files (x86)\Microsoft\Edge Beta\Application\msedge.exe",
        };
        for (int i = 0; i < paths.Length; i++)
            if (File.Exists(paths[i]))
                return paths[i];
        return null;
    }

    private static Process LaunchEdge(string edge, string url)
    {
        try
        {
            string profile = Path.Combine(AppData, "edge_profile");
            Directory.CreateDirectory(profile);
            ProcessStartInfo psi = new ProcessStartInfo(edge);
            psi.Arguments =
                "--app=" + url +
                " --user-data-dir=\"" + profile + "\"" +
                " --no-first-run --no-default-browser-check" +
                " --force-device-scale-factor=1" +
                " --window-size=1500,940" +
                " --disable-features=Translate,msEdgeSidebarV2,msEdgeShoppingAssistant";
            psi.UseShellExecute = false;
            return Process.Start(psi);
        }
        catch
        {
            return null;
        }
    }

    /// <summary>默认浏览器（任何浏览器都能开这个界面 —— 它本来就是纯 HTML）。</summary>
    private static void OpenDefault(string url)
    {
        try
        {
            ProcessStartInfo psi = new ProcessStartInfo(url);
            psi.UseShellExecute = true;
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            Fail("打不开浏览器：\r\n" + ex.Message + "\r\n\r\n"
               + "可以手动在浏览器里打开：\r\n" + url);
        }
    }

    /// <summary>服务还活着吗？（连一下端口就知道）</summary>
    private static bool Alive(string url)
    {
        try
        {
            Uri u = new Uri(url);
            TcpClient c = new TcpClient();
            IAsyncResult r = c.BeginConnect(u.Host, u.Port, null, null);
            if (!r.AsyncWaitHandle.WaitOne(400))
            {
                c.Close();
                return false;
            }
            c.EndConnect(r);
            c.Close();
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static string ReadAll(string path)
    {
        try
        {
            if (!File.Exists(path))
                return null;
            // ⚠️ 去掉可能存在的 BOM（写的时候已经不带，但要防别处写的）
            string s = File.ReadAllText(path, Encoding.UTF8).Trim()
                              .TrimStart('\uFEFF');
            return s.Length == 0 ? null : s;
        }
        catch
        {
            return null;
        }
    }

    private static void WriteAll(string path, string text)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            // ⚠️ **不要 BOM**（`Encoding.UTF8` 在 .NET Framework 上会写 BOM
            //    ⇒ 读回来是「﻿http://…」⇒ Uri 解析失败）
            File.WriteAllText(path, text, new UTF8Encoding(false));
        }
        catch { }
    }

    private static void TryDelete(string path)
    {
        try { if (File.Exists(path)) File.Delete(path); }
        catch { }
    }

    private static void Kill(Process p)
    {
        try { if (p != null && !p.HasExited) p.Kill(); }
        catch { }
    }

    private static void Fail(string msg)
    {
        try
        {
            MessageBox.Show(msg, TITLE, MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        catch
        {
            Console.Error.WriteLine(msg);
        }
    }
}
