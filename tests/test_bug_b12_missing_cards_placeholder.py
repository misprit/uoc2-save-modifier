"""缺 cards.yml 与缺会议检查点是两个独立的状态。"""
import json
import os
import shutil
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / 'src/save_modifier_web/web'


class Buttons(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.enabled = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'button':
            self.enabled[attrs.get('onclick')] = 'disabled' not in attrs


def render(hand, restore, lang):
    source = Path(os.environ.get('UOC2_INDEX_HTML', WEB / 'index.html')).read_text(encoding='utf-8')
    def section(start, end):
        i = source.index(start)
        return source[i:source.index(end, i)]
    js = '\n'.join([
        section('function L(zh)', 'async function loadI18n('),
        section('function esc(s)', '/*',),
        section('function pageCards(w)', 'function restoreHand('),
        "const projectedCards = cards => cards, SEL = {}, w = {};",
        "const I18N = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8')).ui;",
        'const LANG = ' + json.dumps(lang) + ';',
        'const VIEW = ' + json.dumps({'hand': [], 'shelf': [], '_features': [
            {'name': 'hand', 'ok': hand, 'reason': '' if hand else 'missing <cards.yml>'},
            {'name': 'restore_hand', 'ok': restore}]}) + ';',
        'pageCards(w); process.stdout.write(w.innerHTML);',
    ])
    return subprocess.run(['node', '-', str(WEB / 'i18n.json')], input=js, text=True,
                          encoding='utf-8', capture_output=True, check=True).stdout


@unittest.skipUnless(shutil.which('node'), '本机没有 node')
class MissingHandTest(unittest.TestCase):
    def test_hand_and_restore_capabilities(self):
        for lang, missing, empty, title in [
                ('chi', '这个存档没有手牌数据', '手里没有牌', '手牌 · 0 张'),
                ('en', 'This save has no hand data', 'No cards in hand', 'Hand · 0 cards')]:
            for hand in (False, True):
                for restore in (False, True):
                    with self.subTest(lang=lang, hand=hand, restore=restore):
                        html = render(hand, restore, lang)
                        self.assertIn(empty if hand else missing, html)
                        self.assertNotIn(missing if hand else empty, html)
                        self.assertIn(title, html)
                        self.assertEqual('missing &lt;cards.yml&gt;' in html, not hand)
                        buttons = Buttons(html).enabled
                        self.assertEqual(buttons["openCardPicker('hand',0)"], hand)
                        self.assertEqual(buttons['restoreHand()'], restore)
