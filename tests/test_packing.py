"""S2：保真打包器。

验收口径见文档 §11.4 / §11.5：

* 外层 ZIP 的**条目数量与顺序**与原存档一致；
* 除被显式修改的文件外，其余条目**逐条 SHA256 一致**（字节级不变）；
* 内层 `games/<场景>/archive` ZIP 作为**整条目原样复制**（不解压重压）。

这些测试不需要玩家存档：用合成的 .usg 就能覆盖全部机制；
另外有一组"真实存档"测试，在本机找得到存档时自动跑，找不到就跳过。
"""

import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from save_modifier_core import packing

#: 旧工具里的 `savefile.extract_archive` 已随旧 REPL 一起砍掉；
#: 解包能力搬进了核心库（`packing.extract`），旧工具不再需要自己解包。
extract_archive = packing.extract

# 游戏自己的写盘约定（实测 70 个存档一致）：全条目同一时间戳
GAME_STAMP = (2026, 1, 2, 3, 4, 6)


def make_fake_save(path: Path, entries: dict[str, bytes],
                   stamp=GAME_STAMP) -> Path:
    """造一个模仿游戏写盘约定的 .usg。"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zi = zipfile.ZipInfo(name, date_time=stamp)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zi.create_system = 0
            zf.writestr(zi, data)
    return path


def find_real_saves() -> list[Path]:
    """在本机找几个真实存档（找不到就返回空列表，测试自动跳过）。"""
    root = Path(os.environ.get(
        "UOC2_SAVE_ROOT",
        Path.home() / "AppData" / "Local" / ".uoc2" / "save"))
    out: list[Path] = []
    for sub in ("campaigns", "games"):
        d = root / sub
        if d.is_dir():
            out.extend(sorted(d.glob("*.usg"))[:2])
    old = root / "Old Saves"
    if old.is_dir():
        out.extend(sorted(old.rglob("*.usg"))[:1])
    return out


class TestPackingSynthetic(unittest.TestCase):
    """合成存档：覆盖打包器的全部机制。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pack_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.save = make_fake_save(self.tmp / "s.usg", {
            "main.yml": b"campaign_id: west\nprestige: 100\n",
            "units.yml": b"- {id: 1, xp: 10}\n",
            "document/main.yml": b"milestones: []\n",
            "games/avalanche/archive": b"PK\x03\x04fake-inner-zip-bytes",
        })
        self.work = self.tmp / "work"
        extract_archive(self.save, self.work)

    def test_roundtrip_is_byte_identical(self):
        """不改任何东西 → 重打包后必须与原存档逐条一致。"""
        out = self.tmp / "out.usg"
        report = packing.repack(self.save, self.work, out)
        self.assertEqual(report.added, [])
        self.assertEqual(report.missing, [])
        self.assertEqual(report.changed, [])
        self.assertFalse(report.reordered)

        v = packing.verify(self.save, out)
        self.assertTrue(v.ok, f"校验未通过：{v.summary()}")
        self.assertEqual(v.changed, [])

    def test_entry_order_and_metadata_preserved(self):
        out = self.tmp / "out.usg"
        packing.repack(self.save, self.work, out)
        with zipfile.ZipFile(self.save) as a, zipfile.ZipFile(out) as b:
            ia, ib = a.infolist(), b.infolist()
            self.assertEqual([i.filename for i in ia], [i.filename for i in ib])
            self.assertEqual([i.date_time for i in ia], [i.date_time for i in ib])
            self.assertEqual([i.external_attr for i in ia], [i.external_attr for i in ib])
            self.assertEqual([i.create_system for i in ia], [i.create_system for i in ib])
            self.assertEqual([i.compress_type for i in ia], [i.compress_type for i in ib])

    def test_only_edited_entry_changes(self):
        """改一个文件 → 只有它变，其余条目字节级不变。"""
        (self.work / "units.yml").write_bytes(b"- {id: 1, xp: 400}\n")
        out = self.tmp / "out.usg"
        report = packing.repack(self.save, self.work, out)
        self.assertEqual(report.changed, ["units.yml"])

        v = packing.verify(self.save, out)
        self.assertEqual(v.changed, ["units.yml"])
        self.assertEqual(v.missing, [])
        self.assertEqual(v.added, [])
        self.assertFalse(v.reordered)

    def test_inner_archive_is_copied_as_whole_entry(self):
        """内层 archive ZIP 必须是原样字节，不能被解压重压。"""
        out = self.tmp / "out.usg"
        packing.repack(self.save, self.work, out)
        with zipfile.ZipFile(self.save) as a, zipfile.ZipFile(out) as b:
            self.assertEqual(a.read("games/avalanche/archive"),
                             b.read("games/avalanche/archive"))

    def test_missing_work_file_falls_back_to_original(self):
        """工作目录里少了文件 → 从原存档原样取回，绝不静默丢条目。"""
        (self.work / "units.yml").unlink()
        out = self.tmp / "out.usg"
        report = packing.repack(self.save, self.work, out)
        self.assertEqual(report.missing, ["units.yml"])
        v = packing.verify(self.save, out)
        self.assertEqual(v.changed, [])
        self.assertEqual(v.missing, [])

    def test_extra_work_file_is_reported_not_injected(self):
        """工作目录里多出来的文件必须被报告，且不写进存档。"""
        (self.work / "stray.txt").write_text("不该出现", encoding="utf-8")
        out = self.tmp / "out.usg"
        report = packing.repack(self.save, self.work, out)
        self.assertEqual(report.added, ["stray.txt"])
        with zipfile.ZipFile(out) as zf:
            self.assertNotIn("stray.txt", zf.namelist())

    def test_output_can_overwrite_input(self):
        """覆盖保存时 output 与 original 同路径（Windows 上不能开着源文件替换）。"""
        target = self.tmp / "s2.usg"
        shutil.copy2(self.save, target)
        work = self.tmp / "work2"
        extract_archive(target, work)
        (work / "main.yml").write_bytes(b"campaign_id: west\nprestige: 999\n")
        report = packing.repack(target, work, target)
        self.assertEqual(report.changed, ["main.yml"])
        with zipfile.ZipFile(target) as zf:
            self.assertIn(b"prestige: 999", zf.read("main.yml"))
            self.assertEqual(len(zf.namelist()), 4)

    def test_verify_detects_difference(self):
        out = self.tmp / "out.usg"
        packing.repack(self.save, self.work, out)
        with zipfile.ZipFile(out, "a") as zf:
            zi = zipfile.ZipInfo("extra.yml", date_time=GAME_STAMP)
            zf.writestr(zi, b"x: 1\n")
        v = packing.verify(self.save, out)
        self.assertEqual(v.added, ["extra.yml"])
        self.assertFalse(v.ok)


class TestPackingRealSave(unittest.TestCase):
    """真实存档：70 个存档普查的一部分（本机没有存档就跳过）。"""

    def test_real_saves_roundtrip_identically(self):
        saves = find_real_saves()
        if not saves:
            self.skipTest("本机没有找到 .uoc2 存档，跳过真实存档回归测试")
        tmp = Path(tempfile.mkdtemp(prefix="pack_real_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for src in saves:
            with self.subTest(save=src.name):
                work = tmp / "work"
                extract_archive(src, work)
                out = tmp / "out.usg"
                report = packing.repack(src, work, out)
                self.assertEqual(report.added, [],
                                 f"{src.name}：工作目录里有原存档没有的文件")
                v = packing.verify(src, out)
                self.assertEqual(v.changed, [], f"{src.name}：内容发生了变化")
                self.assertEqual(v.missing, [], f"{src.name}：有条目丢失")
                self.assertFalse(v.reordered, f"{src.name}：条目顺序不一致")


if __name__ == "__main__":
    unittest.main()
