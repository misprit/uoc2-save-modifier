# -*- coding: utf-8 -*-
"""U98：启动页（选存档那页）顶部加**标题** + **作者署名**。

**用户原话**：
「你已经帮我在应用上署名了，我希望你在最开始读取存档页的一个位置帮我署上名。
如果单独署名看着怪怪的，你可以在页面最上方先加一个统一指挥2修改器字样，
然后在下面再放上我的作者名」

**做法**：
启动页 `<h1>` 写「统一指挥 2 存档修改器」，紧跟一行小字「烟柳边城 misprit」。

**为什么署名不翻译**：作者名是**人名**，中英文界面都保持「烟柳边城 misprit」——
和概览页底部的 `L("作者") + " " + AUTHOR` 口径一致（U80 定的）。

**为什么有这些测试**：守住四条 ——
① 启动页确实有标题 + 署名，且**署名在标题下方、副标题上方**（别跑到角落里）；
② 标题走词表 ⇒ 英文界面是 "Unity of Command 2 Save Modifier"；
③ 署名**不进词表**（人名不翻译）；
④ 署名和概览页的 `AUTHOR` 常量**是同一个字符串**（别两处各写一份、改一处忘一处）。
"""

import io
import json
import os
import re
import unittest

REPO_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "src")
WEB = os.path.join(REPO_SRC, "save_modifier_web", "web")


class SplashBylineTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = io.open(os.path.join(WEB, "index.html"),
                           encoding="utf-8", newline="").read()
        cls.table = json.loads(io.open(os.path.join(WEB, "i18n.json"),
                                       encoding="utf-8", newline="").read())

    def splash(self):
        """截出启动页那一段 HTML（`#splash` 到 `<!-- ============ 主界面`）。"""
        i = self.html.index('<div id="splash">')
        j = self.html.index("<!-- ==========", i)
        return self.html[i:j]


class TestSplashTitleAndByline(SplashBylineTestBase):
    """① 标题 + 署名，位置要对。"""

    def setUp(self):
        self.s = self.splash()

    def test_splash_has_title(self):
        self.assertIn("<h1>统一指挥 2 存档修改器</h1>", self.s)

    def test_splash_has_byline(self):
        self.assertIn('<div class="by">烟柳边城 misprit</div>', self.s)

    def test_byline_is_between_title_and_subtitle(self):
        """署名夹在标题和「选一个存档开始」之间（别塞到页面角落）。"""
        i_title = self.s.index("<h1>")
        i_by = self.s.index('<div class="by">')
        i_sub = self.s.index('<div class="sub">')
        self.assertLess(i_title, i_by)
        self.assertLess(i_by, i_sub)

    def test_byline_is_not_wrapped_in_translation_call(self):
        """署名是**人名**，不翻译 ⇒ 不许套 `L(...)` / `L2(...)`。"""
        self.assertNotIn('L("烟柳边城 misprit")', self.s)
        self.assertNotIn("L('烟柳边城 misprit')", self.s)

    def test_byline_has_its_own_css(self):
        """`.by` 有自己的样式（灰、小、居中），不跟标题糊在一起。"""
        self.assertIn("#splash .by{", self.html)
        self.assertIn("color:var(--muted)", self.html)


class TestBylineMatchesAuthorConstant(SplashBylineTestBase):
    """④ 署名和概览页的 `AUTHOR` 常量必须是同一个字符串。"""

    def test_author_constant(self):
        m = re.search(r'const AUTHOR = "([^"]+)";', self.html)
        self.assertIsNotNone(m, "找不到 AUTHOR 常量")
        self.assertEqual(m.group(1), "烟柳边城 misprit")

    def test_splash_byline_uses_the_same_string(self):
        m = re.search(r'const AUTHOR = "([^"]+)";', self.html)
        self.assertIsNotNone(m)
        self.assertIn('<div class="by">%s</div>' % m.group(1), self.html)


class TestTitleTranslation(SplashBylineTestBase):
    """②③ 标题翻译 / 署名不翻译。"""

    def test_title_is_in_the_word_table(self):
        ui = self.table["ui"]
        self.assertIn("统一指挥 2 存档修改器", ui)
        self.assertEqual(ui["统一指挥 2 存档修改器"],
                         "Unity of Command 2 Save Modifier")

    def test_author_name_is_not_in_the_word_table(self):
        """人名**不许**进词表 —— 进了就会被翻译，中英文界面就不一致了。"""
        for section, words in self.table.items():
            if not isinstance(words, dict):
                continue
            self.assertNotIn("烟柳边城 misprit", words,
                             "署名出现在词表 %s 段里 —— 会把作者名翻译掉" % section)

    def test_about_page_still_uses_author_word(self):
        """概览页底部的「作者 XXX」那行不许被这次改动弄丢。"""
        self.assertIn('L("作者") + " " + AUTHOR', self.html)


if __name__ == "__main__":
    unittest.main()
