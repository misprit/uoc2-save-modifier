"""路径定位：游戏数据目录、存档目录、游戏包目录。

核心库**不读配置文件**也能工作 —— 全部路径靠探测 + 环境变量覆盖。
这样 GUI 那边不用先跑一遍配置向导。

环境变量
--------
* `UOC2_APPDATA` —— 游戏数据目录（默认 `%LOCALAPPDATA%\\.uoc2`）
* `UOC2_GAME_DIR` —— 游戏安装目录（默认自动探测）
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "appdata_dir","CorePaths", "APP_DIR_NAME", "config_path", "read_config",
           "write_config", "detect_game_dir", "game_dir_candidates",
           "looks_like_game_dir", "set_game_dir", "steam_libraries",
           "modifier_home", "backup_dir", "modifier_data_dir",
           "legacy_config_path", "modifier_imports_dir", "legacy_imports_dir",
           "modifier_log_path", "legacy_log_path", "modifier_profile_dir",
           "legacy_profile_dir", "modifier_fallback_backup_dir"]

APP_DIR_NAME = ".uoc2"
#: 修改器专属数据目录；新写入不得污染游戏数据根目录。
MODIFIER_DIR_NAME = "modifier"
#: 旧导入目录名（只读兼容；新导入目录位于 modifier/ 下）。
LEGACY_IMPORTS_DIR_NAME = "modifier_imports"
#: **备份存档**目录名（放在**修改器所在目录**下 —— U109）
BACKUP_DIR_NAME = "bak"


def appdata_dir() -> Path:
    """游戏数据目录（默认 `%LOCALAPPDATA%\\.uoc2`；`UOC2_APPDATA` 可覆盖）。

    ⚠️ **U126**：服务端要核对「存档路径有没有越界」时**只需要这个目录**
    —— 存档根 = `<游戏数据目录>/save`。
    ⇒ 单独暴露一个轻量入口，**不用**为了拿存档根去探测游戏安装目录
    （`CorePaths.discover()` 会去查注册表 + 扫 Steam 库，慢）。
    """
    return _default_appdata()


def modifier_home() -> Path:
    """修改器自己的「家目录」= **装了它的那个目录**（exe / run.bat 所在处）。

    ⚠️ `src/save_modifier_core/paths.py` 往上两级就是包根 ——
    发布包里 = 解压出来的那个目录（exe 就在那儿）⇒
    备份放 `<家目录>/bak/` ⇒ 玩家在**修改器旁边**就能找到（U109）。
    """
    return Path(__file__).resolve().parents[2]


def modifier_data_dir() -> Path:
    """修改器的新数据根目录：`<游戏数据目录>/modifier/`。

    纯路径 helper，不创建目录；调用方决定何时实际写入。
    """
    return appdata_dir() / MODIFIER_DIR_NAME


def modifier_fallback_backup_dir() -> Path:
    """新布局的备用备份目录：`<appdata>/modifier/bak/`。

    仅提供未来写回管线接线点；当前 writer 仍使用兼容的旧 helper。
    """
    return modifier_data_dir() / BACKUP_DIR_NAME


def fallback_backup_dir() -> Path:
    """**旧**备用备份目录：`<游戏数据目录>/bak/`（U132）。

    ⚠️ **为什么不用「存档旁边」**：游戏只扫存档目录里的 `*.usg`
    ⇒ 备份放那儿会被**游戏当成存档**列出来（U109 的教训）。
    ⇒ 兜底也放在**游戏数据目录**里（游戏不扫那儿）。

    ⚠️ 这个目录**建不出来**时 ⇒ 宁可**拒绝写盘**（没有备份就不写），
    也不要把备份丢给游戏（外部审阅报告 P2-13）。
    """
    return appdata_dir() / BACKUP_DIR_NAME


def backup_dir() -> Path:
    """**备份存档**目录：`<修改器所在目录>/bak/`（U109）。

    ⚠️ **为什么不再放在存档旁边**：
    * 游戏只扫存档目录里的 `*.usg` ⇒ 备份放那儿会被**游戏当成存档**列出来
      （修改器自己过滤掉了 `_BACKUP`，**游戏可不管**）⇒ 玩家可能手抖加载了备份；
    * 改一次多一个文件 ⇒ 存档目录越来越乱。
    ⇒ 统一放 `<修改器目录>/bak/`：**游戏看不到、也好找**。

    环境变量 `UOC2_BAK_DIR` 可覆盖（测试用）。
    """
    env = os.environ.get("UOC2_BAK_DIR")
    if env:
        return Path(env).expanduser()
    return modifier_home() / BACKUP_DIR_NAME

#: 修改器自己的设置文件（放在**游戏数据目录**下，不进存档目录）
#:
#: ⚠️ **只存设置**，绝不写存档内容 —— 存档层（L1–L5）一个字都不动。
CONFIG_FILENAME = "modifier_config.json"

#: 游戏安装目录的候选位置（按优先级）
_GAME_DIR_CANDIDATES = (
    r"D:\SteamLibrary\steamapps\common\Unity of Command 2",
    r"C:\Program Files (x86)\Steam\steamapps\common\Unity of Command 2",
    r"C:\Program Files\Steam\steamapps\common\Unity of Command 2",
    r"D:\Program Files (x86)\Steam\steamapps\common\Unity of Command 2",
)


def _default_appdata() -> Path:
    env = os.environ.get("UOC2_APPDATA")
    if env:
        return Path(env).expanduser()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def _steam_root() -> Path | None:
    """从注册表里找 Steam 的安装目录（Windows）。"""
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:      # pragma: no cover - 非 Windows
        return None
    for hive, key in ((winreg.HKEY_CURRENT_USER,
                       r"Software\Valve\Steam"),
                      (winreg.HKEY_LOCAL_MACHINE,
                       r"SOFTWARE\WOW6432Node\Valve\Steam")):
        try:
            with winreg.OpenKey(hive, key) as k:
                val, _ = winreg.QueryValueEx(k, "SteamPath")
                return Path(val)
        except OSError:
            continue
    return None


def steam_libraries() -> list[Path]:
    """Steam 的**所有**库目录（含自定义库）。

    ⚠️ 只查默认库会漏掉装在别的盘的 Steam —— 注册表里只有一个 `SteamPath`，
    而库是另一回事（`steamapps/libraryfolders.vdf` 里列着全部库，
    但**这个文件不一定存在**，非标准安装下常常没有 ⇒ 还要兜底扫常见库位置）。

    ⚠️ **U122：文件名是 `libraryfolders.vdf`（`.vdf`）** —— 原来写成了
    `.vcf` ⇒ **这个文件从来就没被读到过** ⇒ 装在别的盘的库**一个都发现不了**
    （外部审阅报告 P1-6；本机实测也只有 `.vdf`）。
    
    字节码依据：`paths.pyc::all_package_dirs` ⇒ 游戏自己的包目录是
    `_mod_packages_dirs + [_user_packages_dir] + [_game_package_dir]`；
    游戏本体目录由**安装位置**决定（`_Paths.__init__`）。
    """
    libs: list[Path] = []
    root = _steam_root()
    if root is not None:
        libs.append(root)
        for vdf in (root / "steamapps" / "libraryfolders.vdf",
                    root / "config" / "libraryfolders.vdf"):
            try:
                text = vdf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in re.finditer(r'"path"\s*"([^"]+)"', text):
                try:
                    p = Path(m.group(1).replace("\\", "\\"))
                except Exception:
                    continue
                if p.is_dir() and p not in libs:
                    libs.append(p)
    # 兜底：常见库位置（libraryfolders.vdf 缺失时）
    for extra in (Path("D:/SteamLibrary"), Path("D:/Steam"),
                  Path("E:/SteamLibrary"), Path("C:/SteamLibrary")):
        if extra.is_dir() and extra not in libs:
            libs.append(extra)
    return libs


def library_game_dirs() -> list[tuple]:
    """在各个 Steam 库里找「像游戏本体」的目录。

    ⚠️ **不靠 appmanifest 的 `installdir`** —— 实测那个字段和磁盘上的文件夹名
    可能对不上（本机 manifest 写的是 `Unity of Command II`，
    磁盘上却是 `Unity of Command 2`）⇒ 直接扫 `steamapps/common/*`，
    用「里面有 `_packages` 或 `lib/uoc2`」判定。
    """
    out: list[tuple] = []
    for lib in steam_libraries():
        common = lib / "steamapps" / "common"
        if not common.is_dir():
            continue
        try:
            for d in sorted(common.iterdir()):
                if d.is_dir() and looks_like_game_dir(d):
                    out.append(("Steam 库", d))
        except OSError:
            continue
    return out



def _candidate_game_dirs() -> list[Path]:
    out: list[Path] = []
    cfg = read_config().get("game_dir")
    if cfg:
        out.append(Path(str(cfg)).expanduser())
    env = os.environ.get("UOC2_GAME_DIR")
    if env:
        out.append(Path(env).expanduser())
    for lib in steam_libraries():
        out.append(lib / "steamapps" / "common" / "Unity of Command 2")
    for _label, p in library_game_dirs():
        out.append(p)
    out.extend(Path(p) for p in _GAME_DIR_CANDIDATES)
    return out
    out.extend(Path(p) for p in _GAME_DIR_CANDIDATES)
    return out


def looks_like_game_dir(p: Path) -> bool:
    """判断一个目录是不是游戏安装目录。

    判定依据（与游戏自己的目录结构一致）：里面有 `_packages` 或 `lib/uoc2`。
    """
    try:
        return (p / "_packages").is_dir() or (p / "lib" / "uoc2").is_dir()
    except OSError:
        return False


#: 旧名保留（内部用）
_looks_like_game_dir = looks_like_game_dir


def config_path() -> Path:
    """新设置路径：`<游戏数据目录>/modifier/modifier_config.json`。"""
    return modifier_data_dir() / CONFIG_FILENAME


def legacy_config_path() -> Path:
    """旧设置路径；仅用于读取，不作为新写入目标。"""
    return appdata_dir() / CONFIG_FILENAME


def _read_config_file(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_config() -> dict:
    """新设置优先；新文件不存在时读取旧设置，失败时返回空字典。"""
    data = _read_config_file(config_path())
    if data is not None:
        return data
    data = _read_config_file(legacy_config_path())
    return data if data is not None else {}


def write_config(data: dict) -> Path:
    """只写新设置路径；不会迁移、删除或覆盖旧设置文件。"""
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p


def modifier_imports_dir() -> Path:
    """新导入副本目录：`<appdata>/modifier/modifier_imports/`；不创建目录。"""
    return modifier_data_dir() / LEGACY_IMPORTS_DIR_NAME


def legacy_imports_dir() -> Path:
    """旧导入副本目录；仅供兼容读取。"""
    return appdata_dir() / LEGACY_IMPORTS_DIR_NAME


def modifier_log_path() -> Path:
    """新日志路径：`<appdata>/modifier/modifier.log`。"""
    return modifier_data_dir() / "modifier.log"


def legacy_log_path() -> Path:
    """旧日志路径；仅供兼容读取。"""
    return appdata_dir() / "modifier.log"


def modifier_profile_dir() -> Path:
    """新 Edge profile 目录：`<appdata>/modifier/edge_profile/`。"""
    return modifier_data_dir() / "edge_profile"


def legacy_profile_dir() -> Path:
    """旧 Edge profile 目录；仅供兼容读取。"""
    return appdata_dir() / "edge_profile"


def set_game_dir(path) -> Path:
    """把游戏本体目录记下来（写设置文件）。

    ⚠️ 只校验「像不像游戏目录」，**不移动任何文件**。
    """
    p = Path(path).expanduser()
    if not p.is_dir():
        raise ValueError("目录不存在：%s" % p)
    if not looks_like_game_dir(p):
        raise ValueError("这个目录不像游戏本体（里面应该有 _packages 或 lib/uoc2）：%s" % p)
    cfg = read_config()
    cfg["game_dir"] = str(p.resolve())
    write_config(cfg)
    return p.resolve()


def game_dir_candidates() -> list[dict]:
    """所有候选游戏目录 + 命中与否 —— 界面用它告诉玩家「都找过哪儿了」。"""
    out = []
    cfg = read_config().get("game_dir")
    if cfg:
        p = Path(str(cfg)).expanduser()
        out.append({"label": "设置文件里指定的", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    env = os.environ.get("UOC2_GAME_DIR")
    if env:
        p = Path(env).expanduser()
        out.append({"label": "环境变量 UOC2_GAME_DIR", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    for lib in steam_libraries():
        p = lib / "steamapps" / "common" / "Unity of Command 2"
        out.append({"label": "Steam 库", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    for _label, p in library_game_dirs():
        out.append({"label": "Steam 库里扫到的", "path": str(p), "ok": True})
    for c in _GAME_DIR_CANDIDATES:
        p = Path(c)
        out.append({"label": "常见安装位置", "path": str(p),
                    "ok": looks_like_game_dir(p)})
    return out


def detect_game_dir() -> Path | None:
    """探测游戏安装目录；找不到返回 None（不报错 —— 存档功能不依赖游戏本体）。

    **优先级（U69）**
    1. 设置文件里用户手动指定的（`<游戏数据目录>/modifier_config.json`）；
    2. 环境变量 `UOC2_GAME_DIR`；
    3. Steam 注册表 → **所有库**（`libraryfolders.vdf`）+ 常见安装位置。

    ⚠️ 设置文件里指的目录要是没了（游戏被移动 / 卸载），**自动忽略它**继续往下找 ——
    否则用户会被一个失效的设置卡住。
    """
    seen: set[Path] = set()
    for cand in _candidate_game_dirs():
        try:
            rp = cand.resolve()
        except OSError:
            continue
        if rp in seen:
            continue
        seen.add(rp)
        if looks_like_game_dir(rp):
            return rp
    return None


def _game_package_dirs(game_dir=None) -> list[Path]:
    """官方包目录（base / dlc1..dlc10）—— 数字序（dlc2 在 dlc10 前面）。"""
    gd = Path(game_dir).expanduser() if game_dir else detect_game_dir()
    if gd is None:
        return []
    gp = Path(gd) / "_packages"
    if not gp.is_dir():
        return []
    try:
        names = list(gp.iterdir())
    except OSError:
        return []
    out = [d for d in names if d.is_dir()]

    def key(p):
        stem = p.name
        if stem.startswith("dlc") and stem[3:].isdigit():
            return (1, int(stem[3:]))
        return (0, 0)

    out.sort(key=key)
    return out


#: UoC2 的 Steam App ID（创意工坊目录按它分）
#:
#: ⚠️ 实证：`steamapps/workshop/content/809230/` 里就是 UoC2 的创意工坊项目；
#: UoC2 的 mod **不自动安装**（玩家手动把 zip 解压覆盖到游戏目录），
#: 所以「已订阅但没装」的 mod 数据修改器也要能读（作为参考数据）。
WORKSHOP_APP_ID = "809230"


def workshop_root(app_id: str = WORKSHOP_APP_ID) -> list:
    """Steam 标准创意工坊目录：`<库>/steamapps/workshop/content/<appid>`。"""
    out = []
    for lib in steam_libraries():
        d = lib / "steamapps" / "workshop" / "content" / app_id
        if d.is_dir():
            out.append(d)
    return out


def workshop_items(app_id: str = WORKSHOP_APP_ID) -> list:
    """创意工坊里的每个项目目录。"""
    out = []
    for root in workshop_root(app_id):
        try:
            for d in sorted(root.iterdir()):
                if d.is_dir():
                    out.append(d)
        except OSError:
            continue
    return out


#: 判定「一个目录/压缩包的根是不是一个**包**」的标志
#:
#: 依据：场景编辑器上传创意工坊时给的是**包路径**
#: （`edit_ctrl.pyc::_update_workshop_item` ⇒ `set_item_content_dir(self._package_path)`）
#: ⇒ 下载下来的内容就是**包的裸文件**。
PACK_MARKERS = ("main.yml", "data", "scenarios", "campaigns", "entity_types",
                "maps", "locale.yml")


def _looks_like_package(names) -> bool:
    """一组相对路径（目录或 zip 内）看起来像「一个包」吗？"""
    tops = set()
    for n in names:
        parts = n.replace("\\", "/").split("/")
        if parts and parts[0]:
            tops.add(parts[0])
    return any(t in PACK_MARKERS for t in tops)


def _dir_package_sources(item) -> list:
    """一个创意工坊项目**目录**里的包。"""
    out = []
    pk = item / "_packages"
    if pk.is_dir():
        try:
            subs = sorted(x for x in pk.iterdir() if x.is_dir())
        except OSError:
            subs = []
        for x in subs:
            out.append({"kind": "dir", "path": x, "pkg": x.name,
                        "prefix": "", "item": item.name})
        if out:
            return out
    # 裸文件形态：项目目录**本身就是**一个包
    try:
        names = [str(x.relative_to(item)).replace("\\", "/")
                 for x in item.rglob("*") if x.is_file()]
    except OSError:
        names = []
    if _looks_like_package(names):
        out.append({"kind": "dir", "path": item, "pkg": item.name,
                    "prefix": "", "item": item.name})
    return out


def _zip_package_sources(zip_path, item_name) -> list:
    """一个创意工坊项目里的 **zip** 里的包。"""
    import zipfile
    out = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = zf.namelist()
    except (OSError, zipfile.BadZipFile):
        return out
    # ① 包在 _packages/<包名>/ 下
    pkgs = []
    for m in members:
        parts = m.replace("\\", "/").split("/")
        if len(parts) >= 3 and parts[0] == "_packages" and parts[1] not in pkgs:
            pkgs.append(parts[1])
    for name in pkgs:
        out.append({"kind": "zip", "path": zip_path, "pkg": name,
                    "prefix": "_packages/%s/" % name, "item": item_name})
    if out:
        return out
    # ② 压缩包**根本身**就是一个包
    if _looks_like_package(members):
        out.append({"kind": "zip", "path": zip_path,
                    "pkg": Path(zip_path).stem, "prefix": "", "item": item_name})
    return out


def workshop_package_sources(app_id: str = WORKSHOP_APP_ID) -> list:
    """创意工坊 mod 里的**包**（裸文件 / 子目录里的包 / 压缩包都认）。

    返回 `[{"kind": "dir"|"zip", "path": Path, "pkg": 包名,
    "prefix": 包内前缀, "item": 项目目录名}]`。
    """
    out = []
    for item in workshop_items(app_id):
        out.extend(_dir_package_sources(item))
        try:
            zips = sorted(item.glob("*.zip"))
        except OSError:
            zips = []
        for z in zips:
            out.extend(_zip_package_sources(z, item.name))
    return out


def not_moddable_rules(game_dir=None) -> list:
    """游戏根 `packages.yml` 的 `not_moddable` 规则。

    ⚠️ **游戏据此把整个 mod 包禁用**（不是只跳过那个文件）：
    `paths.pyc::check_not_moddable` ⇒ 命中就把该包从包列表里剔掉，
    并打一条 "MOD DISABLED (non-moddable content)" 的警告。

    规则长这样（每段一段路径，`*` 匹配任意一段）：
        ["*", "data", "entity_types", "nationalities.yml"]
    """
    gd = Path(game_dir).expanduser() if game_dir else detect_game_dir()
    if gd is None:
        return []
    p = Path(gd) / "packages.yml"
    try:
        from . import yamlio
        data = yamlio.load(p.read_bytes())
    except Exception:
        return []
    rules = (data or {}).get("not_moddable") if isinstance(data, dict) else None
    return list(rules) if isinstance(rules, list) else []


def _rule_matches(rule, pkg: Path) -> bool:
    """一条 `not_moddable` 规则是否命中这个包（包内存在匹配的文件）。"""
    if not isinstance(rule, (list, tuple)) or len(rule) < 2:
        return False
    segs = [str(x) for x in rule[1:]]          # 第一段是包名通配（"*"）
    if not segs:
        return False
    import fnmatch
    cur = pkg
    for seg in segs[:-1]:
        if seg == "*":
            if not cur.is_dir():
                return False
            try:
                hits = [d for d in cur.iterdir() if d.is_dir()]
            except OSError:
                return False
            if not hits:
                return False
            cur = hits[0]
            continue
        cur = cur / seg
        if not cur.is_dir():
            return False
    last = segs[-1]
    if last == "*":
        return cur.is_dir()
    try:
        names = [f.name for f in cur.iterdir()]
    except OSError:
        return False
    return any(fnmatch.fnmatch(n, last) for n in names)


def package_dirs(appdata=None, game_dir=None) -> list[Path]:
    """**包列表**（与游戏一致）：非官方包（用户 `_packages` 里的）→ 官方包。

    ⚠️ 两条规矩（字节码依据 `paths.pyc::_build_package_list`）：
    1. **容器内用 `listdir` 原序**（不是 sorted）—— 同名文件冲突时
       选中的包必须和游戏一致；
    2. 官方包名（base / dlc1..）出现在用户目录里时**跳过**（那是官方包，不是 mod）。
    """
    from .paths import CorePaths as _CP          # 自引用避免循环
    paths = _CP.discover(appdata, game_dir)
    out: list[Path] = []
    game_names = {p.name for p in _game_package_dirs(paths.game_dir)}
    for root in paths.package_roots():
        if not root.is_dir():
            continue
        try:
            names = list(root.iterdir())          # listdir 原序
        except OSError:
            continue
        for d in names:
            if not d.is_dir():
                continue
            if d.name in game_names:              # 官方包名 ⇒ 不算 mod
                continue
            if d not in out:
                out.append(d)
    for d in _game_package_dirs(paths.game_dir):
        if d.is_dir() and d not in out:
            out.append(d)
    return out


def disabled_packages(appdata=None, game_dir=None) -> dict:
    """被游戏禁用的包（`not_moddable` 规则命中）⇒ {包路径: 命中的规则}。"""
    rules = not_moddable_rules(game_dir)
    if not rules:
        return {}
    paths = CorePaths.discover(appdata, game_dir)
    game_dirs = {str(d) for d in _game_package_dirs(paths.game_dir)}
    out = {}
    for pkg in package_dirs(appdata, game_dir):
        # ⚠️ 只查 **mod 包**：游戏的 `check_not_moddable` 只在 mod 目录里 glob，
        #    官方包（base / dlcN）自己就带着那些文件 ⇒ 永远不禁用。
        if str(pkg) in game_dirs:
            continue
        for rule in rules:
            if _rule_matches(rule, Path(pkg)):
                out[str(pkg)] = list(rule)
                break
    return out


@dataclass(frozen=True)
class CorePaths:
    """一组已定位的路径。"""

    uoc2_appdata: Path
    game_dir: Path | None = None

    # ---- 存档目录 ----

    @property
    def save_root(self) -> Path:
        return self.uoc2_appdata / "save"

    @property
    def campaigns_dir(self) -> Path:
        """战役存档目录。"""
        return self.save_root / "campaigns"

    @property
    def games_dir(self) -> Path:
        """独立场景存档目录。"""
        return self.save_root / "games"

    @property
    def old_saves_dir(self) -> Path:
        """（旧名，保留兼容）玩家自建的归档目录。

        ⚠️ **游戏不认这个目录** —— 游戏只读 `campaigns` 与 `games` 两个目录。
        新代码请用 `archive_dirs()`（认存档根下**所有**非 campaigns/games 的目录）。
        """
        return self.save_root / "Old Saves"

    def archive_dirs(self) -> list[Path]:
        """存档根下**除 campaigns / games 以外**的目录（玩家自己整理的归档区）。

        ⚠️ **游戏只认 `campaigns` 与 `games` 两个目录**（实测）⇒ 根下其它目录
        都是玩家自己放的旧存档，**目录名叫什么都行** ⇒ 修改器一律认。
        """
        root = self.save_root
        if not root.is_dir():
            return []
        out: list[Path] = []
        try:
            for d in sorted(root.iterdir()):
                if d.is_dir() and d.name not in ("campaigns", "games"):
                    out.append(d)
        except OSError:
            pass
        return out

    # ---- 游戏包 ----

    @property
    def user_packages_dir(self) -> Path:
        """用户包目录（mod 放这里），**优先级高于游戏包**。"""
        return self.uoc2_appdata / "_packages"

    @property
    def game_packages_dir(self) -> Path | None:
        if self.game_dir is None:
            return None
        return self.game_dir / "_packages"

    def package_roots(self) -> list[Path]:
        """包**容器**目录（**用户包在前**）。

        与游戏自己的 `uoc2.paths.all_package_dirs()` 实测顺序一致：
        `['%LOCALAPPDATA%\\.uoc2\\_packages', '<game>\\_packages']`。
        """
        out: list[Path] = []
        up = self.user_packages_dir
        if up.is_dir():
            out.append(up)
        gp = self.game_packages_dir
        if gp is not None and gp.is_dir():
            out.append(gp)
        return out

    def workshop_packages(self) -> list:
        """创意工坊里的 mod 包（含 zip 里还没解压的）—— **只读，不落盘**。"""
        return workshop_package_sources()

    def packages(self) -> list[Path]:
        """全部**包**目录（用户包在前）—— **与游戏同序**（U70）。

        ⚠️ `_packages/` 是**容器**，真正的包是它下面的子目录：
        游戏侧是 `base` / `dlc1` / … / `dlc10`，用户侧是 mod 目录（如 `fall_blau_2`）。

        ⚠️ **顺序 = 游戏的顺序**（U70）：非官方包 → 官方包；容器内用
        `listdir` 原序（不是 sorted）⇒ 同名文件冲突时选中的包与游戏一致。

        ⚠️ **被游戏禁用的包不出现**（U70）：游戏根 `packages.yml` 的
        `not_moddable` 规则命中的包，游戏整个禁用 ⇒ 修改器也不读它
        （否则会读到游戏里根本不加载的数据）。
        """
        dirs = package_dirs(self.uoc2_appdata, self.game_dir)
        disabled = disabled_packages(self.uoc2_appdata, self.game_dir)
        return [d for d in dirs if str(d) not in disabled]
    # 兼容旧名
    package_dirs = package_roots

    # ---- 构造 ----

    @classmethod
    def discover(cls, appdata: Path | None = None,
                 game_dir: Path | None = None) -> "CorePaths":
        """定位路径。`game_dir=None` 时自动探测；探测失败也不报错。"""
        return cls(
            uoc2_appdata=Path(appdata).expanduser() if appdata else _default_appdata(),
            game_dir=Path(game_dir).expanduser() if game_dir else detect_game_dir(),
        )

    def with_game_dir(self, game_dir: Path | None) -> "CorePaths":
        return CorePaths(uoc2_appdata=self.uoc2_appdata, game_dir=game_dir)
