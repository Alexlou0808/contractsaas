"""Lease contract data extraction from OCR text."""

import json
import re
from .ocr_engine import normalize_ocr_text


def extract_contract_data(contract_texts: dict[int, str]) -> dict:
    """Extract main contract fields: areas, rents, etc."""
    data: dict = {}
    all_text = normalize_ocr_text("\n".join(contract_texts.values()))

    # Area patterns - support various bracket types
    bra = r'[〔(（【\[]'
    ket = r'[〕)）\]】]'
    area_patterns = [
        (rf'合作面积\s*{bra}\s*([\d.]+)\s*{ket}', '合作面积'),
        (r'合作面积.{0,3}?(\d+\.?\d*)\s*平', '合作面积'),
        (rf'[其q共]中\s*商业\s*{bra}\s*(\d+\.?\d*)\s*{ket}', '商业面积'),
        (rf'[其q共]中\s*住宅\s*{bra}\s*(\d+\.?\d*)\s*{ket}', '住宅面积'),
        (rf'基底面积\s*{bra}\s*([\d.]+)\s*{ket}', '基底面积'),
        (r'基底面积.{0,3}?(\d+\.?\d*)', '基底面积'),
    ]
    for pat, key in area_patterns:
        if key not in data:
            m = re.search(pat, all_text, re.DOTALL)
            if m:
                try:
                    data[key] = float(m.group(1))
                except ValueError:
                    pass

    # 商业面积 = 合作面积 - 住宅面积 (fallback)
    if '商业面积' not in data and '合作面积' in data and '住宅面积' in data:
        data['商业面积'] = round(data['合作面积'] - data['住宅面积'], 2)

    # Monthly rent from contract terms page (小写: s15742.40/月 or 515742.40/月)
    for pg, text in contract_texts.items():
        clean = normalize_ocr_text(text)
        m = re.search(
            r'商业.*?基本合作收益.*?小\s*写\s*[:：]?\s*[xXsS5]?\s*([\d.]+(?:\s+\d+)?)\s*/?\s*月',
            clean, re.DOTALL,
        )
        if m and '商业月租金' not in data:
            try:
                val = float(m.group(1).strip().replace(' ', '.'))
                if 500 < val < 1000000:
                    data['商业月租金'] = val
            except ValueError:
                pass

        m = re.search(
            r'住宅\s*用\s*途.*?基本合作收益.*?小\s*写\s*[:：]?\s*[xXsS5]?\s*([\d.]+(?:\s+\d+)?)\s*/?\s*月',
            clean, re.DOTALL,
        )
        if m and '住宅月租金' not in data:
            try:
                val = float(m.group(1).strip().replace(' ', '.'))
                if 500 < val < 1000000:
                    data['住宅月租金'] = val
            except ValueError:
                pass

    # Rent from 收益明细表
    for pg, text in contract_texts.items():
        if "收益明细" not in text and "明细表" not in text:
            continue
        clean = normalize_ocr_text(text)
        for line in clean.split("\n"):
            line = line.strip()
            if not line:
                continue
            nums = re.findall(r'(\d+\.?\d*)', line)
            if len(nums) < 2:
                continue
            if '住' in line and '住宅月租金' not in data:
                try:
                    data['住宅月租金'] = float(nums[-1])
                    data['住宅单价'] = float(nums[-2])
                except ValueError:
                    pass
            if '商' in line and '商业月租金' not in data:
                try:
                    data['商业月租金'] = float(nums[-1])
                    data['商业单价'] = float(nums[-2])
                except ValueError:
                    pass

    return data


def extract_survey_data(survey_texts: dict[int, str]) -> dict:
    """Extract floor-by-floor area table from survey report."""
    data: dict = {}
    floors: dict = {}

    summary_text = _find_best_summary_page(survey_texts)
    if not summary_text:
        return data

    for line in summary_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        floor_label = None
        remainder = line
        is_roof = False

        m = re.match(r'\s*(\d{1,2})\s+', line)
        if m:
            fl = m.group(1)
            if 1 <= int(fl) <= 20:
                floor_label = fl
                remainder = line[m.end():]

        if '屋面' in line:
            is_roof = True
            floor_label = '屋面'
            idx = line.find('屋面')
            remainder = line[idx + 2:]

        if floor_label is None:
            continue
        if '合计' in remainder:
            remainder = remainder.split('合计')[0]

        raw_nums = re.findall(r'(\d+\.?\d*)', remainder)
        nums = []
        for n in raw_nums:
            try:
                nums.append(float(n))
            except ValueError:
                continue
        if not nums:
            continue

        rem_text = re.sub(r'[\d.]+', '', remainder)
        rem_text = re.sub(r'[|一一~\-]', '', rem_text).strip()
        remark = re.sub(r'\s+', '', rem_text) if rem_text else ''
        remark = re.sub(r'[^一-鿿()（）]', '', remark) if remark else ''

        full_area = nums[0]
        half_area = 0.0
        subtotal = full_area
        h_proj = 0.0
        drip = 0.0

        if len(nums) == 1:
            subtotal = full_area
        elif len(nums) == 2:
            subtotal = nums[1]
        elif is_roof and len(nums) >= 4:
            full_area, half_area, subtotal, h_proj = nums[0], nums[1], nums[2], nums[3]
            drip = nums[4] if len(nums) > 4 else 0.0
        else:
            j = 1
            while j < len(nums):
                if nums[j] >= full_area * 0.95:
                    subtotal = nums[j]
                    break
                j += 1
            if j >= 2:
                half_area = nums[1]
                if half_area >= full_area * 0.95:
                    half_area = 0.0

        floors[floor_label] = {
            '全面积': full_area,
            '半面积': half_area,
            '小计': subtotal,
            '水平投影': h_proj,
            '滴水': drip,
            '备注': remark if remark else '',
        }

    # Summary fields
    for pg, text in survey_texts.items():
        clean = normalize_ocr_text(text)
        for pat, key in [
            (r'建筑面积\s*(\d+\.?\d*)\s*平', '总建筑面积'),
            (r'基底面积\s*(\d+\.?\d*)', '基底面积'),
            (r'(?:建筑层数|层数)\s*(\d+)', '楼层数'),
        ]:
            if key in data:
                continue
            m = re.search(pat, clean)
            if m:
                try:
                    data[key] = float(m.group(1)) if '.' in m.group(1) else int(m.group(1))
                except ValueError:
                    pass

    data['楼层面积明细'] = floors
    data['各层面积明细'] = _format_floor_summary(floors)
    data['备注明细'] = _format_floor_remarks(floors)

    return data


def _find_best_summary_page(survey_texts: dict[int, str]) -> str:
    best_text = ""
    best_score = -1
    for pg in sorted(survey_texts.keys()):
        text = survey_texts[pg]
        if "建筑面积" not in text and "面积汇总" not in text:
            continue
        candidate = normalize_ocr_text(text)
        score = sum(10 for line in candidate.split("\n")
                    if re.match(r'0[1-9]\s+\d+\.?\d*', line.strip()))
        score -= sum(1 for line in candidate.split("\n")
                     if re.match(r'[1-9]\s+0[1-9]', line.strip()))
        if score > best_score:
            best_score = score
            best_text = candidate

    if not best_text:
        for pg in sorted(survey_texts.keys()):
            text = normalize_ocr_text(survey_texts[pg])
            score = sum(1 for line in text.split("\n")
                        if re.match(r'\s*0?\d\s', line))
            if score > best_score:
                best_score = score
                best_text = text
    return best_text


def _format_floor_summary(floors: dict) -> str:
    def sort_key(k):
        if k == '屋面':
            return (1, 0)
        try:
            return (0, int(k))
        except ValueError:
            return (2, k)
    parts = []
    for fk in sorted(floors.keys(), key=sort_key):
        info = floors[fk]
        label = fk if fk == '屋面' else f"{fk}层"
        parts.append(f"{label}{info.get('小计', 0)}m²")
    return '; '.join(parts)


def _format_floor_remarks(floors: dict) -> str:
    def sort_key(k):
        if k == '屋面':
            return (1, 0)
        try:
            return (0, int(k))
        except ValueError:
            return (2, k)
    parts = []
    for fk in sorted(floors.keys(), key=sort_key):
        info = floors[fk]
        label = fk if fk == '屋面' else f"{fk}层"
        rmk = info.get('备注', '')
        parts.append(f"{label}{rmk}" if rmk else f"{label}无")
    return '; '.join(parts)
