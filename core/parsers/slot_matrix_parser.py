"""
===============================================================================
Module Name   : slot_matrix_parser.py
Location      : analyzer/01_base_parsers/slot_matrix_parser.py
Description   : 160-Slot (Excel Export) & 320-Slot (DET/ANA Deep Analysis) 2D Grid Matrix Calculator
===============================================================================
"""

import re
import pandas as pd
import numpy as np
from typing import Optional, List, Tuple, Dict


class SlotMatrixParser:
    """Computes 160-Slot (80ms cycle) & 320-Slot (160ms cycle) 2D Physical Layer Grid Matrices."""

    def __init__(self):
        pass

    @staticmethod
    def _find_col(df: pd.DataFrame, keywords) -> Optional[str]:
        if df is None or df.empty:
            return None
        from core.canonical_registry import CanonicalColumnRegistry
        kws = keywords if isinstance(keywords, list) else [keywords]
        for kw in kws:
            actual = CanonicalColumnRegistry.get_actual_column(df, kw)
            if actual:
                return actual
        for kw in kws:
            kw_clean = re.sub(r'[^a-zA-Z0-9]', '', kw.lower())
            for c in df.columns:
                c_clean = re.sub(r'[^a-zA-Z0-9]', '', str(c).lower())
                if kw_clean in c_clean:
                    return c
        return None

    def build_160_matrix(self, df: pd.DataFrame, val_col_kw: Optional[str] = None, is_bler: bool = False) -> Optional[pd.DataFrame]:
        """
        Builds 160-Slot 2D Grid Matrix (8 Frames x 20 Slots, 80ms cycle) for Excel Export:
          - Rows (Index)    : Frame 0 ~ Frame 7 (8 Radio Frames)
          - Columns (Header): Slot 0 ~ Slot 19 (20 Slots per 10ms frame)
        """
        return self._build_generic_matrix(df, val_col_kw=val_col_kw, is_bler=is_bler, num_frames=8)

    def build_320_matrix(self, df: pd.DataFrame, val_col_kw: Optional[str] = None, is_bler: bool = False) -> Optional[pd.DataFrame]:
        """
        Builds 320-Slot 2D Grid Matrix (16 Frames x 20 Slots, 160ms cycle) for DET/ANA Deep Analysis:
          - Rows (Index)    : Frame 0 ~ Frame 15 (16 Radio Frames)
          - Columns (Header): Slot 0 ~ Slot 19 (20 Slots per 10ms frame)
        """
        return self._build_generic_matrix(df, val_col_kw=val_col_kw, is_bler=is_bler, num_frames=16)

    def _build_generic_matrix(self, df: pd.DataFrame, val_col_kw: Optional[str], is_bler: bool, num_frames: int) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        df = df.copy()

        sfn_c = self._find_col(df, ['System Frame Number', 'SFN'])
        slot_c = self._find_col(df, ['Slot Number', 'Slot'])

        if not sfn_c or not slot_c:
            return None

        s_sfn = pd.to_numeric(df[sfn_c], errors='coerce').fillna(0).astype(int)
        s_slot = pd.to_numeric(df[slot_c], errors='coerce').fillna(0).astype(int)

        df['Frame_Offset'] = (s_sfn % num_frames).astype(int)
        df['Slot_In_Frame'] = (s_slot % 20).astype(int)

        # Value Column Extraction
        if is_bler:
            crc_c = self._find_col(df, ['CRC State', 'CRC Status', 'CRC'])
            if crc_c:
                s_crc = df[crc_c].astype(str)
                df['val_num'] = np.where(s_crc.str.contains('FAIL|ERROR|NOK|1', case=False, regex=True), 100.0, 0.0)
            else:
                df['val_num'] = 0.0
        elif val_col_kw:
            val_c = self._find_col(df, [val_col_kw])
            if val_c:
                if 'Power Limit' in val_col_kw:
                    pwr_c = self._find_col(df, ['PUSCH Actual Transmit Power'])
                    mtpl_c = self._find_col(df, ['PUSCH Data MTPL'])
                    if pwr_c and mtpl_c:
                        pwr = pd.to_numeric(df[pwr_c], errors='coerce')
                        mtpl = pd.to_numeric(df[mtpl_c], errors='coerce')
                        df['val_num'] = np.where(pwr >= (mtpl - 0.1), 100.0, 0.0)
                    else:
                        df['val_num'] = 0.0
                elif 'SLIV' in val_col_kw or 'Duration' in val_col_kw:
                    dur_c = self._find_col(df, ['Duration', 'PDSCH Duration'])
                    if dur_c:
                        df['val_num'] = pd.to_numeric(df[dur_c], errors='coerce')
                    else:
                        df['val_num'] = 12.0
                else:
                    df['val_num'] = pd.to_numeric(df[val_c], errors='coerce')
            else:
                return None
        else:
            return None

        # Pivot to N Frames x 20 Slots 2D Grid
        pivot = df.pivot_table(index='Frame_Offset', columns='Slot_In_Frame', values='val_num', aggfunc='mean')
        pivot = pivot.reindex(index=range(num_frames), columns=range(20))
        pivot = pivot.round(2)

        # Formatted 2D Matrix
        pivot.index = [f"Frame {i}" for i in range(num_frames)]
        pivot.columns = [f"Slot {j}" for j in range(20)]
        pivot.index.name = "Frame \\ Slot"

        return pivot.reset_index()

    def compute_all_matrices(self, csvs: Dict[str, Optional[str]]) -> List[Tuple[str, pd.DataFrame]]:
        """Computes all 160-slot 2D Grid matrices for Excel Export."""
        from core.kpi_summary_engine import safe_read_csv
        pdsch_csv = csvs.get('PDSCH')
        csf_csv = csvs.get('CSF')
        ul_pc_csv = csvs.get('UL_PC')

        df_pdsch = safe_read_csv(pdsch_csv)
        df_csf = safe_read_csv(csf_csv)
        df_ul_pc = safe_read_csv(ul_pc_csv)

        drm_mtx_list = []
        if df_pdsch is not None and not df_pdsch.empty:
            drm_mtx_list.extend([
                ("1. PDSCH_BLER_Matrix (%)", self.build_160_matrix(df_pdsch, is_bler=True)),
                ("2. PDSCH_MCS_Matrix (Avg MCS)", self.build_160_matrix(df_pdsch, 'MCS')),
                ("3. PDSCH_RB_Matrix (Avg PRBs)", self.build_160_matrix(df_pdsch, 'Num RBs')),
                ("4. PDSCH_Layer_Matrix (Avg Layers)", self.build_160_matrix(df_pdsch, 'Num Layers'))
            ])
        if df_csf is not None and not df_csf.empty:
            drm_mtx_list.append(("5. CSI_CQI_Matrix (Avg WB CQI)", self.build_160_matrix(df_csf, 'WB CQI')))
        if df_ul_pc is not None and not df_ul_pc.empty:
            drm_mtx_list.append(("6. UL_Power_Limit_Matrix (%)", self.build_160_matrix(df_ul_pc, 'Power Limit')))

        return [(name, mtx) for name, mtx in drm_mtx_list if mtx is not None]

    def compute_all_320_matrices(self, csvs: Dict[str, Optional[str]]) -> Dict[str, pd.DataFrame]:
        """Computes 320-slot 2D Grid matrices for DET/ANA Deep Analysis."""
        from core.kpi_summary_engine import safe_read_csv
        pdsch_csv = csvs.get('PDSCH')
        dci_csv = csvs.get('DCI')
        csf_csv = csvs.get('CSF')
        ul_pc_csv = csvs.get('UL_PC')
        ul_sche_csv = csvs.get('UL_SCHE')

        df_pdsch = safe_read_csv(pdsch_csv)
        df_dci = safe_read_csv(dci_csv)
        df_csf = safe_read_csv(csf_csv)
        df_ul_pc = safe_read_csv(ul_pc_csv)
        df_ul_sche = safe_read_csv(ul_sche_csv)

        mtx_dict = {}
        if df_pdsch is not None and not df_pdsch.empty:
            mtx_dict['320_BLER'] = self.build_320_matrix(df_pdsch, is_bler=True)
            mtx_dict['320_MCS'] = self.build_320_matrix(df_pdsch, 'MCS')
            mtx_dict['320_RB'] = self.build_320_matrix(df_pdsch, 'Num RBs')
            mtx_dict['320_LAYER'] = self.build_320_matrix(df_pdsch, 'Num Layers')
        if df_dci is not None and not df_dci.empty:
            mtx_dict['320_SLIV_DURATION'] = self.build_320_matrix(df_dci, 'Duration')
        if df_csf is not None and not df_csf.empty:
            mtx_dict['320_CQI'] = self.build_320_matrix(df_csf, 'WB CQI')
        if df_ul_pc is not None and not df_ul_pc.empty:
            mtx_dict['320_POWER_LIMIT'] = self.build_320_matrix(df_ul_pc, 'Power Limit')
        if df_ul_sche is not None and not df_ul_sche.empty:
            mtx_dict['320_UL_RB'] = self.build_320_matrix(df_ul_sche, 'Num RBs')

        return {k: v for k, v in mtx_dict.items() if v is not None}
