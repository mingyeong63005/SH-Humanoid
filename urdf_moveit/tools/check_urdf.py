#!/usr/bin/env python3
"""sh_gen2_description 의 URDF 를 점검한다.

사용법 (워크스페이스 루트에서):
  python3 tools/check_urdf.py                 # 기본: src/sh_gen2_description/urdf/sh_gen2.urdf.xacro
  python3 tools/check_urdf.py <파일경로>

점검 항목:
  - xacro 변환 가능 여부 / XML 문법
  - 최상위 링크가 base_link 인지
  - 남아 있는 절대경로(file://)
  - mesh 파일 존재 여부
  - continuous(무한회전) 관절, limit 누락/0 인 관절
  - 조인트 이름이 NAMING 규칙(left_/right_ + ..._joint)을 따르는지
"""
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PKG = 'sh_gen2_description'
PKG_DIR = Path(__file__).resolve().parent.parent / PKG
DEFAULT = PKG_DIR / 'urdf' / 'sh_gen2.urdf.xacro'
EXPECTED = [f'{s}_{j}_joint' for s in ('left', 'right')
            for j in ('shoulder_pitch', 'shoulder_roll', 'shoulder_yaw', 'elbow', 'wrist')]

errors, warns = [], []

def clean_xml_head(text: str) -> str:
    """첫 줄 앞 빈 줄 제거, <?xml ...?> 선언이 맨 앞이 아니면 선언을 지운다 (XML 파싱 에러 방지)."""
    text = text.lstrip()
    if not text.startswith('<?xml'):
        text = re.sub(r'<\?xml[^>]*\?>\s*', '', text, count=1)
    return text


def expand(path: Path) -> str:
    raw = clean_xml_head(path.read_text(errors='ignore'))
    if 'xmlns:xacro' not in raw and '<xacro:' not in raw:
        return raw
    if shutil.which('xacro') is None:
        sys.exit('[에러] xacro 명령이 없습니다. source /opt/ros/jazzy/setup.bash 후 다시 실행하세요.')
    r = subprocess.run(['xacro', str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        # 패키지가 아직 빌드/소스 안 된 경우 $(find) 실패 -> 원본 경로로 치환해서 재시도
        tmp = path.parent / '.check_tmp.xacro'
        tmp.write_text(raw.replace(f'$(find {PKG})', str(PKG_DIR)))
        r = subprocess.run(['xacro', str(tmp)], capture_output=True, text=True)
        tmp.unlink()
    if r.returncode != 0:
        sys.exit(f'[에러] xacro 변환 실패:\n{r.stderr.strip()[:800]}')
    return r.stdout


def main():
    path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT
    if not path.is_file():
        sys.exit(f'[에러] 파일이 없습니다: {path}')
    text = clean_xml_head(expand(path))
    try:
        robot = ET.fromstring(text)
    except ET.ParseError as e:
        sys.exit(f'[에러] XML 문법 오류: {e}')

    links = [l.get('name') for l in robot.findall('link')]
    joints = robot.findall('joint')
    children = {j.find('child').get('link') for j in joints}
    roots = [l for l in links if l not in children]

    # 1. 루트 링크
    if roots != ['base_link']:
        errors.append(f'최상위 링크가 base_link 가 아님: {roots}')

    # 2. 절대경로
    for m in set(re.findall(r'file://[^"]+', text)):
        errors.append(f'절대경로 남아 있음: {m}')

    # 3. mesh 존재 여부
    mesh_refs = set(re.findall(r'filename="([^"]+)"', text))
    for ref in sorted(mesh_refs):
        if not ref.lower().endswith(('.stl', '.dae', '.obj')):
            continue
        prefix = f'package://{PKG}/'
        if ref.startswith(prefix):
            if not (PKG_DIR / ref[len(prefix):]).is_file():
                errors.append(f'mesh 파일 없음: {ref}')
        elif not ref.startswith('file://'):
            warns.append(f'다른 패키지를 가리키는 mesh: {ref}')

    # 4. 관절
    movable = []
    print(f'{"조인트":<32}{"타입":<12}{"범위(rad)":<20}축')
    for j in joints:
        name, jtype = j.get('name'), j.get('type')
        if jtype == 'fixed':
            continue
        movable.append(name)
        lim = j.find('limit')
        axis = j.find('axis').get('xyz') if j.find('axis') is not None else '1 0 0(기본값)'
        rng = '-'
        if lim is not None and jtype != 'continuous':
            lo, hi = float(lim.get('lower', 0)), float(lim.get('upper', 0))
            rng = f'{lo:+.2f} ~ {hi:+.2f}'
            if lo == hi:
                errors.append(f'{name}: 범위가 0 (lower=upper={lo})')
            if float(lim.get('velocity', 0)) == 0:
                warns.append(f'{name}: velocity limit 이 0 (MoveIt 궤적 생성 불가)')
        if jtype == 'continuous':
            warns.append(f'{name}: continuous(무한회전) -> revolute + 실제 범위로 바꾸는 것을 권장')
        elif jtype == 'revolute' and lim is None:
            errors.append(f'{name}: revolute 인데 <limit> 없음')
        print(f'{name:<32}{jtype:<12}{rng:<20}{axis}')

    # 5. 이름 규칙
    unknown = [n for n in movable if n not in EXPECTED]
    missing = [n for n in EXPECTED if n not in movable]
    if unknown:
        warns.append(f'NAMING 규칙과 다른 조인트 이름: {unknown}')
    if missing and not unknown:
        warns.append(f'NAMING 규칙에 있는데 없는 조인트: {missing}')

    print(f'\n링크 {len(links)}개, 움직이는 관절 {len(movable)}개, mesh 참조 {len(mesh_refs)}개')
    for w in warns:
        print(f'  [경고] {w}')
    for e in errors:
        print(f'  [에러] {e}')
    if errors:
        print('\n결과: 에러가 있습니다. 위 항목을 URDF 팀과 확인하세요.')
        sys.exit(1)
    print('\n결과: 통과' + (' (경고는 확인 권장)' if warns else ''))


if __name__ == '__main__':
    main()
