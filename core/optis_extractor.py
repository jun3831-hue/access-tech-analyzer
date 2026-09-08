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
import threading
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


class OptisProgressMonitor:
    """
    Non-destructive delta progress monitor for OPTis-S4 CLI.
    - Captures baseline %TEMP% dranalyzer-record-*.tmp files before execution.
    - Monitors new files and delta bytes in a background daemon thread.
    - Emits clean timeline progress every 10 minutes (10m, 20m, 30m, ...).
    - Detects transition to CSV generation stage immediately.
    """
    def __init__(self, temp_out_dir: str, log_cb=None, interval_minutes: int = 10):
        self.temp_out_dir = temp_out_dir
        self.log_cb = log_cb
        self.interval_minutes = interval_minutes
        self.stop_event = threading.Event()
        self.thread = None
        self.start_time = None
        self.baseline_files = set()
        self.temp_dir = os.environ.get('TEMP', '')
        self.csv_stage_reported = False

    def start(self):
        self.start_time = time.time()
        self.stop_event.clear()
        self.csv_stage_reported = False
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                self.baseline_files = set(glob.glob(os.path.join(self.temp_dir, 'dranalyzer-record-*.tmp')))
            else:
                self.baseline_files = set()
        except Exception:
            self.baseline_files = set()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> float:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        elapsed = time.time() - (self.start_time or time.time())
        return elapsed

    @staticmethod
    def format_time(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}시간 {m}분 {s}초"
        return f"{m}분 {s}초"

    def _run(self):
        last_reported_ten_min = 0
        while not self.stop_event.wait(timeout=2.0):
            elapsed = time.time() - self.start_time
            current_ten_min = int(elapsed // (self.interval_minutes * 60))

            # 1. Check if CSV files started generating in temp_out_dir
            if not self.csv_stage_reported and os.path.exists(self.temp_out_dir):
                csv_files = glob.glob(os.path.join(self.temp_out_dir, "**", "*.csv"), recursive=True)
                if csv_files:
                    self.csv_stage_reported = True
                    if self.log_cb:
                        time_str = self.format_time(elapsed)
                        self.log_cb(f"   [📄 CSV 파일 생성 단계 진입 | 경과: {time_str}] 슬롯 레코드 빌드 완료 ➔ FAV CSV 파일 디스크 출력 중 ({len(csv_files)}개 생성됨)...")

            # 2. Check 10-minute periodic interval
            if current_ten_min > last_reported_ten_min:
                last_reported_ten_min = current_ten_min
                time_str = self.format_time(elapsed)

                delta_count = 0
                delta_bytes = 0
                try:
                    if self.temp_dir and os.path.exists(self.temp_dir):
                        cur_files = set(glob.glob(os.path.join(self.temp_dir, 'dranalyzer-record-*.tmp')))
                        new_files = cur_files - self.baseline_files
                        delta_count = len(new_files)
                        delta_bytes = sum(os.path.getsize(f) for f in new_files if os.path.exists(f))
                except Exception:
                    pass

                delta_gb = delta_bytes / (1024 ** 3)
                if self.log_cb:
                    if not self.csv_stage_reported:
                        self.log_cb(f"   [⏳ 연산 진행 중 | 경과: {time_str}] 슬롯 디코딩 레코드: {delta_count}개 (+{delta_gb:.2f} GB 누적 연산 중)")
                    else:
                        self.log_cb(f"   [⏳ CSV 출력 진행 중 | 경과: {time_str}]")


class OptisExtractor:
    """Manages CLI-based high-speed CSV extraction from DRM log files."""

    def __init__(self, cache_dir: str):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def extract(self, drm_files: List[str], fav_list: List[str], model_file_path: str = "", log_cb=None) -> Dict[str, Dict[str, str]]:
        """
        OPTis-S4 CLI Extraction Pipeline:
        - Direct CM (Create Model) single-pass execution.
        - Robust timeout and process cleanup to prevent hangs.
        - Marker: Generate 0-byte completed markers for empty scenario FAVs.
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

                # Direct CM (Create Model) Single Execution
                cmd_cm = [OPTIS_EXE, "-CM", drm_file_win, temp_out]
                if missing_favs:
                    cmd_cm.extend(["-FEP", fav_args_win])
                if missing_l3:
                    cmd_cm.extend(["-MEP", "G", "D", "BRC", "L3"])
                cmd_cm.append("-MG")

                if log_cb:
                    log_cb(f"   ➔ OPTis-S4 -CM (Create Model) 실행 시작 (대용량 파일은 수십 분 소요될 수 있습니다)...")

                elapsed_sec = 0.0
                if os.path.exists(OPTIS_EXE):
                    monitor = OptisProgressMonitor(temp_out, log_cb=log_cb, interval_minutes=10)
                    monitor.start()
                    try:
                        subprocess.run(
                            cmd_cm,
                            cwd=OPTIS_DIR,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=subprocess.HIGH_PRIORITY_CLASS,
                            timeout=None
                        )
                    except Exception as e:
                        if log_cb:
                            log_cb(f"   [!] OPTis-S4 실행 중 예외 발생: {e}")
                    finally:
                        elapsed_sec = monitor.stop()
                        subprocess.run(['taskkill', '/f', '/im', 'OPTis-S4 Analyzer.exe'], capture_output=True)
                        time.sleep(0.5)

                if log_cb:
                    tot_time_str = OptisProgressMonitor.format_time(elapsed_sec)
                    log_cb(f"   ➔ OPTis-S4 실행 완료 (총 소요 시간: {tot_time_str}), 생성된 CSV 파일 수합 중...")

                # Move generated CSVs
                valid_generated = False
                for csv_path in glob.glob(os.path.join(temp_out, "**", "*.csv"), recursive=True):
                    if os.path.getsize(csv_path) > 0:
                        valid_generated = True
                    new_path = os.path.join(self.cache_dir, os.path.basename(csv_path))
                    shutil.move(csv_path, new_path)
                    csv_name = os.path.basename(new_path).upper()
                    csv_clean = re.sub(r'[^A-Za-z0-9가-힣]', '', csv_name).upper()

                    for kw, key in FAV_MAP.items():
                        if kw in csv_name:
                            matched_csvs[key] = new_path
                    if "MESSAGEBROWSER" in csv_clean and drm_clean in csv_clean:
                        matched_csvs["L3_MSG"] = new_path

                # 0-Byte completed marker:
                # 유효 데이터 CSV가 최소 1개 이상 수합된 정상 세션에 한해, 측정되지 않은 나머지 FAV에 대해 목 파일 보완
                has_any_valid_data = valid_generated or any(os.path.exists(p) and os.path.getsize(p) > 0 for p in matched_csvs.values())
                if has_any_valid_data:
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
                else:
                    if log_cb:
                        log_cb(f"   [!] 유효한 CSV 데이터가 디스크에 생성되지 않았습니다.")

                shutil.rmtree(temp_out, ignore_errors=True)


            file_dict[drm_name] = matched_csvs

        if os.path.exists(OPTIS_EXE):
            subprocess.run(['taskkill', '/f', '/im', 'OPTis-S4 Analyzer.exe'], capture_output=True)
        return file_dict
