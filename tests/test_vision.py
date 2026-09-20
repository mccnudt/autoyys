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

    def test_shared_registry_across_matchers(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            _write_tpl(p, 20)
            m1 = TemplateMatcher()
            m2 = TemplateMatcher()
            assert m1.registry is m2.registry
            a = m1.registry.load(p)
            b = m2.registry.load(p)
            assert a is not None and a is b

    def test_multiscale_matching_finds_scaled_template(self):
        """跨分辨率等比缩放: 模板在画面中尺寸缩放(如1.2倍)时，多尺度匹配能正确命中。"""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            # 原始模板 20x20
            _write_tpl(p, 20)
            # 在画面中放入 24x24 的放大版图案(1.2倍缩放)
            screen = make_screen(120, 100)
            import cv2
            tpl_img = cv2.imread(p)
            scaled_tpl = cv2.resize(tpl_img, (24, 24), interpolation=cv2.INTER_LINEAR)
            screen[30:54, 40:64] = scaled_tpl

            matcher = TemplateMatcher()
            # 默认 1.0 尺度匹配低分不命中
            m1 = matcher.find(screen, p, threshold=0.9, scales=[1.0])
            assert not m1.matched

            # 启用多尺度 scales=[1.0, 1.2, 0.8] 成功命中
            m2 = matcher.find(screen, p, threshold=0.85, scales=[1.0, 1.2, 0.8])
            assert m2.matched
            assert abs(m2.center[0] - (40 + 12)) <= 2
            assert abs(m2.center[1] - (30 + 12)) <= 2

    def test_find_all_multiple_targets(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.png")
            tpl = _write_tpl(p, 20)
            screen = make_screen(300, 200)
            # 放置 3 个相同目标
            screen[30:50, 40:60] = tpl
            screen[30:50, 120:140] = tpl
            screen[100:120, 40:60] = tpl

            matcher = TemplateMatcher()
            matches = matcher.find_all(screen, p, threshold=0.8)
            assert len(matches) == 3
            centers = {m.center for m in matches}
            assert (50, 40) in centers
            assert (130, 40) in centers
            assert (50, 110) in centers


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

    def test_exclude_filter_skips_failed_challenges(self):
        """结界突破排除测试: 顶部目标打上失败标记时，多目标策略自动跳过该目标选择下方可用目标。"""
        with tempfile.TemporaryDirectory() as d:
            p_battle = os.path.join(d, "battle.png")
            p_exclude = os.path.join(d, "fail_mark.png")
            tpl_battle = _write_tpl(p_battle, 20)

            # 排除标记(不同图案)
            ex_img = np.full((15, 15, 3), 50, dtype=np.uint8)
            cv2.circle(ex_img, (7, 7), 5, (0, 0, 255), -1)
            cv2.imwrite(p_exclude, ex_img)

            screen = make_screen(300, 300)
            # 两个挑战目标: 上方 (60, 40) 和 下方 (60, 160)
            screen[40:60, 60:80] = tpl_battle
            screen[160:180, 60:80] = tpl_battle

            # 在上方挑战目标右侧 (90, 40) 贴排除标记(间距 ~27px，不破坏模板像素)
            screen[40:55, 90:105] = ex_img

            prof = BattleProfile(
                battle_img=p_battle,
                exclude_enabled=True,
                exclude_img=p_exclude,
                exclude_distance=40.0,
                exclude_threshold=0.8,
                match_strategy="最上面"
            )
            det = ScreenDetector()
            res = det.detect(screen, prof, [ScreenType.CHALLENGE], strategy=prof.match_strategy)
            assert res.challenge is not None and res.challenge.matched
            # 上方目标被排除，选中的应是下方目标 (60+10, 160+10) = (70, 170)
            assert res.challenge.center == (70, 170)
            assert res.excluded_count == 1

    def test_exclude_filter_all_excluded(self):
        """当所有挑战目标均被打上排除标记时，全部跳过且 challenge 为 None。"""
        with tempfile.TemporaryDirectory() as d:
            p_battle = os.path.join(d, "battle.png")
            p_exclude = os.path.join(d, "fail_mark.png")
            tpl_battle = _write_tpl(p_battle, 20)
            ex_img = np.full((15, 15, 3), 50, dtype=np.uint8)
            cv2.circle(ex_img, (7, 7), 5, (0, 0, 255), -1)
            cv2.imwrite(p_exclude, ex_img)

            screen = make_screen(200, 200)
            screen[40:60, 60:80] = tpl_battle
            screen[40:55, 85:100] = ex_img  # 距目标中心 (70, 50) 约 22px

            prof = BattleProfile(
                battle_img=p_battle,
                exclude_enabled=True,
                exclude_img=p_exclude,
                exclude_distance=30.0,
            )
            det = ScreenDetector()
            res = det.detect(screen, prof, [ScreenType.CHALLENGE])
            assert res.challenge is None or not res.challenge.matched
            assert res.excluded_count == 1


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
