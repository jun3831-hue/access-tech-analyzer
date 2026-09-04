"""
===============================================================================
Module Name   : optis_extractor.py
Location      : core/optis_extractor.py
Description   : OPTis-S4 CLI Extraction Pipeline & Cache Manager
===============================================================================
"""

import os
import glob
import re
import time
import shutil
import subprocess
from typing import Dict, List, Optional


OPTIS_DIR = r"C:\Program Files (x86)\Innowireless\OPTis-S4 Analyzer"
OPTIS_EXE = os.path.join(OPTIS_DIR, "OPTis-S4 Analyzer.exe")

FAV_MAP = {
    "QC_KPI": "KPI", "MAC_DL_DCI": "DL_DCI", "DL_DCI_PER_SLOT": "DL_DCI", 
    "MAC_UL_DCI": "UL_DCI", "UL_DCI_PER_SLOT": "UL_DCI", "MAC_PDSCH": "PDSCH", 
    "PDSCH_PER_SLOT": "PDSCH", "MAC_CSF": "CSF", "CSF_REPORT": "CSF", 
    "UL_PHY_CHA_PC": "UL_PC", "PC_PER_SLOT": "UL_PC", "UL_PHY_CHA_SCHE": "UL_SCHE", 
    "SCHE_PER_SLOT": "UL_SCHE",
    "CALL_RESULT": "CALL_RESULT",
    "EVENT_DETAIL": "EVENT_DETAIL",
    "EVENT_(DETAIL)": "EVENT_DETAIL",
    "EVENT": "EVENT",
    "SMART_PHONE": "SMART_PHONE",
    "SMARTPHONE": "SMART_PHONE",
    "RTP": "RTP"
}


class OptisExtractor:
    """Manages CLI-based high-speed CSV extraction from DRM log files."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def extract(self, drm_files: List[str], fav_list: List[str], model_file_path: str = "") -> Dict[str, Dict[str, str]]:
        """
        OPTis-S4 CLI Extraction Pipeline:
        1. 1st Attempt: MOP (Open Model) fast extraction.
        2. Fallback: CM (Create Model) full rebuild.
        3. Marker: Generate 0-byte completed markers for empty scenario FAVs.
        """
        if not drm_files:
            return {}
        file_dict = {}

        for drm_file in drm_files:
            drm_file_win = os.path.normpath(drm_file)
            drm_name = os.path.basename(drm_file_win).replace(".drm", "")
            drm_name_upper = drm_name.upper()
            drm_clean = re.sub(r'[^A-Za-z0-9가-힣]', '', drm_name).upper()

            existing_csvs = {re.sub(r'[^A-Za-z0-9가-힣]', '', f).upper(): os.path.join(self.cache_dir, f) for f in os.listdir(self.cache_dir) if f.lower().endswith('.csv')}
            matched_csvs = {}
            missing_favs = []
            missing_l3 = True

            if fav_list:
                for fav_path in fav_list:
                    if not os.path.exists(fav_path):
                        continue
                    fav_name = os.path.basename(fav_path).replace(".fav", "")
                    expected_csv_upper = f"{drm_name_upper}_M1_FAV_{fav_name.upper()}.CSV"
                    expected_clean = re.sub(r'[^A-Za-z0-9가-힣]', '', expected_csv_upper).upper()

                    found_path = None
                    if expected_clean in existing_csvs:
                        found_path = existing_csvs[expected_clean]
                    else:
                        clean_fav = re.sub(r'[^A-Za-z0-9가-힣]', '', fav_name).upper()
                        for k, p in existing_csvs.items():
                            if drm_clean in k and clean_fav in k:
                                found_path = p
                                break

                    if found_path:
                        for kw, key in FAV_MAP.items():
                            if kw in fav_name.upper():
                                matched_csvs[key] = found_path
                    else:
                        missing_favs.append(fav_path)

            for existing_clean, existing_path in existing_csvs.items():
                if "MESSAGEBROWSER" in existing_clean and drm_clean in existing_clean:
                    matched_csvs["L3_MSG"] = existing_path
                    missing_l3 = False
                    break

            if missing_favs or missing_l3:
                if os.path.exists(OPTIS_EXE):
                    subprocess.run(['taskkill', '/f', '/im', 'OPTis-S4 Analyzer.exe'], capture_output=True)
                    time.sleep(0.5)

                temp_out = os.path.normpath(os.path.join(self.cache_dir, "Temp_Work"))
                shutil.rmtree(temp_out, ignore_errors=True)
                os.makedirs(temp_out, exist_ok=True)

                fav_args_win = os.path.normpath(";".join(missing_favs)) if missing_favs else ""
                default_model_dir = os.path.expanduser(r'~\Documents\InnoWireless\OPTis Analyzer\Model')
                auto_model_path = os.path.join(default_model_dir, f"{drm_name}_M1")
                target_model_path = model_file_path if (model_file_path and os.path.exists(model_file_path)) else auto_model_path

                # 1. MOP Attempt
                mop_success = False
                if target_model_path and os.path.exists(target_model_path) and os.path.exists(OPTIS_EXE):
                    cmd_mop = [OPTIS_EXE, "-MOP", os.path.normpath(target_model_path), temp_out]
                    if missing_favs:
                        cmd_mop.extend(["-FEP", fav_args_win])
                    if missing_l3:
                        cmd_mop.extend(["-MEP", "G", "D", "BRC", "L3"])
                    cmd_mop.append("-MG")

                    subprocess.run(cmd_mop, cwd=OPTIS_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.HIGH_PRIORITY_CLASS)
                    subprocess.run(['taskkill', '/f', '/im', 'OPTis-S4 Analyzer.exe'], capture_output=True)
                    time.sleep(0.5)

                    gen_csvs = glob.glob(os.path.join(temp_out, "**", "*.csv"), recursive=True)
                    if gen_csvs and all(os.path.getsize(c) > 0 for c in gen_csvs):
                        mop_success = True

                # 2. CM Fallback
                if not mop_success:
                    if os.path.exists(OPTIS_EXE):
                        subprocess.run(['taskkill', '/f', '/im', 'OPTis-S4 Analyzer.exe'], capture_output=True)
                        time.sleep(0.5)

                    shutil.rmtree(temp_out, ignore_errors=True)
                    os.makedirs(temp_out, exist_ok=True)

                    cmd_cm = [OPTIS_EXE, "-CM", drm_file_win, temp_out]
                    if missing_favs:
                        cmd_cm.extend(["-FEP", fav_args_win])
                    if missing_l3:
                        cmd_cm.extend(["-MEP", "G", "D", "BRC", "L3"])
                    cmd_cm.append("-MG")

                    if os.path.exists(OPTIS_EXE):
                        subprocess.run(cmd_cm, cwd=OPTIS_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.HIGH_PRIORITY_CLASS)
                        subprocess.run(['taskkill', '/f', '/im', 'OPTis-S4 Analyzer.exe'], capture_output=True)
                        time.sleep(0.5)

                # Move generated CSVs
                for csv_path in glob.glob(os.path.join(temp_out, "**", "*.csv"), recursive=True):
                    new_path = os.path.join(self.cache_dir, os.path.basename(csv_path))
                    shutil.move(csv_path, new_path)
                    csv_name = os.path.basename(new_path).upper()
                    csv_clean = re.sub(r'[^A-Za-z0-9가-힣]', '', csv_name).upper()

                    for kw, key in FAV_MAP.items():
                        if kw in csv_name:
                            matched_csvs[key] = new_path
                    if "MESSAGEBROWSER" in csv_clean and drm_clean in csv_clean:
                        matched_csvs["L3_MSG"] = new_path

                # 0-Byte completed marker
                for fav_path in missing_favs:
                    fav_name = os.path.basename(fav_path).replace(".fav", "")
                    mapped_key = None
                    for kw, key in FAV_MAP.items():
                        if kw in fav_name.upper():
                            mapped_key = key
                            break
                    if mapped_key and mapped_key not in matched_csvs:
                        marker_csv_name = f"{drm_name}_M1_Fav_{fav_name}.csv"
                        marker_path = os.path.join(self.cache_dir, marker_csv_name)
                        if not os.path.exists(marker_path):
                            with open(marker_path, 'w', encoding='utf-8') as f_empty:
                                pass
                        matched_csvs[mapped_key] = marker_path

                shutil.rmtree(temp_out, ignore_errors=True)

            file_dict[drm_name] = matched_csvs

        if os.path.exists(OPTIS_EXE):
            subprocess.run(['taskkill', '/f', '/im', 'OPTis-S4 Analyzer.exe'], capture_output=True)
        return file_dict
