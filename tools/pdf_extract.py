# -*- coding: utf-8 -*-
"""极简 PDF 文本提取器：解析 xref/对象流 + FlateDecode + ToUnicode CMap，支持中英文。"""
import re, zlib, sys, os, io, collections

def read_objects(data):
    objs = {}
    # 经典 xref 表形式的对象
    for m in re.finditer(rb'(\d{1,6})\s+(\d{1,5})\s+obj\b', data):
        num = int(m.group(1))
        end = data.find(b'endobj', m.end())
        if end == -1:
            continue
        objs[num] = data[m.end():end]
    return objs

def get_stream(obj):
    m = re.search(rb'stream\r?\n', obj)
    if not m:
        return None, obj
    dict_part = obj[:m.start()]
    raw = obj[m.end():]
    e = raw.rfind(b'endstream')
    if e != -1:
        raw = raw[:e]
    if b'FlateDecode' in dict_part:
        for attempt in (raw, raw.rstrip(b'\r\n'), raw.strip()):
            try:
                return zlib.decompress(attempt), dict_part
            except Exception:
                try:
                    return zlib.decompressobj().decompress(attempt), dict_part
                except Exception:
                    continue
        return None, dict_part
    return raw, dict_part

def parse_tounicode(cmap_bytes):
    """返回 code(bytes hex) -> unicode str"""
    text = cmap_bytes.decode('latin-1', 'ignore')
    mapping = {}
    for block in re.findall(r'beginbfchar(.*?)endbfchar', text, re.S):
        for a, b in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            try:
                mapping[a] = ''.join(chr(int(b[i:i+4], 16)) for i in range(0, len(b), 4))
            except Exception:
                pass
    for block in re.findall(r'beginbfrange(.*?)endbfrange', text, re.S):
        for lo, hi, dst in re.findall(r'<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>', block):
            try:
                l, h, d = int(lo, 16), int(hi, 16), int(dst, 16)
                for i in range(h - l + 1):
                    mapping[f'{l+i:0{len(lo)}X}'] = chr(d + i)
            except Exception:
                pass
    return mapping

def decode_with_fonts(content, fontmaps, default_map):
    """粗略解析内容流中的文本，按字体切换解码。"""
    out = []
    cur_map = default_map
    # 监听 Tf 切换字体
    tokens = re.finditer(rb'/([A-Za-z0-9_\.\-\+]+)\s+[\d\.]+\s+Tf|\[(.*?)\]\s*TJ|\((.*?)\)\s*Tj|<([0-9A-Fa-f\s]+)>\s*Tj|(T\*|Td|TD|ET)', content, re.S)
    for t in tokens:
        if t.group(1):
            name = t.group(1).decode('latin-1')
            cur_map = fontmaps.get(name, default_map)
        elif t.group(2) is not None:
            arr = t.group(2)
            for hm in re.finditer(rb'<([0-9A-Fa-f\s]+)>|\((.*?)(?<!\\)\)', arr, re.S):
                if hm.group(1):
                    out.append(hex_to_text(re.sub(rb'\s', b'', hm.group(1)).decode('latin-1'), cur_map))
                elif hm.group(2) is not None:
                    out.append(lit_to_text(hm.group(2), cur_map))
        elif t.group(3) is not None:
            out.append(lit_to_text(t.group(3), cur_map))
        elif t.group(4) is not None:
            out.append(hex_to_text(re.sub(rb'\s', b'', t.group(4)).decode('latin-1'), cur_map))
        elif t.group(5):
            if t.group(5) in (b'T*', b'Td', b'TD'):
                out.append('\n')
    return ''.join(out)

def hex_to_text(h, cmap):
    res = []
    # 先按 4 位一组的 code 尝试
    for i in range(0, len(h) - 3, 4):
        code = h[i:i+4].upper()
        res.append(cmap.get(code, ''))
    if not any(res) and len(h) >= 2:
        res = [cmap.get(h[i:i+2].upper(), '') for i in range(0, len(h) - 1, 2)]
    return ''.join(res)

def lit_to_text(b, cmap):
    res = []
    for i in range(len(b)):
        code = f'{b[i]:02X}'
        res.append(cmap.get(code, chr(b[i]) if 32 <= b[i] < 127 else ''))
    return ''.join(res)

def main(path, outpath):
    data = open(path, 'rb').read()
    objs = read_objects(data)
    # 收集 ToUnicode 流与字体名映射
    fontmaps = {}
    default_map = {}
    cmap_count = 0
    for num, obj in objs.items():
        if b'/ToUnicode' in obj or b'beginbfchar' in obj or b'beginbfrange' in obj:
            stream, _ = get_stream(obj)
            if stream and (b'beginbfchar' in stream or b'beginbfrange' in stream):
                cm = parse_tounicode(stream)
                if cm:
                    cmap_count += 1
                    names = re.findall(rb'/BaseFont\s*/([A-Za-z0-9_\.\-\+]+)', obj)
                    touni = re.search(rb'/ToUnicode\s+(\d+)\s+\d+\s+R', obj)
                    for n in names:
                        fontmaps[n.decode('latin-1')] = cm
                    if not default_map:
                        default_map = cm
    # 收集页面内容流
    chunks = []
    for num, obj in objs.items():
        if b'/Font' in obj and b'stream' not in obj:
            for fn, ref in re.findall(rb'/([A-Za-z0-9_\.\-\+]+)\s+(\d+)\s+\d+\s+R', obj):
                refobj = objs.get(int(ref), b'')
                tm = re.search(rb'/ToUnicode\s+(\d+)\s+\d+\s+R', refobj)
                if tm:
                    st, _ = get_stream(objs.get(int(tm.group(1)), b''))
                    if st:
                        cm = parse_tounicode(st)
                        if cm:
                            fontmaps[fn.decode('latin-1')] = cm
                            if not default_map:
                                default_map = cm
    for num, obj in objs.items():
        if b'stream' not in obj:
            continue
        stream, dpart = get_stream(obj)
        if not stream:
            continue
        if b'Tj' in stream or b'TJ' in stream:
            chunks.append(decode_with_fonts(stream, fontmaps, default_map))
    text = '\n'.join(chunks)
    text = re.sub(r'\n{3,}', '\n\n', text)
    open(outpath, 'w', encoding='utf-8').write(text)
    print(f"objects={len(objs)} cmaps={cmap_count} fonts={len(fontmaps)} chars={len(text)} -> {outpath}")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
