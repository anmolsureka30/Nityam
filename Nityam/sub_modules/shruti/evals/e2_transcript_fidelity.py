import re

_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def word_error_rate(hypothesis: str, reference: str) -> float:
    hyp_words, ref_words = hypothesis.split(), reference.split()
    m, n = len(hyp_words), len(ref_words)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if hyp_words[i - 1] == ref_words[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[m][n] / max(1, n)


def _script_of(word: str) -> str:
    return "devanagari" if _DEVANAGARI_RE.search(word) else "latin"


def script_fidelity(hypothesis: str, reference: str) -> float:
    """Fraction of reference words whose script (Latin vs Devanagari) the
    hypothesis preserves at the same position — a transcript that
    transliterates everything into one script scores low here even if the
    words are individually 'correct'."""
    hyp_words, ref_words = hypothesis.split(), reference.split()
    if not ref_words:
        return 1.0
    matches = sum(1 for h, r in zip(hyp_words, ref_words) if _script_of(h) == _script_of(r))
    return matches / len(ref_words)
