"""收敛判定：绝对值不超过 3.0 mm 为合格。抽稀取样规则：飞点跳变与窗内重复。"""
from statistics import median

LIMIT_MM = 3.0

# 抽稀台默认参数（落库前/重置时的出厂值）
DEFAULT_WINDOW_SECONDS = 3600
DEFAULT_JUMP_THRESHOLD_MM = 5.0

# 测点部位：掌子面放炮、边墙锤击都走同一张抽稀台
SECTIONS = ("掌子面", "边墙")
DEFAULT_SECTION = "掌子面"

# 拦截规则编号
RULE_MEDIAN_JUMP = "median_jump"  # 相对窗内中位跳变过猛
RULE_WINDOW_DUP = "window_dup"    # 取样窗内同测点已有一笔进队


def judge(delta_mm: float) -> tuple[str, str]:
    if abs(delta_mm) <= LIMIT_MM:
        return "合格", f"收敛 {delta_mm} mm 在 ±{LIMIT_MM} mm 以内"
    return "超限", f"收敛 {delta_mm} mm 超过 ±{LIMIT_MM} mm"


def window_median(values) -> float | None:
    """窗内已进队读数的中位数；窗内无样本时返回 None（没有基线可比对）。"""
    vals = [float(v) for v in values]
    return float(median(vals)) if vals else None


def check_thinning(items, recent_values, recent_keys, window_seconds, jump_threshold_mm):
    """抽稀开着时的进队校验。

    items: 本次交单的测点列表 [{"chainage", "section", "delta_mm"}, ...]
    recent_values: 取样窗内已进队的全部读数（跨测点，用于窗内中位）
    recent_keys: 取样窗内已进队的 (chainage, section) 集合

    返回 None 表示放行；返回 (rule, detail, item, median) 表示整份退回。
    """
    med = window_median(recent_values)

    # 同一测点在同一取样窗内至多进队一笔（含本份交单内部自相重复）
    seen = set()
    for it in items:
        key = (it["chainage"], it["section"])
        if key in recent_keys or key in seen:
            detail = (
                f"{it['chainage']}（{it['section']}）在 {window_seconds} 秒取样窗内"
                f"已有一笔进队，本次整份退回"
            )
            return RULE_WINDOW_DUP, detail, it, med
        seen.add(key)

    # 相对窗内中位跳得太猛的飞点，整份退回
    for it in items:
        if med is not None and abs(float(it["delta_mm"]) - med) > jump_threshold_mm:
            detail = (
                f"{it['chainage']}（{it['section']}）收敛 {it['delta_mm']} mm "
                f"相对窗内中位 {round(med, 3)} mm 跳变超过 {jump_threshold_mm} mm，整份退回"
            )
            return RULE_MEDIAN_JUMP, detail, it, med

    return None
