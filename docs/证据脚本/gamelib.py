"""加载**游戏自己的** voluptuous 校验器 —— 验收的硬标准。

为什么需要这个
------------
「写回后游戏还能不能读」只有一个硬标准：**游戏自己的 schema 通过**。
本模块把游戏 `lib/` 里的校验器模块加载起来（uoc2.state.*.data_validation.*），
让验收脚本可以直接对写回后的存档跑一遍。

三个坑
------
1. **游戏是 .pyc**（`lib/uoc2/**/*.pyc`），但 **magic 与 Python 3.14 一致**
   （`2b 0e 0d 0a`）⇒ 仓库自带的 python 能直接 import。
2. **不能把游戏整个 `lib/` 加进 sys.path** —— 那里的 `numpy/` 是**源码目录**
   （没有编译好的 `_multiarray_umath`）⇒ 一 import 就炸。
   ⇒ 只把需要的子目录（uoc2 / tools / voluptuous / glob2 / greenlet / …）复制到
   临时目录，numpy 用一个**只够 import 的 stub**（校验器只要能 import 成功）。
3. `greenlet` 有 `_greenlet.cp314-win_amd64.pyd` ⇒ **正好是这个 ABI** ⇒ 可以直接用。

用法
----
```python
from gamelib import GameValidators
gv = GameValidators()          # 首次会复制（约 7 MB）+ 加载
gv.validate_save(r"...\\copy.usg")   # -> {"units.yml": (True, ""), ...}
```
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import zipfile
from types import SimpleNamespace

#: 游戏安装目录
GAME_DIR = r"D:\SteamLibrary\steamapps\common\Unity of Command 2"
LIB = os.path.join(GAME_DIR, "lib")
PKG = os.path.join(GAME_DIR, "_packages")
PKGS = ["base"] + ["dlc%d" % i for i in range(1, 11)]

#: 要复制到临时目录的游戏子包（纯 Python + 与本机 ABI 匹配的 .pyd）
COPY_DIRS = ("uoc2", "tools", "voluptuous", "glob2", "greenlet",
             "sortedcontainers", "intervaltree", "pydispatch", "pytweening")

#: 校验器模块（键 = 短名）
MODULES = {
    "campaign": "uoc2.state.campaign.campaign_data_validation",
    "unit": "uoc2.state.entities.data_validation.unit",
    "hq": "uoc2.state.entities.data_validation.hq",
    "card": "uoc2.state.entities.data_validation.card",
    "force_pool": "uoc2.state.entities.data_validation.force_pool",
    "scenario": "uoc2.state.scenario.scenario_data_validation",
    "game": "uoc2.state.game.game_data_validation",
}

#: numpy stub —— 校验器只要能 import 成功；真用到 numpy 的函数才会露馅
NUMPY_STUB = """int8=int; int16=int; int32=int; int64=int; uint8=int; uint16=int
intp=int; intc=int; int_=int
float16=float; float32=float; float64=float; float_=float
complex64=complex; complex128=complex
bool_=bool; bool8=bool
integer=int; floating=float; number=(int, float)
class ndarray(list):
    pass
def array(x, *a, **k):
    return list(x)
def zeros(n, *a, **k):
    return [0] * n
def ones(n, *a, **k):
    return [1] * n
def isfinite(x):
    return x == x and abs(x) != float('inf')
class _Err:
    def __getattr__(self, n):
        return _Err()
    def __call__(self, *a, **k):
        return _Err()
errstate = _Err()
"""


def _ensure_lib(workdir: str) -> str:
    """把游戏需要的子包复制到 `workdir` 并把它挂进 `sys.path`。

    ⚠️ **不能把游戏整个 `lib/` 挂上去** —— 那里的 `numpy/` 是源码目录
    （没有编译好的 `_multiarray_umath`）⇒ 一 import 就炸。
    ⇒ 只复制 `uoc2 / tools / voluptuous / glob2 / greenlet / …`，
    numpy 用一个**只够 import 的 stub**。
    """
    os.makedirs(workdir, exist_ok=True)
    for d in COPY_DIRS:
        src = os.path.join(LIB, d)
        dst = os.path.join(workdir, d)
        if os.path.isdir(src) and not os.path.isdir(dst):
            shutil.copytree(src, dst)
    np_dir = os.path.join(workdir, "numpy")
    os.makedirs(np_dir, exist_ok=True)
    stub = os.path.join(np_dir, "__init__.py")
    # ⚠️ **无条件重写** —— 旧版 stub 可能没有 linalg（scenario / game 校验器要用）
    with open(stub, "w", encoding="utf-8") as f:
        f.write(NUMPY_STUB)
        f.write("from . import linalg  # noqa: E402,F401\n")
    # numpy.linalg —— scenario / game 校验器会 import 到
    linalg = os.path.join(np_dir, "linalg")
    os.makedirs(linalg, exist_ok=True)
    linalg_init = os.path.join(linalg, "__init__.py")
    with open(linalg_init, "w", encoding="utf-8") as f:
        f.write("def norm(x, *a, **k):\n    return x\n"
                "class LinAlgError(Exception):\n    pass\n")
    if workdir not in sys.path:
        sys.path.insert(0, workdir)
    return workdir


class _TypeTable:
    """类型表的对象形态 —— 游戏里 `campaign_doc.unit_types` 就是这种东西。

    校验器要的是 `campaign_doc.unit_types.id_validation_schema()`
    （= 「值必须是类型表里的键」）。
    """

    def __init__(self, d):
        self._d = d or {}

    def id_validation_schema(self):
        from voluptuous import In
        return In(self._d)

    def __contains__(self, k):
        return k in self._d

    def __len__(self):
        return len(self._d)

    def get(self, k, default=None):
        return self._d.get(k, default)

    def __getattr__(self, n):
        return self._d.get(n)


class _CampaignDocStub:
    """游戏校验器要的「上下文对象」。

    只提供校验器真正用到的几个属性：六张类型表 + `id_validation_schema()`。
    """

    def __init__(self, ctx):
        self.unit_types = _TypeTable(ctx.unit_types)
        self.hq_types = _TypeTable(ctx.hq_types)
        self.card_types = _TypeTable(ctx.card_types)
        self.specialist_types = _TypeTable(ctx.specialist_types)
        self.nationality_types = _TypeTable(ctx.nationality_types)
        self.faction_types = _TypeTable(ctx.faction_types)

    def id_validation_schema(self):
        from voluptuous import Schema
        return Schema(lambda v: v is not None)


#: 模块导入时就把游戏 lib 准备好（这样 `import gamelib` 之后 `voluptuous` 等可用）
import tempfile as _tempfile  # noqa: E402
_DEFAULT_WORKDIR = os.path.join(_tempfile.gettempdir(), "uoc2_gamelib")
_ensure_lib(_DEFAULT_WORKDIR)


class GameValidators:
    """游戏自己的校验器 + 实体类型上下文。"""

    def __init__(self, workdir: str | None = None):
        import tempfile
        self.workdir = workdir or os.path.join(tempfile.gettempdir(), "uoc2_gamelib")
        _ensure_lib(self.workdir)
        self.modules = {}
        for key, mod in MODULES.items():
            try:
                self.modules[key] = importlib.import_module(mod)
            except Exception as exc:          # 某个模块缺依赖 ⇒ 记下来，不影响别的
                self.modules[key] = None
                self._errors = getattr(self, "_errors", [])
                self._errors.append("%s -> %s: %s" % (mod, type(exc).__name__, exc))
        self.ctx = self._make_ctx()

    # ---- 准备 ----
    def _prepare(self):
        _ensure_lib(self.workdir)

    # ---- 实体类型上下文（校验器要的类型表）----
    def _make_ctx(self) -> SimpleNamespace:
        import yaml

        def load_dir(sub):
            out = {}
            for pkg in PKGS:
                d = os.path.join(PKG, pkg, "data", "entity_types", sub)
                if not os.path.isdir(d):
                    continue
                for f in sorted(os.listdir(d)):
                    if not f.endswith(".yml"):
                        continue
                    try:
                        with open(os.path.join(d, f), encoding="utf-8") as fh:
                            raw = yaml.safe_load(fh.read())
                    except Exception:
                        continue
                    if isinstance(raw, dict):
                        out[f[:-4]] = raw
            return out

        def load_single(name):
            for pkg in PKGS:
                fp = os.path.join(PKG, pkg, "data", "entity_types", name)
                if os.path.isfile(fp):
                    import yaml
                    with open(fp, encoding="utf-8") as fh:
                        return yaml.safe_load(fh.read())
            return None

        return SimpleNamespace(
            unit_types=load_dir("unit_types"),
            hq_types=load_dir("hq_types"),
            specialist_types=load_dir("specialists"),
            card_types=load_dir("cards"),
            nationality_types=load_single("nationalities.yml"),
            faction_types=load_single("factions.yml"),
            general_types=None,
        )

    # ---- 校验 ----
    def validate_save(self, save_path: str) -> dict:
        """对存档里的**每张表**跑一遍游戏自己的 schema。

        返回 `{条目名: (通过?, 说明)}`。
        """
        import yaml
        res: dict = {}
        with zipfile.ZipFile(save_path, "r") as zf:
            names = zf.namelist()

            def data_of(entry):
                try:
                    return yaml.safe_load(zf.read(entry))
                except Exception as exc:
                    return exc

            cam = self.modules.get("campaign")
            um = self.modules.get("unit")
            hm = self.modules.get("hq")
            cm = self.modules.get("card")
            sm = self.modules.get("scenario")
            gm = self.modules.get("game")

            def run(label, entry, fn, *args):
                if fn is None:
                    res[label] = (None, "校验器模块没加载成功")
                    return
                if entry not in names:
                    res[label] = (None, "存档里没有这个条目")
                    return
                data = data_of(entry)
                if isinstance(data, Exception):
                    res[label] = (False, "YAML 解析失败：%s" % data)
                    return
                try:
                    fn(data, *args)
                    res[label] = (True, "")
                except Exception as exc:
                    res[label] = (False, "%s: %s" % (type(exc).__name__, str(exc)[:300]))

            if cam:
                run("根 units.yml", "units.yml", cam.campaign_units_schema, self.ctx)
                run("根 hqs.yml", "hqs.yml", cam.campaign_hqs_schema, self.ctx)
                run("根 store.yml", "store.yml", cam.campaign_store_schema, self.ctx)
                run("根 main.yml", "main.yml", cam.campaign_schema, self.ctx)
                run("document/units.yml", "document/units.yml", cam.doc_units_schema, self.ctx)
                run("document/hqs.yml", "document/hqs.yml", cam.doc_hqs_schema, self.ctx)
            if cm:
                run("根 cards.yml", "cards.yml", cm.cards_schema, self.ctx)
            # 战斗目录（L3）：按 scenario 分组校验
            for entry in names:
                if entry.startswith("games/") and entry.endswith("/units.yml"):
                    run(entry, entry, um.units_schema, False, self.ctx) if um else None
                if entry.startswith("games/") and entry.endswith("/hqs.yml"):
                    run(entry, entry, hm.hqs_schema, False, self.ctx) if hm else None
                if entry.startswith("games/") and entry.endswith("/main.yml"):
                    run(entry, entry, gm.game_main_schema, self.ctx) if gm else None
        return res
