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
// ⚠️⚠️ **v1.4.2：退出判定改了** ——
// 以前是「**被拉起的那个 Edge 进程**退出 ⇒ 用户关了窗口 ⇒ 杀服务」。
// 但 Edge 启动 `--app` 时**首个进程会自己退出**（relaunch —— 浏览器进程重启，
// 而**窗口照常开着**、服务照常收到请求；实测 0.5 秒就退出、rc=0）
// ⇒ 启动器**误判**成「用户关了窗口」⇒ **把服务杀了**
// ⇒ 首次打开直接「无法访问此网站」、写回时报 "Failed to fetch"。
//
// ⇒ 改成：**不再看 Edge 的进程**，改为**等 python 服务进程自己退出**。
//    服务端按**客户端心跳**判活（前端定时器发的，与操作无关）：
//    客户端关窗 ⇒ beacon 通知 ⇒ 服务立刻退；浏览器崩了 ⇒ 心跳超时 ⇒ 也退。
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
[assembly: AssemblyVersion("1.4.2.0")]
[assembly: AssemblyFileVersion("1.4.2.0")]

internal static class Launcher
{
    private const string TITLE = "统一指挥 2 存档修改器";

    private static string Root
    {
        get { return AppDomain.CurrentDomain.BaseDirectory; }
    }

    private static string RuntimeData
    {
        get { return Path.Combine(Root, "data", "runtime"); }
    }

    private static string LogFile
    {
        get { return Path.Combine(Root, "data", "logs", "modifier.log"); }
    }

    private static string EdgeProfile
    {
        get { return Path.Combine(Root, "data", "cache", "edge"); }
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

        string urlFile = Path.Combine(RuntimeData, "server.url");

        // ① 已经在跑？⇒ 只把窗口叫出来
        string old = ReadAll(urlFile);
        if (old != null && Alive(old))
        {
            string existingEdge = FindEdge();
            Process existingBrowser;
            string existingReason = null;
            if (existingEdge != null && TryLaunchEdge(existingEdge, old,
                                                       out existingBrowser,
                                                       out existingReason))
            {
                // The running server owns its rendezvous file.
                // ⚠️ **v1.4.2：不要等这个 Edge 进程退出** ——
                // Edge 的首个进程会自己退出（relaunch，窗口照常开着）
                // ⇒ 等它返回 = 这个启动器白退（而且没有任何好处：
                // 服务是**另一个**启动器起的，它自己会管服务的生死）。
                Log("[launcher] 已有服务在跑 ⇒ 只把窗口叫出来（不重复起服务）");
                return 0;
            }
            Fail(existingEdge == null
                ? "找不到 Microsoft Edge，无法打开修改器。"
                : "Microsoft Edge 启动失败：\r\n" + existingReason);
            return 1;
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
            Log("[launcher] 60 秒内没拿到服务地址 ⇒ 放弃");
            Kill(proc);
            TryDelete(urlFile);
            Fail("服务没能启动（60 秒内没拿到地址）。\r\n\r\n日志在：\r\n"
               + LogFile);
            return 1;
        }
        if (!WriteAll(urlFile, url))
        {
            Log("[launcher] 写不了 server.url ⇒ 放弃");
            Kill(proc);
            TryDelete(urlFile);
            Fail("无法写入启动器运行状态：\r\n" + urlFile);
            return 1;
        }
        Log("[launcher] 服务已启动：" + url);

        // ③ 只用独立 profile 启动 Edge；失败不得回退到默认浏览器
        string edge = FindEdge();
        Process browser;
        string reason = null;
        if (edge == null || !TryLaunchEdge(edge, url, out browser, out reason))
        {
            Log("[launcher] Edge 启动失败 ⇒ 杀服务");
            Kill(proc);
            TryDelete(urlFile);
            Fail(edge == null
                ? "找不到 Microsoft Edge，无法打开修改器。"
                : "Microsoft Edge 启动失败：\r\n" + reason);
            return 1;
        }
        Log("[launcher] Edge 已拉起（pid=" + browser.Id + "）");

        // ④ ⚠️ **v1.4.2：不再 `browser.WaitForExit()`** ——
        //    Edge 的首个进程会自己退出（relaunch，窗口照常开着）⇒
        //    等它返回就等于「服务立刻自杀」（v1.4.1 的实测故障）。
        //    ⇒ 改为**等 python 服务进程自己退出**：服务端按**客户端心跳**判活
        //    （关窗 ⇒ beacon ⇒ 立刻退；浏览器崩了 ⇒ 心跳超时 ⇒ 也退）。
        try
        {
            proc.WaitForExit();
            Log("[launcher] 服务进程已退出（码=" + proc.ExitCode + "）");
        }
        catch (Exception ex)
        {
            Log("[launcher] 等服务退出时出错：" + ex.Message);
        }
        finally
        {
            Kill(proc);
            TryDelete(urlFile);
        }
        return 0;
    }

    // ---------------------------------------------------------------- 小工具

    /// <summary>写一行到日志（**每次杀服务都记** ⇒ 下次出问题能直接看出是谁杀的）。</summary>
    private static void Log(string msg)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(LogFile));
            File.AppendAllText(LogFile,
                "[launcher] " + DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
                + "  " + msg + Environment.NewLine,
                new UTF8Encoding(false));
        }
        catch { }
    }

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

    private static bool TryLaunchEdge(string edge, string url,
                                      out Process browser, out string reason)
    {
        browser = null;
        reason = null;
        try
        {
            Directory.CreateDirectory(EdgeProfile);
            ProcessStartInfo psi = new ProcessStartInfo(edge);
            psi.Arguments =
                "--app=" + url +
                " --user-data-dir=\"" + EdgeProfile + "\"" +
                " --no-first-run --no-default-browser-check" +
                " --force-device-scale-factor=1" +
                " --window-size=1500,940" +
                " --disable-features=Translate,msEdgeSidebarV2,msEdgeShoppingAssistant";
            psi.UseShellExecute = false;
            browser = Process.Start(psi);
            if (browser == null)
            {
                reason = "进程未能创建。";
                return false;
            }
            return true;
        }
        catch (Exception ex)
        {
            reason = ex.Message;
            return false;
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

    private static bool WriteAll(string path, string text)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            // ⚠️ **不要 BOM**（`Encoding.UTF8` 在 .NET Framework 上会写 BOM
            //    ⇒ 读回来是「﻿http://…」⇒ Uri 解析失败）
            File.WriteAllText(path, text, new UTF8Encoding(false));
            return true;
        }
        catch
        {
            return false;
        }
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
