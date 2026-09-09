# -*- coding: utf-8 -*-
"""
CanonicalColumnRegistry
Optis 원천 18종 CSV의 컬럼 공백/특수문자/대괄호 왜곡을 아키텍처 레벨에서 근본적으로 정합하는 레지스트리.
"""
import re
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List


class CanonicalColumnRegistry:
    """원천 CSV의 컬럼 공백/특수문자 왜곡을 정규화하고 1:1 풀 컬럼명을 보존하는 레지스트리"""
    
    @staticmethod
    def to_canonical_key(col_name: str) -> str:
        if not col_name:
            return ""
        # 1. 특수 공백, non-breaking spaces (\xa0, \u200b), tab, newline 단일화
        s = re.sub(r'[\s\xa0\u200b\t\n\r]+', ' ', str(col_name)).strip()
        # 2. 앞뒤 대괄호 제거 ([...] -> ...)
        if s.startswith('[') and s.endswith(']'):
            s = s[1:-1].strip()
        # 3. 소문자화
        return s.lower()

    @classmethod
    def get_actual_column(cls, df: Optional[pd.DataFrame], target_col: str) -> Optional[str]:
        if df is None or df.empty or not target_col:
            return None
        # 1. 원본 완전 일치
        if target_col in df.columns:
            return target_col
        
        # 2. Canonical Key 기반 검색
        target_k = cls.to_canonical_key(target_col)
        for actual_col in df.columns:
            if cls.to_canonical_key(actual_col) == target_k:
                return actual_col
                
        # 3. 만약 대괄호가 붙어있거나 떼어진 버전 직접 검색
        unbracketed = target_col.strip('[]').strip()
        bracketed = f"[{unbracketed}]"
        if unbracketed in df.columns:
            return unbracketed
        if bracketed in df.columns:
            return bracketed

        # 4. Truncated column name / Partial overlap fallback
        for actual_col in df.columns:
            act_k = cls.to_canonical_key(actual_col)
            if len(target_k) >= 15 and len(act_k) >= 15:
                if target_k[:20] in act_k or act_k[:20] in target_k:
                    return actual_col
            
        return None

    @classmethod
    def get_series(cls, df: Optional[pd.DataFrame], target_col: str) -> pd.Series:
        if df is None or df.empty:
            return pd.Series(dtype=float)
        actual_col = cls.get_actual_column(df, target_col)
        if actual_col and actual_col in df.columns:
            return df[actual_col]
        return pd.Series(dtype=float)

    @classmethod
    def get_numeric_mean(cls, df: Optional[pd.DataFrame], target_col: str) -> float:
        s = cls.get_series(df, target_col)
        if not s.empty:
            v = pd.to_numeric(s, errors='coerce').dropna()
            if not v.empty:
                return float(v.mean())
        return np.nan

    @classmethod
    def get_numeric_min(cls, df: Optional[pd.DataFrame], target_col: str) -> float:
        s = cls.get_series(df, target_col)
        if not s.empty:
            v = pd.to_numeric(s, errors='coerce').dropna()
            if not v.empty:
                return float(v.min())
        return np.nan

    @classmethod
    def get_numeric_max(cls, df: Optional[pd.DataFrame], target_col: str) -> float:
        s = cls.get_series(df, target_col)
        if not s.empty:
            v = pd.to_numeric(s, errors='coerce').dropna()
            if not v.empty:
                return float(v.max())
        return np.nan

    @classmethod
    def get_numeric_std(cls, df: Optional[pd.DataFrame], target_col: str) -> float:
        s = cls.get_series(df, target_col)
        if not s.empty:
            v = pd.to_numeric(s, errors='coerce').dropna()
            if len(v) > 1:
                return float(v.std())
        return 0.0
