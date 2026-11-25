"""U188：战役页的「废墟」块必须在**路线图下面**（用户 2026-11-25：
「目前修改废墟功能埋在战役最低下，太难发现了。把这个功能调整到战役第二行，
也就是路线图下面」）。

**为什么要断言 i18n 词表里的英文模板**：英文界面渲染的是 `I18N[key]`，
不是源码里那份 ⇒ 只搬 `index.html` 的话，**中文界面挪了、英文界面还埋在底下**
（U186 的教训：同一个规则的**每一处实现**都要覆盖）。

**为什么还要一条巡检**：静态断言只比对源码字面量、不验行为（U186 实锤：
一条断言把 bug 本身锁住了 46 个 commit）⇒ 真 DOM 位置要由 `tools/ui_audit.py`
点出来验一遍。
"""

import io
import json
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(REPO, "src", "save_modifier_web", "web")
HTML = os.path.join(WEB, "index.html")
I18N = os.path.join(WEB, "i18n.json")

MARK = "w.innerHTML = L2(`"

#: 废墟块在模板里的占位符（`pageCampaign` 的最后一个参数）
RUIN_PH = "      {12}"

#: 路线图块的收尾（这两行中英两版**完全一样** —— 只有占位符，没有文案）
ROUTE_TAIL = "        {2}\n      </div>\n"

#: 会议商店块之后的说明段开头（英文版里是 `<div class="note">`，一样）
NOTE_HEAD = "      <div class=\"note\">"


def campaign_template(html: str) -> str:
    """从 `index.html` 里取出战役页那段 L2 模板。"""
    i = html.index(MARK, html.index("function pageCampaign("))
    j = html.index("`", i + len(MARK))
    return html[i + len(MARK):j]


class RuinsBlockPositionTest(unittest.TestCase):
    def setUp(self):
        with io.open(HTML, encoding="utf-8") as f:
            self.html = f.read()
        with io.open(I18N, encoding="utf-8") as f:
            self.table = json.load(f)
        self.tpl_zh = campaign_template(self.html)
        self.tpl_en = self.table["ui"].get(self.tpl_zh)

    def test_the_chinese_template_moves_the_ruins_below_the_roadmap(self):
        self.assertIsNotNone(self.tpl_en, "战役页模板不在 i18n 的 ui 词表里")
        self.assertIn(ROUTE_TAIL + RUIN_PH + "\n", self.tpl_zh,
                      "废墟块必须紧跟在路线图块下面")
        self.assertNotIn("        {11}\n      </div>\n" + RUIN_PH + "\n",
                         self.tpl_zh,
                         "废墟块不该还留在页面最底下（会议商店后面）")

    def test_the_english_template_moves_it_too(self):
        """英文界面用的是 `I18N[key]` —— 源码挪了、词表没挪 ⇒ 英文界面还在底下。"""
        self.assertIsNotNone(self.tpl_en, "战役页模板不在 i18n 的 ui 词表里")
        self.assertIn(ROUTE_TAIL + RUIN_PH + "\n", self.tpl_en,
                      "英文模板里的废墟块也必须在路线图下面")
        self.assertNotIn("        {11}\n      </div>\n" + RUIN_PH + "\n",
                         self.tpl_en)

    def test_both_templates_stay_line_aligned(self):
        """中英两版必须**逐行对应** —— 否则搬动后占位符会对不上。"""
        self.assertIsNotNone(self.tpl_en)
        self.assertEqual(len(self.tpl_zh.split("\n")),
                         len(self.tpl_en.split("\n")))

    def test_the_ruins_box_has_a_stable_id(self):
        """巡检要按 DOM 位置断言 ⇒ 废墟块得有个稳定标识。"""
        body = self.html[self.html.index("function ruinsBox("):
                          self.html.index("function ruinsBox(") + 3000]
        self.assertIn('id="ruinsbox"', body)

    def test_ruins_box_is_still_a_full_width_block(self):
        """搬位置**不改形态** —— 仍是整块的 `.storegrp`（不是挤进两列格子里）。"""
        body = self.html[self.html.index("function ruinsBox("):
                          self.html.index("function ruinsBox(") + 3000]
        self.assertIn('class="storegrp" id="ruinsbox"', body)


if __name__ == "__main__":
    unittest.main()
