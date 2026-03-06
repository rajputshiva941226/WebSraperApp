# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

# Collect all Scrapy ecosystem packages
scrapy_packages = [
    'lxml', 'cssselect', 'parsel', 'scrapy', 'w3lib', 'twisted', 
    'fuzzywuzzy', 'pandas', 'urllib3', 'certifi', 'charset_normalizer',
    'idna', 'requests', 'six', 'pyopenssl', 'cryptography', 'cffi'
]

all_datas = []
all_binaries = []
all_hiddenimports = []

for package in scrapy_packages:
    try:
        datas, binaries, hiddenimports = collect_all(package)
        all_datas.extend(datas)
        all_binaries.extend(binaries)
        all_hiddenimports.extend(hiddenimports)
        print(f"Successfully collected {package}")
    except Exception as e:
        print(f"Warning: Could not collect {package}: {e}")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=all_binaries,
    datas=[
        ('db-1.txt', '.'), 
        ('PMC_New_Edit\\items.py','.'),
        ('PMC_New_Edit\\middlewares.py','.'),
        ('PMC_New_Edit\\pipelines.py','.'),
        ('PMC_New_Edit\\settings.py','.'),
        ('PMC_New_Edit\\spiders','spiders'),
        ('scrapy.cfg','.'),
    ] + all_datas,
    hiddenimports=[
        # Core Python
        'pkg_resources', 'pkg_resources.py2_warn',
        # lxml
        'lxml', 'lxml.etree', 'lxml.html', 'lxml._elementpath', 'lxml.objectify',
        # cssselect  
        'cssselect', 'cssselect.parser', 'cssselect.xpath',
        # parsel
        'parsel', 'parsel.selector', 'parsel.csstranslator',
        # w3lib
        'w3lib', 'w3lib.html', 'w3lib.url', 'w3lib.encoding', 'w3lib.util',
        # scrapy
        'scrapy', 'scrapy.selector', 'scrapy.http', 'scrapy.spiders',
        'scrapy.utils.misc', 'scrapy.core.scraper', 'scrapy.utils.request',
        'scrapy.downloadermiddlewares', 'scrapy.spidermiddlewares',
        # twisted
        'twisted', 'twisted.internet', 'twisted.internet.defer',
        'twisted.internet.asyncioreactor', 'twisted.protocols.tls',
        # others
        'fuzzywuzzy', 'pandas', 're', 'json', 'csv'
    ] + all_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PMCNCBICrawlerVer01',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)