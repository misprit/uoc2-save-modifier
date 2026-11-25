"""e167 —— 城市废墟的存档读写路径：`MapObjects` 怎么加载 / 保存 `cities.yml` 与 `forts.yml`。

**背景**：U182 要做「修复被摧毁城市」，必须先知道废墟在存档里的**确切形状**与
**读写路径**，才能决定改哪几个字节、以及「删空之后」写成什么才安全。

**结论（全部来自字节码，不是推断）**

| 问题 | 答案 | 出处 |
|---|---|---|
| `cities.yml` 的结构？ | `map: [[x, y], {in_repair: false}]`；附加数据**只有** `in_repair`（布尔，默认 `False`） | ⑤ |
| `forts.yml` 的结构？ | `map: [[x, y], {functional: true}]`；附加数据是 `functional`（布尔，**无默认值 ⇒ 必须写**） | ⑤ |
| 坐标在 YAML 里是 list 还是 tuple？ | YAML 里是 **list**；**voluptuous 的 `uv_schema` 会把它转成 tuple** —— 不转的话 `dict(data['map'])` 会因 list 不可哈希而炸 | ①⑤ |
| 加载路径？ | `MapObjects.__init__` → `map_additional[ft] = dict(data['map'])`；随后把「不在本图 `map_existing` 里的坐标」**静默删掉**并打印一条 `Warning: removing …` | ① |
| 文件不存在时怎么办？ | `_read_data_file` 返回 `schema(dict())` ⇒ `{'map': []}` ⇒ `map_additional[ft] = {}` | ② |
| 保存路径？ | `MapObjects.save` → `data['map'] = [(uv, {k: v …}) …]` → `serialization.save_yaml_check_empty('<ft>.yml', data)` ⇒ **空表不写文件** | ③ |
| 废墟是怎么注入的？ | `set_destroyed_cities`：坐标在 `map_existing['cities']` 且不在 `map_additional['cities']` ⇒ 写入 `SimpleNamespace(in_repair=False)`；**同格要塞** `functional=False` | ④ |
| 「删空之后写 `map: []`」安全吗？ | **安全，且与「文件不存在」完全等价** —— 两种路径都让 `map_additional[ft] = {}` | ②③ |

**跑法（仓库根目录）**：
    .\\python\\python.exe docs\\证据脚本\\e167_ruins_mapobjects.py
"""

from __future__ import annotations

import dis
import io
import marshal
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from save_modifier_core.paths import CorePaths                     # noqa: E402

OUT_DIR = Path(r"D:\MiniMax\_analysis")
OUT: list[str] = []

REL = "uoc2/state/gamelike/map_objects.pyc"


def p(*a) -> None:
    OUT.append(" ".join(str(x) for x in a))


def load_pyc(path: Path):
    """游戏 .pyc 的头是 magic(4)+flags(4)+mtime(4)+size(4) = 16 字节。"""
    return marshal.loads(path.read_bytes()[16:])


def find_class(code, cls_name):
    for k in code.co_consts:
        if isinstance(k, types.CodeType):
            if k.co_name == cls_name:
                return k
            got = find_class(k, cls_name)
            if got is not None:
                return got
    return None


def find_func(code, func_name):
    for k in code.co_consts:
        if isinstance(k, types.CodeType) and k.co_name == func_name:
            return k
    return None


def dump(label: str, code) -> None:
    p("\n----- %s  (argcount=%d, varnames=%s) -----" % (
        label, code.co_argcount, code.co_varnames))
    for ins in dis.get_instructions(code):
        v = ""
        if ins.opname in ("LOAD_CONST", "LOAD_SMALL_INT", "LOAD_GLOBAL",
                          "LOAD_ATTR", "BINARY_OP", "COMPARE_OP",
                          "CONTAINS_OP", "STORE_SUBSCR", "STORE_ATTR"):
            v = "   <<%r>>" % (ins.argval,)
        p("    %-22s %s%s" % (ins.opname, ins.argrepr, v))


def main() -> int:
    gd = CorePaths.discover().game_dir
    if gd is None:
        raise SystemExit("找不到游戏目录")
    mod = load_pyc(gd / "lib" / REL)
    cls = find_class(mod, "MapObjects")

    p("=" * 78)
    p("① 加载路径：MapObjects.__init__（L58-86）")
    p("=" * 78)
    p("  源码行号就是游戏自己 .pyc 里记的行号，可直接对照。")
    dump("MapObjects.__init__", find_func(cls, "__init__"))

    p("\n" + "=" * 78)
    p("② 文件不存在时读什么：MapObjects._read_data_file（L116-121）")
    p("=" * 78)
    p("  ⇒ 文件不存在 ⇒ 返回 `schema(dict())` ⇒ `{'map': []}`（schema 的 default 生效）")
    dump("MapObjects._read_data_file", find_func(cls, "_read_data_file"))

    p("\n" + "=" * 78)
    p("③ 保存路径：MapObjects.save（L123-131）")
    p("=" * 78)
    p("  ⇒ `save_yaml_check_empty` ⇒ **空表不写文件**（游戏自己的「空 = 不存在」规矩）")
    dump("MapObjects.save", find_func(cls, "save"))

    p("\n" + "=" * 78)
    p("④ 废墟注入：MapObjects.set_destroyed_cities（L317-324）")
    p("=" * 78)
    p("  ⇒ 坐标必须在 `map_existing['cities']` 里，否则**静默丢弃**；")
    p("  ⇒ 同格要塞从 `map_additional['forts']` 取，取到就置 `functional = False`。")
    dump("MapObjects.set_destroyed_cities", find_func(cls, "set_destroyed_cities"))

    p("\n" + "=" * 78)
    p("⑤ 模块级 schema（_cities_schema / _forts_schema / _map_additional_schema）")
    p("=" * 78)
    p("  —— 模块体是顶层字节码，下面只打关键片段。")
    for ins in dis.get_instructions(mod):
        if ins.opname == "STORE_NAME" and ins.argval in (
                "_map_additional_schema", "_cities_schema", "_forts_schema",
                "_map_feature_types", "_ft_schemas"):
            p("  · STORE_NAME %s" % ins.argval)
    p("")
    p("  _map_additional_schema（L23-25）:")
    p("      Namespace({Required('in_repair', default=False): bool})")
    p("  _cities_schema（L37-38）:")
    p("      Schema(Dict({Required('map', default=list()):"
      " ExactSequence(uv_schema, _map_additional_schema)}))")
    p("  _forts_schema（L44-49）:")
    p("      Schema(Dict({Required('map', default=list()):"
      " ExactSequence(uv_schema, Namespace({Required('functional'): bool}))}))")
    p("      ⚠️ `functional` **没有 default** ⇒ 写 fort 条目时必须显式写 functional")
    p("  _map_feature_types（L53）= ('bridges', 'cities', 'airports', 'forts')")
    p("  _ft_schemas（L54）= (_bridges_schema, _cities_schema, _airports_schema, _forts_schema)")

    p("\n" + "=" * 78)
    p("⑥ 「删空之后写 `map: []`」的等价性（把 ②③ 连起来）")
    p("=" * 78)
    p("  路径 A（文件不存在）:")
    p("      _read_data_file → schema(dict()) → {'map': []}")
    p("      __init__      → map_additional['cities'] = dict([]) = {}")
    p("  路径 B（文件存在，内容 = `map: []`）:")
    p("      _read_data_file → load_yaml('cities.yml', schema) → {'map': []}")
    p("      __init__      → map_additional['cities'] = dict([]) = {}")
    p("  ⇒ **两条路径完全等价** ⇒ 第一版删空时写 `map: []` 是安全的，")
    p("    不需要给 packing.py 加「删除 ZIP 条目」的能力。")

    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        io.open(str(OUT_DIR / "e167_out.txt"), "w",
                encoding="utf-8", newline="\n").write("\n".join(OUT))
    except Exception as e:                       # pragma: no cover
        p("  （写不出去文件：%s）" % e)
    print("\n".join(OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
