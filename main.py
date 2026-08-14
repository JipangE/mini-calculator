"""Mini NPU Simulator

MAC(Multiply-Accumulate) 연산으로 입력 패턴이 어떤 필터(십자가 / X)에
더 가까운지 판별하는 콘솔 애플리케이션.

- 외부 라이브러리 사용하지 않음 (json, time 등 표준 라이브러리만 사용)
- MAC 연산은 반복문으로 직접 구현
"""

import json
import os
import time

# ---------------------------------------------------------------
# 상수
# ---------------------------------------------------------------

# 프로그램 내부에서 사용하는 "표준 라벨"
CROSS = "Cross"
X = "X"
UNDECIDED = "UNDECIDED"

# 부동소수점 오차를 감안한 동점 판정 기준
EPSILON = 1e-9

# 성능 측정 반복 횟수
REPEAT = 10

DATA_FILE = "data.json"

# 외부 표기 -> 표준 라벨 변환표
# data.json의 expected는 '+' / 'x', filter 키는 'cross' / 'x' 로 서로 다르게 표기되어 있다.
LABEL_TABLE = {
    "+": CROSS,
    "cross": CROSS,
    "plus": CROSS,
    "x": X,
}


def normalize_label(raw):
    """'+' , 'cross' 같은 외부 표기를 표준 라벨(Cross / X)로 정규화한다.

    해석할 수 없는 값이면 None을 돌려준다.
    """
    if not isinstance(raw, str):
        return None
    return LABEL_TABLE.get(raw.strip().lower())


# ---------------------------------------------------------------
# 데이터 구조
# ---------------------------------------------------------------


class Matrix:
    """n x n 크기의 2차원 실수 배열."""

    def __init__(self, size, rows=None):
        self.size = size
        if rows is None:
            self.rows = [[0.0] * size for _ in range(size)]
        else:
            self.rows = rows

    @classmethod
    def from_rows(cls, rows):
        """2차원 리스트를 검증한 뒤 Matrix로 만든다. 문제가 있으면 ValueError."""
        if not isinstance(rows, list) or len(rows) == 0:
            raise ValueError("2차원 배열이 아닙니다.")

        size = len(rows)
        converted = []
        for r, row in enumerate(rows):
            if not isinstance(row, list):
                raise ValueError("%d번째 행이 배열이 아닙니다." % (r + 1))
            if len(row) != size:
                raise ValueError(
                    "정사각형이 아닙니다: %d행 %d열 (행 수와 열 수가 달라야 함)"
                    % (size, len(row))
                )
            new_row = []
            for value in row:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("숫자가 아닌 값이 들어있습니다: %r" % (value,))
                new_row.append(float(value))
            converted.append(new_row)
        return cls(size, converted)

    # 특정 위치의 값 읽기 / 쓰기
    def get(self, row, col):
        return self.rows[row][col]

    def set(self, row, col, value):
        self.rows[row][col] = float(value)

    def to_text(self, indent="  "):
        lines = []
        for row in self.rows:
            lines.append(indent + " ".join("%g" % value for value in row))
        return "\n".join(lines)


def build_pattern(size, kind):
    """N x N 십자가 / X 패턴을 만들어 준다. (3x3 성능 측정용 기본 데이터)"""
    matrix = Matrix(size)
    center = size // 2
    for i in range(size):
        if kind == CROSS:
            matrix.set(center, i, 1.0)
            matrix.set(i, center, 1.0)
        else:
            matrix.set(i, i, 1.0)
            matrix.set(i, size - 1 - i, 1.0)
    return matrix


# ---------------------------------------------------------------
# MAC 연산 / 판정
# ---------------------------------------------------------------


def mac(pattern, filter_matrix):
    """위치별로 곱하고 모두 더한다 (Multiply-Accumulate)."""
    if pattern.size != filter_matrix.size:
        raise ValueError(
            "크기 불일치: 패턴 %dx%d, 필터 %dx%d"
            % (pattern.size, pattern.size, filter_matrix.size, filter_matrix.size)
        )

    size = pattern.size
    total = 0.0
    for row in range(size):
        for col in range(size):
            total += pattern.get(row, col) * filter_matrix.get(row, col)
    return total


def measure_mac(pattern, filter_matrix, repeat=REPEAT):
    """MAC 연산만 repeat회 반복 측정한다. (점수, 평균 시간 ms) 반환."""
    score = 0.0
    elapsed = 0.0
    for _ in range(repeat):
        start = time.perf_counter()
        score = mac(pattern, filter_matrix)
        elapsed += time.perf_counter() - start
    return score, (elapsed / repeat) * 1000.0


def decide(score_a, score_b, label_a, label_b):
    """두 점수를 비교해 판정한다. 차이가 EPSILON 미만이면 동점 처리."""
    if abs(score_a - score_b) < EPSILON:
        return UNDECIDED
    return label_a if score_a > score_b else label_b


# ---------------------------------------------------------------
# 출력 보조
# ---------------------------------------------------------------


def print_header(text):
    print()
    print("#" + "-" * 40)
    print("# " + text)
    print("#" + "-" * 40)


def print_perf_table(rows):
    """rows: [(size, avg_ms), ...]"""
    print("%-10s %-16s %s" % ("크기", "평균 시간(ms)", "연산 횟수"))
    print("-" * 42)
    for size, avg_ms in rows:
        label = "%dx%d" % (size, size)
        print("%-10s %-16.4f %d" % (label, avg_ms, size * size))


# ---------------------------------------------------------------
# 모드 1 : 사용자 입력 (3x3)
# ---------------------------------------------------------------


def read_matrix(title, size):
    """size줄을 공백 구분으로 입력받는다. 형식이 틀리면 안내 후 처음부터 다시 받는다."""
    while True:
        print("\n%s (%d줄 입력, 공백 구분)" % (title, size))
        rows = []
        valid = True

        for _ in range(size):
            line = input()
            parts = line.split()

            if len(parts) != size:
                print(
                    "입력 형식 오류: 각 줄에 %d개의 숫자를 공백으로 구분해 입력하세요. "
                    "(입력된 개수: %d)" % (size, len(parts))
                )
                valid = False
                break

            try:
                rows.append([float(part) for part in parts])
            except ValueError:
                print("입력 형식 오류: 숫자로 변환할 수 없는 값이 있습니다. (%s)" % line.strip())
                valid = False
                break

        if valid:
            return Matrix.from_rows(rows)

        print("-> 처음부터 다시 입력해 주세요.")


def run_user_mode():
    size = 3

    print_header("[1] 필터 입력")
    filter_a = read_matrix("필터 A", size)
    filter_b = read_matrix("필터 B", size)

    print("\n저장 확인")
    print(" 필터 A")
    print(filter_a.to_text("  "))
    print(" 필터 B")
    print(filter_b.to_text("  "))

    print_header("[2] 패턴 입력")
    pattern = read_matrix("패턴", size)
    print("\n저장 확인")
    print(pattern.to_text("  "))

    print_header("[3] MAC 결과")
    score_a, time_a = measure_mac(pattern, filter_a)
    score_b, time_b = measure_mac(pattern, filter_b)
    verdict = decide(score_a, score_b, "A", "B")

    print("A 점수: %r" % score_a)
    print("B 점수: %r" % score_b)
    print("연산 시간(평균/%d회): %.4f ms" % (REPEAT, (time_a + time_b) / 2))
    if verdict == UNDECIDED:
        print("판정: 판정 불가 (|A-B| = %.3e < %g)" % (abs(score_a - score_b), EPSILON))
    else:
        print("판정: %s" % verdict)

    print_header("[4] 성능 분석 (평균/%d회)" % REPEAT)
    print_perf_table([(size, (time_a + time_b) / 2)])


# ---------------------------------------------------------------
# 모드 2 : data.json 분석
# ---------------------------------------------------------------


def load_data(path=DATA_FILE):
    """data.json을 읽는다. 실패하면 (None, 사유)."""
    if not os.path.exists(path):
        return None, "%s 파일을 찾을 수 없습니다. main.py와 같은 폴더에 두세요." % path
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return None, "JSON 형식 오류: %s" % e
    except OSError as e:
        return None, "파일을 읽을 수 없습니다: %s" % e

    if not isinstance(data, dict):
        return None, "최상위 구조가 객체(dict)가 아닙니다."
    if not isinstance(data.get("filters"), dict):
        return None, "'filters' 항목이 없거나 형식이 올바르지 않습니다."
    if not isinstance(data.get("patterns"), dict):
        return None, "'patterns' 항목이 없거나 형식이 올바르지 않습니다."
    return data, None


def load_filters(raw_filters):
    """{5: {Cross: Matrix, X: Matrix}, ...} 형태로 정규화해서 돌려준다."""
    filters = {}

    for key in sorted(raw_filters, key=filter_sort_key):
        # 필터 키에서 N 추출 : size_5 -> 5
        parts = key.split("_")
        if len(parts) != 2 or parts[0] != "size" or not parts[1].isdigit():
            print("x %-8s 필터 키 형식 오류 (size_N 형태가 아님) -> 건너뜀" % key)
            continue

        size = int(parts[1])
        entry = raw_filters[key]
        if not isinstance(entry, dict):
            print("x %-8s 필터 형식 오류 (객체가 아님) -> 건너뜀" % key)
            continue

        loaded = {}
        problem = None
        for raw_label, rows in entry.items():
            # 필터 키 라벨 정규화 : 'cross' -> Cross, 'x' -> X
            label = normalize_label(raw_label)
            if label is None:
                problem = "알 수 없는 필터 라벨 '%s'" % raw_label
                break
            try:
                matrix = Matrix.from_rows(rows)
            except ValueError as e:
                problem = "%s 필터 %s" % (raw_label, e)
                break
            if matrix.size != size:
                problem = "%s 필터 크기 불일치 (키=%d, 실제=%d)" % (
                    raw_label,
                    size,
                    matrix.size,
                )
                break
            loaded[label] = matrix

        if problem is None and (CROSS not in loaded or X not in loaded):
            problem = "Cross / X 필터가 모두 있어야 합니다."

        if problem is not None:
            print("x %-8s 필터 로드 실패: %s" % (key, problem))
            continue

        filters[size] = loaded
        print("O %-8s 필터 로드 완료 (Cross, X)" % key)

    return filters


def filter_sort_key(key):
    parts = key.split("_")
    if len(parts) == 2 and parts[1].isdigit():
        return (0, int(parts[1]))
    return (1, 0)


def pattern_sort_key(key):
    parts = key.split("_")
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        return (0, int(parts[1]), int(parts[2]))
    return (1, 0, 0)


def analyze_pattern(key, entry, filters):
    """패턴 1건을 분석한다. (status, reason) 반환. 예외로 프로그램이 죽지 않게 한다."""
    # 1) 키에서 N 추출 : size_5_1 -> 5
    parts = key.split("_")
    if len(parts) != 3 or parts[0] != "size" or not parts[1].isdigit():
        return "FAIL", "키 형식 오류 (size_N_idx 형태가 아님)"
    size = int(parts[1])

    if not isinstance(entry, dict):
        return "FAIL", "패턴 형식 오류 (객체가 아님)"

    # 2) 패턴 배열 검증
    try:
        pattern = Matrix.from_rows(entry.get("input"))
    except ValueError as e:
        return "FAIL", "input 오류: %s" % e

    # 3) 키에서 뽑은 N에 해당하는 필터 선택
    if size not in filters:
        return "FAIL", "size_%d 필터가 없습니다." % size
    pair = filters[size]

    # 4) 필터와 패턴의 크기 일치 검증
    if pattern.size != size:
        return "FAIL", "크기 불일치 (키=%d, input=%d)" % (size, pattern.size)

    # 5) expected 라벨 정규화 : '+' -> Cross, 'x' -> X
    expected = normalize_label(entry.get("expected"))

    # 6) MAC 연산
    try:
        score_cross = mac(pattern, pair[CROSS])
        score_x = mac(pattern, pair[X])
    except ValueError as e:
        return "FAIL", str(e)

    verdict = decide(score_cross, score_x, CROSS, X)
    gap = abs(score_cross - score_x)

    print("--- %s ---" % key)
    print("Cross 점수: %r" % score_cross)
    print("X 점수: %r" % score_x)

    if expected is None:
        print("판정: %s | expected: %r | FAIL (expected 라벨 해석 불가)" % (verdict, entry.get("expected")))
        return "FAIL", "expected 라벨을 해석할 수 없음 (%r)" % (entry.get("expected"),)

    if verdict == UNDECIDED:
        print("  (동점 확인) Cross=%.17g / X=%.17g / 차이=%.3e" % (score_cross, score_x, gap))
        print("판정: %s | expected: %s | FAIL (동점 규칙)" % (verdict, expected))
        return "FAIL", "동점(UNDECIDED) 처리 규칙에 따라 FAIL (차이 %.3e < %g)" % (gap, EPSILON)

    status = "PASS" if verdict == expected else "FAIL"
    print("판정: %s | expected: %s | %s" % (verdict, expected, status))
    if status == "FAIL":
        return "FAIL", "판정(%s)이 expected(%s)와 다름" % (verdict, expected)
    return "PASS", ""


def run_performance(filters, patterns):
    """3x3(자체 생성) + data.json의 크기별 MAC 연산 시간을 측정한다."""
    rows = []

    # 3x3은 data.json에 없으므로 십자가/X 패턴을 직접 만들어 사용
    pattern_3 = build_pattern(3, CROSS)
    filter_3 = build_pattern(3, CROSS)
    _, avg_ms = measure_mac(pattern_3, filter_3)
    rows.append((3, avg_ms))

    for size in sorted(filters):
        sample = None
        for key in sorted(patterns, key=pattern_sort_key):
            parts = key.split("_")
            if len(parts) == 3 and parts[1].isdigit() and int(parts[1]) == size:
                try:
                    candidate = Matrix.from_rows(patterns[key].get("input"))
                except (ValueError, AttributeError):
                    continue
                if candidate.size == size:
                    sample = candidate
                    break
        if sample is None:
            sample = build_pattern(size, CROSS)

        _, avg_ms = measure_mac(sample, filters[size][CROSS])
        rows.append((size, avg_ms))

    print_perf_table(rows)


def run_json_mode():
    data, error = load_data()
    if data is None:
        print("\n[오류] %s" % error)
        return

    print_header("[1] 필터 로드")
    filters = load_filters(data["filters"])
    if not filters:
        print("\n[오류] 사용할 수 있는 필터가 없어 분석을 중단합니다.")
        return

    print_header("[2] 패턴 분석 (라벨 정규화 적용)")
    patterns = data["patterns"]
    results = []
    for key in sorted(patterns, key=pattern_sort_key):
        try:
            status, reason = analyze_pattern(key, patterns[key], filters)
        except Exception as e:  # 예상 못한 오류도 케이스 단위 FAIL로 처리
            status, reason = "FAIL", "예상치 못한 오류: %s" % e
            print("--- %s ---" % key)
            print("판정: FAIL (%s)" % reason)
        results.append((key, status, reason))

    print_header("[3] 성능 분석 (평균/%d회)" % REPEAT)
    run_performance(filters, patterns)

    print_header("[4] 결과 요약")
    failures = [(key, reason) for key, status, reason in results if status == "FAIL"]
    print("총 테스트: %d개" % len(results))
    print("통과: %d개" % (len(results) - len(failures)))
    print("실패: %d개" % len(failures))

    if failures:
        print("\n실패 케이스:")
        for key, reason in failures:
            print("- %s: %s" % (key, reason))

    print("\n(상세 원인 분석 및 복잡도 설명은 README.md의 \"결과 리포트\" 섹션 참고)")


# ---------------------------------------------------------------
# 실행 흐름
# ---------------------------------------------------------------


def main():
    print("=== Mini NPU Simulator ===")

    while True:
        print("\n[모드 선택]")
        print("1. 사용자 입력 (3x3)")
        print("2. data.json 분석")
        print("0. 종료")
        choice = input("선택: ").strip()

        if choice == "1":
            run_user_mode()
        elif choice == "2":
            run_json_mode()
        elif choice == "0":
            print("프로그램을 종료합니다.")
            return
        else:
            print("입력 오류: 0, 1, 2 중에서 선택하세요.")


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print("\n입력이 중단되어 프로그램을 종료합니다.")
