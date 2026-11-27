"""修改器备份的限时预览与逐件回收。save_path 必须由服务端验证。"""
from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import re
import secrets
import stat
import threading
import time
import uuid
from pathlib import Path

from save_modifier_core import paths as core_paths



class BackupCleanupError(ValueError):
    pass


def _clean(path):
    # resolve() 会先吃掉联接点；必须在逐层 lstat 之前保留原路径。
    if not path.is_absolute() or ".." in path.parts:
        return False
    for part in (*reversed(path.parents), path):
        st = part.lstat()
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_file_attributes", 0) & 0x400:
            return False
    return True


def _enumerate(save):
    base = core_paths.appdata_dir().absolute()
    sources = (base / "save", *(p.absolute() for p in core_paths.import_roots()))
    if not any(save.is_relative_to(root) for root in sources) or not _clean(save) or not save.is_file() or save.suffix.lower() != ".usg":
        raise BackupCleanupError("存档不允许操作")
    # writer 只记文件名，不记来源目录。同名活跃存档或导入副本无法区分。
    def fail(exc):
        raise exc
    for root in sources:
        if not root.exists():
            continue
        if not _clean(root):
            raise BackupCleanupError("存档目录无法核验")
        for folder, dirs, names in os.walk(root, onerror=fail, followlinks=False):
            dirs[:] = [d for d in dirs if _clean(Path(folder) / d)]
            if any(n.casefold() == save.name.casefold() and Path(folder) / n != save for n in names):
                raise BackupCleanupError("存在同名存档，无法确定备份归属")
    exact = re.compile(re.escape(save.stem) + r"_BACKUP(?:_(?:[2-9]|[1-9][0-9]+))?" + re.escape(save.suffix))
    # 只有程序自身 bak 可回收；旧 appdata fallback bak 仅作为只读遗留目录。
    root = core_paths.backup_dir().absolute()
    # ⚠️ **v1.4.3 修**：区分「程序**专属**的 bak」与「环境变量指定的目录」。
    #
    # * **程序专属**（`<修改器目录>/bak/`，默认布局）
    #   ⇒ 里面的 `_BACKUP.usg` **一定是程序自己写的** ⇒ 该列、该删。
    #   ⚠️ 玩家把程序解压到**存档目录里面**是完全合理的用法
    #   （实测：`%LOCALAPPDATA%\.uoc2\save\uoc2-save-modifier`）
    #   ⇒ 旧写法「bak 落在存档目录里就整个跳过」⇒ **概览页能显示、
    #   管理备份却一条都没有**（两处口径不一致）。
    # * **环境变量指定的**（`UOC2_BAK_DIR`）⇒ 那个目录**可能就是**存档目录
    #   ⇒ 里面的 `_BACKUP.usg` 可能是玩家/游戏造的 ⇒ **保持原来的闸门**。
    own_backup_dir = (core_paths.modifier_home()
                      / core_paths.BACKUP_DIR_NAME).absolute()
    is_own_backup_dir = (root == own_backup_dir)
    if not is_own_backup_dir and (
            root.is_relative_to(core_paths.fallback_backup_dir().absolute())
            or any(root.is_relative_to(folder) for folder in sources)):
        return
    try:
        if not _clean(root) or not root.is_dir():
            return
        for p in root.iterdir():
            if not exact.fullmatch(p.name):
                continue
            try:
                st = p.lstat()
                if stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and _clean(p):
                    yield p, st
            except FileNotFoundError:
                continue
    except FileNotFoundError:
        return


def _check_recycle_result(hr, recycled, path):
    """判「回收到底成没成」—— **看行为，不看 HRESULT**。

    ⚠️ 实测（2026-11-27）：Windows 的 `RecycleItem` **成功时也返回正值状态码**
    —— `0x00270008` = COPYENGINE_S_USER_IGNORED（名字骗人：实际是
    「没有弹确认框，操作照常执行」）⇒ 旧判据 `hr != 0 ⇒ 失败`
    把**成功**报成了失败（玩家看到「回收失败」，备份其实已在回收站里）。

    ⇒ 判据：
      ① HRESULT 为负（明确的失败）⇒ 失败；
      ② 没有返回回收后的项目 ⇒ 失败；
      ③ 文件**仍在原处** ⇒ 失败（根本没被移走）；
      ④ 其余 ⇒ 成功 —— `ITransferSource::RecycleItem` 的语义就是「放进回收站」，
         它**没有永久删除那条路**（永久删除是 `RemoveItem`，我们没调）。
    """
    if hr < 0:
        raise BackupCleanupError("Windows 回收失败 (0x%08X)" % (hr & 0xffffffff))
    if not recycled:
        raise BackupCleanupError("Windows 未返回回收后的项目")
    try:
        still_there = path.exists()
    except OSError:
        still_there = True
    if still_there:
        raise BackupCleanupError("Windows 没有回收该文件（它还在原处）")


def _recycle_windows(path):
    """只调用 ITransferSource::RecycleItem，不使用允许永久删除的通用 Delete。"""
    if os.name != "nt":
        raise BackupCleanupError("需要 Windows 回收站")
    ptr = ctypes.c_void_p
    output = ctypes.POINTER(ptr)
    shell, ole = ctypes.windll.shell32, ctypes.windll.ole32

    def check(hr):
        if hr < 0:
            raise BackupCleanupError("Windows 回收失败 (0x%08X)" % (hr & 0xffffffff))

    def guid(value):
        return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)

    def method(obj, slot, types, *args):
        table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ptr)))[0]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ptr, *types)(table[slot])(obj, *args)

    iid_item = guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")
    bhid = guid("d5e346a1-f753-4932-b403-4574800e2498")
    iid_source = guid("00adb003-bde9-45c6-8e29-d09f9353e108")
    parent, item, bin_item, source, recycled = (ptr() for _ in range(5))
    check(ole.CoInitializeEx(None, 2))
    try:
        for name, obj in ((str(path.parent), parent), (str(path), item),
                          ("::{645ff040-5081-101b-9f08-00aa002f954e}", bin_item)):
            check(shell.SHCreateItemFromParsingName(ctypes.c_wchar_p(name), None, iid_item, ctypes.byref(obj)))
        # IShellItem::BindToHandler(3); ITransferSource::RecycleItem(8), NOT RemoveItem(9).
        check(method(parent, 3, (ptr, ptr, ptr, output), None, bhid, iid_source, ctypes.byref(source)))
        hr = method(source, 8, (ptr, ptr, ctypes.c_uint, output), item, bin_item, 0, ctypes.byref(recycled))
        _check_recycle_result(hr, recycled, path)
    finally:
        for obj in (recycled, source, bin_item, item, parent):
            if obj:
                method(obj, 2, ())
        ole.CoUninitialize()


class BackupCleanup:
    """复用同一实例；preview(save_path) 的 id 可交给 recycle_one(save_path, id)。"""

    def __init__(self, *, backend=None, ttl=300):
        self._key = secrets.token_bytes(32)
        self._backend = backend or _recycle_windows
        self._ttl = ttl
        self._recycle_lock = threading.RLock()

    def _id(self, save, p, st, expires):
        def version(s):
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink

        with p.open("rb") as stream:
            if version(os.fstat(stream.fileno())) != version(st):
                raise BackupCleanupError("备份已变化，请刷新")
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if not _clean(p) or version(p.lstat()) != version(st):
            raise BackupCleanupError("备份已变化，请刷新")
        state = (digest, str(save), str(p), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns,
                 st.st_ctime_ns, getattr(st, "st_birthtime_ns", 0), expires)
        return str(expires) + "." + hmac.digest(self._key, repr(state).encode("utf-8"), "sha256").hex()

    def preview(self, save_path):
        save = Path(save_path)
        expires = int(time.monotonic()) + self._ttl
        return [{"id": self._id(save, p, st, expires), "name": p.name, "size": st.st_size,
                 "mtime": st.st_mtime, "source": "primary"}
                for p, st in _enumerate(save)]

    def recycle_one(self, save_path, item_id):
        if not isinstance(item_id, str) or not re.fullmatch(r"[0-9]{1,16}[.][0-9a-f]{64}", item_id):
            raise BackupCleanupError("备份标识无效")
        with self._recycle_lock:
            expires = int(item_id.partition(".")[0])
            save = Path(save_path)
            if time.monotonic() >= expires:
                raise BackupCleanupError("预览过期，请刷新")
            for p, st in _enumerate(save):
                if hmac.compare_digest(self._id(save, p, st, expires), item_id) and time.monotonic() < expires:
                    self._backend(p)
                    return
            raise BackupCleanupError("备份已变化或预览过期，请刷新")

    def recycle_many(self, save_path, item_ids):
        for item_id in item_ids:
            self.recycle_one(save_path, item_id)
