# -*- mode: python ; coding: utf-8 -*-
"""高中物理 v3.0 PyInstaller spec"""
import os
import sys

spec_file = os.path.abspath(SPECPATH)
project_root = os.path.dirname(spec_file)
sys.path.insert(0, project_root)

subject_dir = os.path.join(project_root, 'subjects', '高中物理v3.0')

a = Analysis(
    [os.path.join(subject_dir, 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=[
        # config.json / agent_prompt.json 放在 _internal 根目录，
        # 首次运行时由 main.py 复制到 exe 同级
        (os.path.join(subject_dir, 'config.json'), '.'),
        (os.path.join(subject_dir, 'agent_prompt.json'), '.'),
        (os.path.join(subject_dir, 'subject.py'), '.'),
        (os.path.join(subject_dir, 'app.py'), '.'),
        (os.path.join(project_root, 'shared', 'templates'), 'templates'),
        # macOS 用系统 TeX Live，bundled_texlive 仅 Windows 打包时需要
        # (os.path.join(project_root, 'bundled_texlive'), 'texlive'),
    ],
    hiddenimports=[
        'core',
        'core.parsing',
        'core.api_client',
        'core.pandoc_utils',
        'core.env_config',
        'core.logging_utils',
        'core.config_loader',
        'core.defaults',
        'core.manual_split',
        'core.session_context',
        'core.format_enforcement',
        'core.idml_extractor',
        'core.base_subject',
        'core.config_schema',
        'core.docx_report',
        'core.unit_detect',
        'shared',
        'shared.sympy_tools',
        'shared.sympy_tools.tools',
        'shared.sympy_tools.templates',
        'shared.sympy_tools.sandbox',
        'shared.sympy_tools.safety',
        'shared.web_tools',
        'shared.latex_generator',
        'shared.pdf_compiler',
        'shared.free_proofread',
        'shared.smart_split',
        'shared.review_mode',
        'shared.docx_comments',
        'shared.docx_format_enhancer',
        'shared.chinese_classics_tools',
        'shared.bash_tool',
        'shared.split_post_utils',
        'shared.text_nav_tools',
        'shared.decor_utils',
        'shared.image_utils',
        'shared.physics_tools',
        'shared.chemistry_tools',
        'shared.comment_marker',
        'shared.formula_render',
        'shared.plan_tools',
        'shared.session',
        'shared.shidianguji_playwright',
        'ui',
        'ui.widgets',
        'ui.pipeline',
        'ui.default_app',
        'sympy',
        'sympy.parsing',
        'sympy.parsing.sympy_parser',
        'PIL',
        'PIL.Image',
        'docx',
        'requests',
        'pydantic',
        'langchain_core',
        'langchain_core.tools',
        'langchain_core.messages',
        'langchain_core.output_parsers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'pytest', 'scipy'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='高中物理',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='高中物理',
)
