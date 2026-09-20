"""视觉层测试：ImageValidator / TemplateRegistry / TemplateMatcher / ScreenDetector（Phase 3-4）。"""
import os
import tempfile

import cv2
import numpy as np

from core.models import BattleProfile, ScreenType
from vision.capture import ImageValidator
from vision.detector import ScreenDetector
from vision.matcher import TemplateMatcher, TemplateRegistry

from .conftest import make_screen


def _write_tpl(path, size=20):
    img = np.full((size, size, 3), 128, dtype=np.uint8)
    cv2.rectangle(img, (2, 2), (size - 3, size - 3), (255, 0, 0), -1)
    cv2.imwrite(path, img)
    return img


class TestImageValidator:

    def test_valid_image(self):
        assert ImageValidator.is_valid(make_screen())

    def test_none_and_empty(self):
        assert not ImageValidator.is_valid(None)
        assert not ImageValidator.is_valid(np.zeros((0, 0, 3), np.uint8))

    def test_black_image_invalid(self):
        assert not ImageValidator.is_valid(np.zeros((48, 64, 3), np.uint8))


class TestTemplateRegistry:

    def test_load_and_cache(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            _write_tpl(p)
            reg = TemplateRegistry()
            a = reg.load(p)
            b = reg.load(p)
            assert a is not None and a is b  # 命中缓存

    def test_missing_returns_none(self):
        reg = TemplateRegistry()
        assert reg.load("") is None
        assert reg.load("no/such/file.png") is None

    def test_mtime_invalidation(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            _write_tpl(p)
            reg = TemplateRegistry()
            a = reg.load(p)
            # 覆盖写 -> mtime 变化 -> 缓存失效
            import time
            time.sleep(0.05)
            _write_tpl(p)
            b = reg.load(p)
            assert a is not b


class TestTemplateMatcher:

    def test_find_hit_and_center(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            tpl = _write_tpl(p, 20)
            screen = make_screen(200, 150)
            # 模板贴到屏幕 (60, 40) 左上角
            screen[40:40 + 20, 60:60 + 20] = tpl
            m = TemplateMatcher().find(screen, p, threshold=0.8)
            assert m.matched
            assert m.center == (60 + 10, 40 + 10)
            assert m.score >= 0.8

    def test_find_miss_returns_none_center(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            _write_tpl(p)
            m = TemplateMatcher().find(make_screen(100, 80), p, threshold=0.99)
            assert not m.matched
            assert m.center is None


class TestScreenDetector:

    def test_detect_only_requested_types(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            tpl = _write_tpl(p, 20)
            screen = make_screen(200, 150)
            screen[40:60, 60:80] = tpl
            prof = BattleProfile(battle_img=p, victory_img=p)
            det = ScreenDetector()
            res = det.detect(screen, prof, [ScreenType.CHALLENGE])
            assert res.challenge is not None and res.challenge.matched
            assert res.victory is None  # 未请求

    def test_empty_template_skipped(self):
        prof = BattleProfile(battle_img="")
        res = ScreenDetector().detect(make_screen(), prof,
                                      [ScreenType.CHALLENGE])
        assert res.challenge is None

    def test_first_priority_order(self):
        from core.models import MatchResult, ScreenResult
        res = ScreenResult()
        res.victory = MatchResult(ScreenType.VICTORY, (1, 1), 0.9)
        res.failure = MatchResult(ScreenType.FAILURE, (2, 2), 0.9)
        assert res.first(ScreenType.FAILURE, ScreenType.VICTORY).center == (2, 2)
        assert res.first(ScreenType.VICTORY, ScreenType.FAILURE).center == (1, 1)
        assert res.first(ScreenType.SETTLEMENT) is None


class TestUnicodePath:
    """中文文件名模板可读取(语义化命名后模板图名含中文,cv2.imread 不支持)。"""

    def test_chinese_path_load_and_match(self, tmp_path):
        import numpy as np
        import cv2
        from PIL import Image
        from vision.matcher import TemplateMatcher, TemplateRegistry

        tpl = np.full((20, 30, 3), 128, np.uint8)
        cv2.rectangle(tpl, (2, 2), (27, 17), (255, 0, 0), -1)
        cn = str(tmp_path / "999爬塔_victory.png")
        Image.fromarray(tpl[:, :, ::-1]).save(cn)

        reg = TemplateRegistry()
        loaded = reg.load(cn)
        assert loaded is not None, "中文路径模板读取失败"

        screen = np.full((100, 200, 3), 200, np.uint8)
        screen[40:60, 60:90] = tpl
        r = TemplateMatcher(reg).find(screen, cn, 0.8)
        assert r.matched and r.center == (75, 50)

    def test_missing_path_safe(self):
        from vision.matcher import TemplateRegistry
        assert TemplateRegistry().load("不存在.png") is None
