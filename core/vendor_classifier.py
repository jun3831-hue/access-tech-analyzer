"""
===============================================================================
Module Name   : vendor_classifier.py
Location      : core/vendor_classifier.py
Description   : 5G/LTE Base Station Vendor Identification Engine
===============================================================================
"""

import pandas as pd
import numpy as np


class VendorClassifier:
    """Classifies Base Station Vendor based on eNB/Cell ID ranges and rules."""

    def __init__(self):
        # 4대 벤더 (화웨이 포함) eNB 범위 (실제 국사 매핑 DB 연동 전까지 0,0 비활성화)
        self.rules = [
            (lambda cid: 0 <= (cid // 256) <= 0, "NOKIA"),
            (lambda cid: 0 <= (cid // 256) <= 0, "SAMSUNG"),
            (lambda cid: 0 <= (cid // 256) <= 0, "ERICSSON"),
            (lambda cid: 0 <= (cid // 256) <= 0, "HUAWEI")
        ]

    def identify(self, cell_id, default: str = "COMMON") -> str:
        """Identifies vendor string ('NOKIA', 'SAMSUNG', 'ERICSSON', 'HUAWEI', 'COMMON')."""
        if cell_id is None or pd.isna(cell_id):
            return default
        try:
            val = int(float(cell_id))
            for rule_func, vendor in self.rules:
                if rule_func(val) and val > 0:
                    return vendor
        except Exception:
            pass
        return default
