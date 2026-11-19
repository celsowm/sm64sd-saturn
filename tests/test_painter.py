import shutil
import subprocess
import tempfile
import unittest
import os
from pathlib import Path


class PainterTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('cc'), 'C compiler missing')
    def test_triangle_depth_relations(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'painter'
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=undefined', '-I', str(root / 'runtime'),
                            str(root / 'runtime/sm64ds_painter.c'),
                            str(root / 'tests/host_painter.c'), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

    @unittest.skipUnless(shutil.which('cc') and shutil.which('c++'), 'C/C++ compiler missing')
    def test_bucket_plan_matches_installed_sdk(self):
        root = Path(__file__).resolve().parents[1]
        sdk = Path(os.environ.get('LIBSATURN_SOURCE', root.parent / 'lib-saturn'))
        if not (sdk / 'src/graphics/3d/rendering/logic.hpp').is_file():
            self.skipTest('LibSaturn source checkout not available')
        with tempfile.TemporaryDirectory() as directory:
            obj, exe = Path(directory) / 'painter.o', Path(directory) / 'check'
            subprocess.run(['cc', '-std=c11', '-I', str(root / 'runtime'), '-c',
                            str(root / 'runtime/sm64ds_painter.c'), '-o', str(obj)], check=True)
            subprocess.run(['c++', '-std=c++17', '-I', str(root / 'runtime'),
                            '-I', str(sdk), '-I', str(sdk / 'include'),
                            str(root / 'tests/host_painter_sdk.cpp'), str(obj), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
