"""收敛判定与抽稀规则。

- judge：绝对值不超过 3.0 mm 为合格。
- evaluate_thin：相对取样窗中位跳变判定。窗口为同部位最近若干笔
  「已准入」读数；新读数与窗内中位的偏离达到阈值（>=）即判飞点，
  整份退回。取「达到即退」是为了让贴着门槛几乎同时到达的两笔
  不可能双双混入队列。样本不足无法定中位时一律放行。
"""
from statistics import median

LIMIT_MM = 3.0

# 少于这么多已准入样本时不做飞点判定（无法确定相对中位）
MIN_WINDOW_SAMPLES = 2


def judge(delta_mm: float) -> tuple[str, str]:
    if abs(delta_mm) <= LIMIT_MM:
        return "合格", f"收敛 {delta_mm} mm 在 ±{LIMIT_MM} mm 以内"
    return "超限", f"收敛 {delta_mm} mm 超过 ±{LIMIT_MM} mm"


def window_median(samples: list[float]) -> float:
    return float(median(samples))


def evaluate_thin(
    delta_mm: float, samples: list[float], threshold_mm: float
) -> tuple[bool, float | None, float | None, str]:
    """返回 (是否放行, 中位, 跳变量, 说明)。"""
    if len(samples) < MIN_WINDOW_SAMPLES:
        return (
            True,
            None,
            None,
            f"取样窗仅 {len(samples)} 笔（不足 {MIN_WINDOW_SAMPLES} 笔），不做飞点判定",
        )
    med = window_median(samples)
    deviation = abs(delta_mm - med)
    # 1e-9 mm 容差仅用于消除二进制浮点毛刺（读数精度 0.1 mm），
    # 保证「恰好贴门槛」的点不会因 1.9999999999999998 这类误差漏网
    if deviation + 1e-9 >= threshold_mm:
        return (
            False,
            med,
            deviation,
            f"相对窗中位 {med:.2f} mm 跳变 {deviation:.2f} mm，达到阈值 {threshold_mm:.1f} mm，整份退回",
        )
    return (
        True,
        med,
        deviation,
        f"相对窗中位 {med:.2f} mm，跳变 {deviation:.2f} mm 在阈值 {threshold_mm:.1f} mm 以内",
    )
