# -*- coding: utf-8 -*-
"""界面**全盘巡检**（U111）—— 在真浏览器里把每个页面、每个交互走一遍，
把**控制台异常**全抓出来。

**为什么需要它**（这批 bug 的教训）：

> **JS 的异常是静默的** —— 事件处理函数抛了异常，界面不报错、只是不响应。
> U108（`theaterFieldCn` 当函数调）、U110（注释没闭合 ⇒ `setUnitEntr` 不存在、
> 遍历活的 HTMLCollection）都是这一类：自动化测试测不出来，静态扫也难扫全，
> 只能**在真浏览器里把界面走一遍**。

**用法**（要**系统 Python**，随包 python 没有 pip、装不了 websocket-client）：

```bat
:: ① 起服务（隔离的 appdata，别碰玩家的真存档）
::    （路径**相对仓库**⇒ 换台机器也能跑；中间文件都在 .scratch/ 里）
set UOC2_APPDATA=%CD%\\.scratch\\appdata\\.uoc2
python\\python.exe -u -m save_modifier_web.server --serve --no-window --no-browser

:: ② 跑巡检（另开一个窗口）
python tools\\ui_audit.py http://127.0.0.1:<端口>/?t=<token> 9401
```

**退出码**：0 = 没有异常；1 = 有异常（打印每一条）。

**中间文件在哪**：浏览器的独立 profile 固定在 `<仓库>\\.scratch\\ui_audit_profile`
（**复用**；要全新的先删掉它再跑）、隔离 appdata 在 `<仓库>\\.scratch\\appdata`。
⇒ 两处都在 `.scratch/` 下，**会话结束清空**即可（见《开发上下文》§7 工作方式）。

⚠️ 它只走**界面能点到的主流程** —— 覆盖不到的路径要自己加步骤
（脚本里的 `STEPS` 数组就是清单）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    import websocket
except ImportError:      # pragma: no cover
    print("!! 需要 websocket-client：")
    print("   pip install websocket-client   （随包的 python 没有 pip，")
    print("    用**系统 Python** 跑这个脚本）")
    raise SystemExit(2)

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

#: 仓库根（`tools/` 的上一级）—— 用它推路径，**不写死某台机器的目录**。
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Edge 的**独立 profile**（跟日常浏览隔开）。
#:
#: ⚠️ **固定一个目录反复用**（U172）—— 每次新建一个带随机名的目录，
#:    跑几十次巡检就会堆出**几百 MB 到几 GB** 的垃圾
#:    （实测：131 个 profile 目录 = **4.16 GB**）。
#:    要「全新」状态：**先把这个目录删掉再跑**，**别新建另一个**。
#:
#: ⚠️ 放在仓库的 `.scratch/` 下（已 gitignore、不进包）——
#:    这样换台机器也能跑，而且**回收站删得掉**（工作区外的路径删不掉）。
PROFILE = str(REPO_ROOT / ".scratch" / "ui_audit_profile")

_id = [0]
EVENTS: list = []


def cdp_send(ws, method, params=None):
    _id[0] += 1
    mid = _id[0]
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    return mid


def cdp_eval(ws, expr, timeout=120):
    mid = cdp_send(ws, "Runtime.evaluate",
                   {"expression": expr, "awaitPromise": True, "returnByValue": True})
    t0 = time.time()
    while time.time() - t0 < timeout:
        ws.settimeout(max(1, timeout - (time.time() - t0)))
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        if msg.get("method") in ("Runtime.exceptionThrown", "Log.entryAdded",
                                 "Runtime.consoleAPICalled"):
            EVENTS.append(msg)
        if msg.get("id") == mid:
            res = msg.get("result", {})
            if "exceptionDetails" in res:
                return {"__error__": str(res["exceptionDetails"])[:400]}
            return res.get("result", {}).get("value")
    return {"__error__": "timeout"}


# 走查脚本（贴进页面里跑）—— 每一步都包了 try/catch，异常会被记进控制台。
WALK = r"""
  (async () => {
    const sleep = ms => new Promise(r=>setTimeout(r,ms));
    const log = [];
    const step = async (name, fn) => {
      try { await fn(); log.push(name + ' ✓'); }
      catch(e){ log.push(name + ' ✗ ' + (e && e.message ? e.message : String(e))); }
      await sleep(250);
    };
    const u = (VIEW.units||[])[0] || (VIEW.units||[])[1];
    const h = (VIEW.hqs||[])[0];

    await step('概览页', async()=>{ PAGE='overview'; show('overview'); await sleep(900); });
    await step('单位页-渲染', async()=>{ PAGE='units'; show('units'); await sleep(1200); });
    await step('单位页-选单位', async()=>{ if(u) pickUnit(u.id); await sleep(400); });
    await step('单位页-工事等级', async()=>{ if(u) setUnitEntr(u.id, 1); await sleep(300); });
    await step('单位页-行动力', async()=>{ if(u) setUnitAp(u.id, 2); await sleep(300); });
    await step('单位页-移动力', async()=>{ if(u){ const el=document.getElementById('in_mp_'+u.id);
      if(el){ el.value='5'; el.dispatchEvent(new Event('input',{bubbles:true})); } } await sleep(300); });
    await step('单位页-显示所有特种兵', async()=>{ toggleFullPool(); await sleep(500); });
    /* ⚠️ **U186 回归**：国籍分组的折叠状态**读写用的键必须一致**。
       以前写用字符串键、读用整个对象 ⇒ 查 `SEL.poolOpen['[object Object]']`
       ⇒ 永远折叠 ⇒ **一个都点不开**，而这一步以前只调 `toggleFullPool()`、
       根本不验证 ⇒ 这个 bug 一直没被抓到。 */
    await step('单位页-展开国籍分组', async()=>{
      const heads = document.querySelectorAll('#udetail .grphead');
      if(!heads.length) throw new Error('没有国籍分组（显示所有特种兵 没开？）');
      const before = heads[0].className.indexOf('closed')>=0;
      heads[0].click();
      await sleep(500);
      const after = document.querySelector('#udetail .grphead');
      if(!after) throw new Error('点完国籍分组，详情区没了');
      const opened = after.className.indexOf('closed')<0;
      const body = after.nextElementSibling;
      const vis = body && body.style.display!=='none';
      if(before && !opened) throw new Error('点了国籍分组还是折叠的（折叠状态读写键不一致）');
      if(!vis) throw new Error('国籍分组展开标记对了，但内容仍然隐藏');
      if(after) after.click();          /* 点回去，别把状态留给后面的步骤 */
      await sleep(400);
    });
    /* ⚠️ **候选池搜索框**：真敲字 ⇒ 真过滤 ⇒ 分组自动展开。
       （只看「有搜索框」不够 —— 必须验证**过滤真的发生了**。） */
    await step('单位页-候选池搜索', async()=>{
      const box = document.getElementById('poolq');
      if(!box) throw new Error('候选池里没有搜索框（poolq）');
      const body = document.getElementById('poolbody');
      if(!body) throw new Error('候选池体（poolbody）不见了');
      const before = body.querySelectorAll('.pcell').length;
      if(!before) throw new Error('候选池里一个格子都没有（显示所有特种兵 没开？）');
      const first = Object.keys((CATALOG&&CATALOG.spec_types)||{})[0];
      if(!first) throw new Error('目录里没有特种兵类型');
      box.value = first;
      box.dispatchEvent(new Event('input',{bubbles:true}));
      await sleep(400);
      const after = document.querySelectorAll('#poolbody .pcell').length;
      if(after === 0) throw new Error('搜一个真实存在的 type id 反而一个都没了');
      if(after >= before) throw new Error('搜索后格子数没减少（过滤没生效）');
      /* 搜到的分组必须**展开**（否则搜到了却藏在折叠组里看不见） */
      const hidden = Array.from(document.querySelectorAll('#poolbody .grpbody'))
        .filter(b=>b.style.display==='none').length;
      if(hidden) throw new Error('有搜索词时分组仍是折叠的（搜到了看不见）');
      box.value = '';
      box.dispatchEvent(new Event('input',{bubbles:true}));
      await sleep(400);
      const restored = document.querySelectorAll('#poolbody .pcell').length;
      if(restored < before) throw new Error('清空搜索后格子没回来');
    });
    await step('单位页-隐藏所有特种兵', async()=>{ toggleFullPool(); await sleep(400); });
    await step('单位页-加特种兵', async()=>{
      const pool = unitPoolFor(u); if(!pool || !pool.candidates.length) return;
      addSpec(u.id, pool.candidates[0]); await sleep(400); });
    await step('单位页-卸特种兵', async()=>{
      const specs = projectedSpecs(u); const last = specs[specs.length-1];
      if(last) removeSpec(u.id, last.type, last.idx); await sleep(400); });
    await step('单位页-改名框', async()=>{ if(u) renameUnit(u.id); await sleep(300); });
    await step('总部页-渲染', async()=>{ PAGE='hqs'; show('hqs'); await sleep(1000); });
    await step('总部页-选总部', async()=>{ if(h) pickHq(h.id); await sleep(400); });
    await step('总部页-切标签', async()=>{ pickHqTab('fp'); await sleep(400); });
    await step('总部页-切回标签', async()=>{ pickHqTab('mx'); await sleep(400); });
    await step('总部页-卡车', async()=>{ if(h) hqTrucks(h.id, 4); await sleep(400); });
    await step('总部页-分支等级', async()=>{ if(h) hqBranchLevel(h.id,'intel',1); await sleep(400); });
    await step('总部页-压制', async()=>{ if(h) hqSuppress(h.id,'intel',1); await sleep(400); });
    await step('总部页-兵库加条目', async()=>{ if(h) openHqPoolModal(h.id); await sleep(400);
                                            closeModal(); await sleep(200); });
    await step('总部页-兵库删条目', async()=>{
      const cur = projectedPool(h); if(cur.length) hqPoolRemove(h.id, cur[0]._o); await sleep(400); });
    await step('卡牌页-渲染', async()=>{ PAGE='cards'; show('cards'); await sleep(1200); });
    /* ⚠️ T5：卡牌状态改成了**按钮**（免费/收费、已用/未用，点一下切状态）——
       这里真点一次：① 按钮文字要跟着状态变 ② 待应用里要出现对应编辑。 */
    await step('卡牌页-状态按钮切换', async()=>{
      const sel = '#work .hcard .acts button[onclick*="cardSetFree"]';
      const btn = document.querySelector(sel);
      if(!btn) throw new Error('卡面上找不到「免费/收费」按钮');
      const before = btn.textContent.trim();
      btn.click(); await sleep(500);
      const after = document.querySelector(sel);
      if(!after) throw new Error('点完按钮后卡面上按钮没了');
      if(after.textContent.trim()===before)
        throw new Error('按钮文字没跟着状态变（仍是 ' + before + '）');
      const pend = (PENDING||[]).filter(p=>p.kind==='card_set' && p.params.field==='is_free');
      if(!pend.length) throw new Error('待应用里没有「免费/收费」的改动');
    });
    await step('卡牌页-持续卡已用按钮', async()=>{
      const btn = document.querySelector('#work .hcard .acts button[onclick*="cardSetUsed"]');
      if(!btn) return;          /* 这个存档的手牌里没有持续卡 ⇒ 跳过（不算失败） */
      btn.click(); await sleep(500);
      const pend = (PENDING||[]).filter(p=>p.kind==='card_set' && p.params.field==='used');
      if(!pend.length) throw new Error('待应用里没有「已使用」的改动');
    });
    await step('卡牌页-换牌', async()=>{
      const c=(VIEW.hand||[])[0]; if(c) openCardPickerModal('hand', c.position); await sleep(500);
      closeModal(); await sleep(200); });
    /* ⚠️ **U187 回归**：空降 / 登陆卡（会召唤单位）**不许直接加到手牌**。
       以前没这一步 ⇒ 核心库那边漏了「单位已被召唤过」的检查也没人发现。
       这里**真看 DOM**：手牌选择器里**不能有**还能点的召唤卡（blocked 的 onclick 是 void 0）。 */
    await step('卡牌页-手牌选择器禁掉空降卡', async()=>{
      const c=(VIEW.hand||[])[0]; if(!c) return;
      openCardPickerModal('hand', c.position); await sleep(700);
      const cells = Array.from(document.querySelectorAll('#spick_grid .pcell'));
      if(!cells.length) throw new Error('手牌选择器里一张卡都没有');
      const clickable = cells.filter(el => /para|naval_assault/.test(el.getAttribute('onclick')||''));
      if(clickable.length) throw new Error(clickable.length + ' 张空降/登陆卡还能点（U187 回归）');
      const greyed = cells.filter(el => /blocked/.test(el.className||''));
      if(!greyed.length) throw new Error('一张卡都没被灰掉（U187 回归）');
      closeModal(); await sleep(200);
    });
    await step('商店页-渲染', async()=>{ PAGE='store'; show('store'); await sleep(1200); });
    await step('商店页-上架新商品', async()=>{ openStoreAddModal(); await sleep(500);
                                              closeModal(); await sleep(200); });
    /* U139：上架一条之后，在表格里改它的价格 ——
       旧写法会发出 `store_set(index=-1)` ⇒ 核心库报错 ⇒ **整批**写不进去。
       这里断言：① 没有负下标的 store_set；② 待上架那条的 entry.price 真的改了。 */
    await step('商店页-上架后调价', async()=>{
      const first = projectedStore()[0];
      if(!first) return;
      storeAddEquip('armor','german');
      await sleep(500);
      const rows = projectedStore();
      const nr = rows[rows.length-1];
      if(!nr || nr.index>=0) return;              /* 没有待上架行 ⇒ 跳过 */
      const el = document.getElementById('st_p_'+nr.e.front+'_'+nr.e.sub+'_'+nr.index);
      if(!el) throw new Error('待上架那行没有价格输入框');
      el.value='23';
      el.dispatchEvent(new Event('input',{bubbles:true}));
      await sleep(500);
      const bad = PENDING.filter(p=>p.kind==='store_set' && p.params && p.params.index<0);
      if(bad.length) throw new Error('发出了负下标的 store_set ⇒ 整批会被拦');
      const adds = PENDING.filter(p=>p.kind==='store_add');
      if(!adds.length) throw new Error('待上架那条不见了');
      const ep = adds[adds.length-1].params.entry;
      if(Number(ep.price)!==23) throw new Error('待上架那条的价格没被改成 23（实际 '+ep.price+'）');
    });
    await step('商店页-下架', async()=>{
      const rows=projectedStore(); const r=rows[0];
      if(r) storeRemove(r.e.front, r.e.sub, r.index); await sleep(400); });
    await step('战区资产页-渲染', async()=>{ PAGE='theater'; show('theater'); await sleep(1000); });
    await step('战区资产页-改次数', async()=>{
      const a=(VIEW.theater_assets||[])[0]; if(!a) return;
      theaterSet(a.asset,'to_use',(a.to_use||0)+1); await sleep(300);
      theaterSet(a.asset,'uses_turn',(a.uses_turn||1)+1); await sleep(300); });
    await step('战区资产页-加一项', async()=>{
      const c=(VIEW.theater_candidates||[])[0]; if(c) openTheaterAddModal(c.asset);
      await sleep(500); closeModal(); await sleep(200); });
    await step('战役页-渲染', async()=>{ PAGE='campaign'; show('campaign'); await sleep(1200); });
    /* ⚠️ **U188 回归**：废墟块必须在**路线图下面**（用户 2026-11-25：
       「目前修改废墟功能埋在战役最低下，太难发现了」⇒ 挪到战役第二行）。
       静态断言只比对源码字面量、不验行为（U186 实锤：一条断言把 bug 锁了 46 个 commit）
       ⇒ 这里**真看 DOM 顺序**：废墟块的**上一个兄弟**是路线图块、
       **下一个兄弟**是两列格子（可选场景 / 总部）。
       ⚠️ `ruinsBox()` 在**没有废墟时返回空串** ⇒ 存档没废墟就跳过；
          但「有废墟却没渲染出来」是回归 ⇒ 要报错。 */
    await step('战役页-废墟块在路线图下面', async()=>{
      /* 战役明细是**异步**拉的（`loadCampaignDetail()`）⇒ 先等它到位再断言 */
      for(let i=0;i<30 && !CDETAIL;i++) await sleep(200);
      const ruins = (CDETAIL && CDETAIL.ruins) || [];
      const box = document.querySelector('#ruinsbox');
      if(!box){
        if(ruins.length) throw new Error('存档里有 '+ruins.length+' 座废墟，但废墟块没渲染（U188 回归）');
        return;                       /* 这个存档本来就没有废墟 ⇒ 无从验证 */
      }
      const prev = box.previousElementSibling;
      const next = box.nextElementSibling;
      if(!prev || !/路线图|Roadmap/.test(prev.textContent||''))
        throw new Error('废墟块上面不是路线图块（U188 回归）');
      if(!next || String(next.className).indexOf('cols-wide')<0)
        throw new Error('废墟块不在「可选场景/总部」两列格子上面（U188 回归）');
      const r = box.getBoundingClientRect();
      if(r.height<=0) throw new Error('废墟块高度为 0（不可见）');
      const pr = prev.getBoundingClientRect();
      if(pr.top > r.top) throw new Error('废墟块在路线图块上面（U188 回归）');
    });
    await step('回概览', async()=>{ PAGE='overview'; show('overview'); await sleep(900); });
    return log;
  })()
"""


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    url = sys.argv[1]
    port = int(sys.argv[2])
    save_id = sys.argv[3] if len(sys.argv) > 3 else "campaigns%2Fwest.usg"

    os.makedirs(PROFILE, exist_ok=True)
    proc = subprocess.Popen([
        EDGE, "--remote-debugging-port=%d" % port,
        "--user-data-dir=%s" % PROFILE,
        "--window-size=1600,1000", "--no-first-run", "--no-default-browser-check",
        url])
    tgt = None
    for _ in range(60):
        time.sleep(1)
        try:
            raw = urllib.request.urlopen(
                "http://127.0.0.1:%d/json/list" % port, timeout=5).read()
            for t in json.loads(raw.decode("utf-8")):
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    tgt = t
                    break
            if tgt:
                break
        except Exception:
            continue
    if not tgt:
        print("!! 拿不到调试目标（Edge 没起来？）")
        proc.terminate()
        return 1
    ws = websocket.create_connection(tgt["webSocketDebuggerUrl"], timeout=30,
                                     max_size=20 * 1024 * 1024)
    cdp_eval(ws, "1")
    cdp_send(ws, "Runtime.enable")
    cdp_send(ws, "Log.enable")
    for _ in range(40):
        info = cdp_eval(ws, "(() => ({has: typeof openSave}))()")
        if isinstance(info, dict) and info.get("has") == "function":
            break
        time.sleep(0.5)

    cdp_eval(ws, """
      (async () => {
        const sleep = ms => new Promise(r=>setTimeout(r,ms));
        openSave('%s');
        for(let i=0;i<80;i++){ await sleep(250); if(window.VIEW && VIEW.units) break; }
        for(let i=0;i<80;i++){ await sleep(250); if(window.CATALOG) break; }
        return true;
      })()
    """ % save_id)

    log = cdp_eval(ws, WALK)
    print("=== 走查步骤 ===")
    if isinstance(log, dict):
        print("  脚本整体失败：", json.dumps(log, ensure_ascii=False)[:400])
    for line in (log or []):
        print("  ", line)

    time.sleep(1)
    print("\n=== 控制台异常 / 报错 ===")
    seen = set()
    n = 0
    for ev in EVENTS:
        m = ev.get("method")
        if m == "Runtime.exceptionThrown":
            d = ev["params"]["exceptionDetails"]
            txt = d.get("exception", {}).get("description") or d.get("text")
            key = (txt, d.get("url"), d.get("lineNumber"))
            if key in seen:
                continue
            seen.add(key)
            n += 1
            print("  [%d] %s" % (n, (txt or "")[:300]))
            print("      %s:%s" % ((d.get("url") or "").split("/")[-1], d.get("lineNumber")))
        elif m == "Log.entryAdded":
            e = ev["params"]["entry"]
            if e.get("level") == "error":
                key = (e.get("text"), e.get("url"))
                if key in seen:
                    continue
                seen.add(key)
                n += 1
                print("  [%d] %s  (%s)" % (n, e.get("text", "")[:250],
                                           (e.get("url") or "").split("/")[-1]))
        elif m == "Runtime.consoleAPICalled":
            p = ev["params"]
            if p.get("type") in ("error", "assert"):
                txt = " ".join(str(a.get("value", a.get("description", "")))
                               for a in p.get("args", []))
                if (txt,) in seen:
                    continue
                seen.add((txt,))
                n += 1
                print("  [%d] console.%s: %s" % (n, p.get("type"), txt[:250]))
    print("\n共 %d 条异常" % n)

    ws.close()
    proc.terminate()
    return 0 if n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
