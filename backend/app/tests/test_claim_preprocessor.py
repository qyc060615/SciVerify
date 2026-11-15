from __future__ import annotations

import pytest

from app.utils.claim_preprocessor import (
    CLAIM_MAX_LENGTH,
    InvalidClaimError,
    preprocess_claim,
)


class TestClaimPreprocessing:
    def test_normalization(self) -> None:
        result = preprocess_claim("The method improves accuracy by 40%.")

        assert result.original == "The method improves accuracy by 40%."
        assert result.normalized == "the method improves accuracy by 40%"
        assert "method" in result.tokens
        assert "accuracy" in result.tokens
        assert "40%" in result.claim_numbers

    def test_whitespace_normalization(self) -> None:
        result = preprocess_claim("  method   improves   accuracy  ")

        assert result.normalized == "method improves accuracy"

    def test_punctuation_removal(self) -> None:
        result = preprocess_claim("Accuracy, however, improved!")

        assert "," not in result.normalized
        assert "!" not in result.normalized
        assert "accuracy" in result.tokens

    def test_empty_claim(self) -> None:
        with pytest.raises(InvalidClaimError):
            preprocess_claim("   ")

    def test_claim_too_long(self) -> None:
        with pytest.raises(InvalidClaimError):
            preprocess_claim("a" * (CLAIM_MAX_LENGTH + 1))

    def test_numeric_extraction(self) -> None:
        result = preprocess_claim("Sample size was 120 and accuracy improved by 3.5%.")

        assert "120" in result.claim_numbers
        assert "3.5%" in result.claim_numbers
