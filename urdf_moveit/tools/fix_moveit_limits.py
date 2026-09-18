#!/usr/bin/env python3
"""MoveIt Setup Assistant 로 config 생성 직후 실행: 가속도 리밋 수정.

생성된 joint_limits.yaml 은 has_acceleration_limits: false / max_acceleration: 0 이라
Plan 이 실패한다. 이를 true / 10.0 으로 바꾼다.

사용법 (워크스페이스 루트에서):
  python3 tools/fix_moveit_limits.py                      # 기본: src/sh_gen2_moveit_config
  python3 tools/fix_moveit_limits.py src/다른_moveit_config
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
pkg = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / 'sh_gen2_moveit_config'
f = pkg / 'config' / 'joint_limits.yaml'
if not f.is_file():
    sys.exit(f'[에러] 파일이 없습니다: {f}')

t = f.read_text()
t, n1 = re.subn(r'has_acceleration_limits:\s*false', 'has_acceleration_limits: true', t)
t, n2 = re.subn(r'max_acceleration:\s*0(\.0+)?\s*$', 'max_acceleration: 10.0', t, flags=re.M)
f.write_text(t)
print(f'{f}\n  has_acceleration_limits -> true : {n1}개\n  max_acceleration -> 10.0       : {n2}개')
