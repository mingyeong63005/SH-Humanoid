#!/usr/bin/env python3
"""URDF 팀(fusion2urdf) 결과물을 sh_gen2_description 패키지로 가져온다.

사용법 (워크스페이스 루트에서):
  python3 tools/import_urdf.py <URDF팀이 준 폴더>
  예) python3 tools/import_urdf.py ~/Downloads/sh_gen2_description

하는 일:
  1. 받은 폴더에서 urdf/xacro 관련 파일과 meshes 파일을 찾아 복사
     (urdf 폴더 안의 하위 폴더(.usd 등)는 무시)
  2. mesh / include 경로를 전부 package://sh_gen2_description/... 형식으로 변환
     - file:///home/누군가/...        (절대경로)
     - file://$(find 다른패키지)/...   (fusion2urdf 기본 출력)
     - package://다른패키지/...
  3. 메인 모델 파일을 urdf/sh_gen2.urdf.xacro 로 저장 (display.launch.py 기본값)
  4. check_urdf.py 로 자동 점검
기존 urdf/, meshes/ 는 워크스페이스의 urdf_backups/<시각>/ 으로 백업한다.
"""
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PKG = 'sh_gen2_description'
MAIN_NAME = 'sh_gen2.urdf.xacro'
MODEL_EXT = {'.urdf', '.xacro', '.gazebo', '.trans'}
MESH_EXT = {'.stl', '.dae', '.obj'}

TOOLS = Path(__file__).resolve().parent
BASE = TOOLS.parent
PKG_DIR = BASE / PKG

def clean_xml_head(text: str) -> str:
    """첫 줄 앞 빈 줄 제거, <?xml ...?> 선언이 맨 앞이 아니면 선언을 지운다 (XML 파싱 에러 방지)."""
    text = text.lstrip()
    if not text.startswith('<?xml'):
        text = re.sub(r'<\?xml[^>]*\?>\s*', '', text, count=1)
    return text


def find_files(src: Path):
    model, mesh = [], []
    for f in src.rglob('*'):
        if not f.is_file():
            continue
        parts = {p.lower() for p in f.relative_to(src).parts[:-1]}
        if parts & {'build', 'install', 'log', '.git'}:
            continue
        ext = f.suffix.lower()
        if ext in MODEL_EXT and f.parent.name == 'urdf':
            model.append(f)
        elif ext in MESH_EXT:
            mesh.append(f)
    if not model:  # urdf 폴더가 없는 경우: 최상위에 있는 파일도 허용
        model = [f for f in src.iterdir() if f.is_file() and f.suffix.lower() in MODEL_EXT]
    return model, mesh


def fix_paths(text: str) -> str:
    text = clean_xml_head(text)
    # mesh 경로 (어떤 형식이든) -> package://PKG/meshes/파일명
    text = re.sub(r'filename="[^"]*?/meshes/([^"/]+)"',
                  rf'filename="package://{PKG}/meshes/\1"', text)
    # xacro include 등의 $(find 다른패키지) -> $(find PKG)
    text = re.sub(r'\$\(find [^)]+\)', f'$(find {PKG})', text)
    # 남아 있는 package://다른패키지/ -> package://PKG/
    text = re.sub(r'package://(?!%s/)[^/"]+/' % PKG, f'package://{PKG}/', text)
    return text


def pick_main(files):
    """<robot> 태그가 있는 파일 중 링크가 있는 xacro 우선, 그다음 <link> 가 가장 많은 파일."""
    best, best_key = None, None
    for f in files:
        t = f.read_text(errors='ignore')
        if '<robot' not in t:
            continue
        n = t.count('<link')
        key = (f.suffix == '.xacro' and n > 0, n)
        if best_key is None or key > best_key:
            best, best_key = f, key
    return best


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1]).expanduser().resolve()
    if not src.is_dir():
        sys.exit(f'[에러] 폴더가 없습니다: {src}')
    if not PKG_DIR.is_dir():
        sys.exit(f'[에러] 패키지 폴더가 없습니다: {PKG_DIR}')

    model, mesh = find_files(src)
    main_file = pick_main(model)
    print(f'찾은 모델 파일 {len(model)}개, mesh {len(mesh)}개')
    if main_file is None:
        sys.exit('[에러] <robot> 태그가 있는 urdf/xacro 파일을 못 찾았습니다.')
    print(f'메인 모델: {main_file.name}')

    # 백업
    stamp = time.strftime('%Y%m%d_%H%M%S')
    backup = BASE / 'urdf_backups' / stamp
    backup.mkdir(parents=True)
    for d in ('urdf', 'meshes'):
        if (PKG_DIR / d).exists():
            shutil.move(str(PKG_DIR / d), str(backup / d))
        (PKG_DIR / d).mkdir()
    (PKG_DIR / 'meshes' / '.gitkeep').touch()
    print(f'기존 파일 백업: {backup.relative_to(BASE.parent)}')

    for f in mesh:
        dst = PKG_DIR / 'meshes' / f.name
        if dst.exists():
            print(f'  [경고] mesh 이름 중복, 덮어씀: {f.name}')
        shutil.copy2(f, dst)
    for f in model:
        name = MAIN_NAME if f == main_file else f.name
        (PKG_DIR / 'urdf' / name).write_text(fix_paths(f.read_text(errors='ignore')))

    # 원래 이름으로 메인 파일을 include 하는 다른 파일이 있을 수 있어 사본도 남김
    if main_file.name != MAIN_NAME:
        shutil.copy2(PKG_DIR / 'urdf' / MAIN_NAME, PKG_DIR / 'urdf' / main_file.name)

    print('\n복사 및 경로 변환 완료. 점검을 시작합니다.\n')
    rc = subprocess.call([sys.executable, str(TOOLS / 'check_urdf.py')])
    print('\n다음 단계:')
    print('  colcon build --packages-select sh_gen2_description && source install/setup.bash')
    print('  ros2 launch sh_gen2_description display.launch.py')
    sys.exit(rc)


if __name__ == '__main__':
    main()
