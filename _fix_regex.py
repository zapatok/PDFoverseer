
import re

# Read, patch, write
txt = open('sr_tester.py', encoding='utf-8').read()

# Patch by replacing the whole _PAGE_RE block
old_block = re.search(r'_PAGE_RE = re\.compile\(.*?\)', txt, re.DOTALL)
if old_block:
    print("Found. Replacing...")
    good = ('_PAGE_RE = re.compile(\n'
            '    r"P.{0,2}[gq](?:ina?)?' + r'\\.?\s*(\d{1,3})\s*\\.?\s*de\s*(\d{1,3})",' + '\n'
            '    re.IGNORECASE,\n'
            ')')
    txt2 = txt[:old_block.start()] + good + txt[old_block.end():]
    open('sr_tester.py', 'w', encoding='utf-8').write(txt2)
    # Verify
    m2 = re.search(r'_PAGE_RE = re\.compile\((.+?)\)', txt2, re.DOTALL)
    print("New block:", repr(m2.group(1)))
    # Test the regex itself
    test_re = re.compile(r'P.{0,2}[gq](?:ina?)?\.?\s*(\d{1,3})\s*\.?\s*de\s*(\d{1,3})', re.IGNORECASE)
    for s in ['Pagina 1 de 2', 'Pagina 1de 2', 'Pagina 1.de 2', 'Pqina 1 de 2']:
        m = test_re.search(s)
        print(f"  '{s}' → {m.group(1)+' de '+m.group(2) if m else 'NO MATCH'}")
else:
    print("Block not found!")
