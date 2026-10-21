# -*- coding: utf-8 -*-
"""把报告 HTML 里的图片全部内联成 data URI，产出一个「单文件自包含」分享版。

为什么需要：报告里的图片有两类来源，单独发 HTML 时都会变空框 ——
  1. `assets/hotspot_xxx.jpg`  本地相对路径，文件没跟着走就 404
  2. `https://cdn.poizon.com/…` 远程外链，对方网络/防盗链/图片过期就加载不出来

这个脚本把两类都取下来、按实际显示尺寸压缩（热点长图 / 案例缩略图分别给宽度），
再 base64 内联进 HTML。产出的单文件随便发微信、邮件、钉钉都能直接看，图片不再丢。

用法：
    python inline_images.py 报告.html
    python inline_images.py 报告.html --out 分享版.html --hotspot-width 1400 --case-width 360

也可以被 build_report.py 调用：
    from inline_images import inline_html
    inline_html("报告.html", "报告-单文件分享版.html")
"""

import argparse
import base64
import io
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

try:
    from PIL import Image
except ImportError:  # 允许模块被 import，真正用到时再报错
    Image = None

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/122.0 Safari/537.36')
ATTR_RE = re.compile(r"""(?P<attr>src|href)=(?P<q>['"])(?P<val>[^'"]+)(?P=q)""")
IMAGE_EXT_RE = re.compile(r'\.(jpe?g|png|webp|gif|bmp)(\?.*)?$', re.I)


def _to_jpeg_bytes(raw, max_w, quality):
    """任意图片字节 → 压到指定宽度、白底 JPEG 字节。"""
    if Image is None:
        raise RuntimeError('缺少 Pillow，请先安装：python -m pip install pillow')
    im = Image.open(io.BytesIO(raw))
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA')
        bg = Image.new('RGB', im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    else:
        im = im.convert('RGB')
    if im.width > max_w:
        new_h = max(1, round(im.height * max_w / im.width))
        im = im.resize((max_w, new_h), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=quality, optimize=True, progressive=True)
    return buf.getvalue(), im.size


def _fetch(url, timeout=30):
    req = Request(url, headers={
        'User-Agent': UA,
        'Referer': 'https://www.dewu.com/',
        'Accept': 'image/avif,image/webp,image/*,*/*;q=0.8',
    })
    return urlopen(req, timeout=timeout).read()


def _data_uri(raw):
    return 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii')


def inline_html(src_html, out_path=None, hotspot_width=1400, case_width=360,
                hotspot_quality=82, case_quality=80, workers=8, verbose=True):
    """把 src_html 里的本地图 + 得物 CDN 图内联，写到 out_path，返回统计 dict。"""
    def log(*a):
        if verbose:
            print(*a)

    t0 = time.time()
    src_html = os.path.abspath(src_html)
    if not os.path.isfile(src_html):
        raise FileNotFoundError(src_html)
    base_dir = os.path.dirname(src_html)
    out_path = out_path or re.sub(r'\.html?$', '', src_html, flags=re.I) + '-单文件分享版.html'
    orig_size = os.path.getsize(src_html)

    html = open(src_html, encoding='utf-8').read()

    # ---- 1. 收集图片地址 ----
    refs = set()
    for m in ATTR_RE.finditer(html):
        val = m.group('val')
        if val.startswith('data:'):
            continue
        if val.startswith(('http://', 'https://')):
            if 'poizon' in val and IMAGE_EXT_RE.search(val):
                refs.add(val)
        elif not val.startswith(('#', 'mailto:', 'javascript:')) and IMAGE_EXT_RE.search(val):
            refs.add(val)

    local_refs = sorted(r for r in refs if not r.startswith('http'))
    remote_refs = sorted(r for r in refs if r.startswith('http'))
    log('待内联：本地 %d 张，远程 %d 张' % (len(local_refs), len(remote_refs)))

    mapping, failed = {}, []

    # ---- 2. 本地图（热点长图）----
    for ref in local_refs:
        path = os.path.join(base_dir, ref.replace('/', os.sep))
        try:
            raw = open(path, 'rb').read()
            small, size = _to_jpeg_bytes(raw, hotspot_width, hotspot_quality)
            mapping[ref] = _data_uri(small)
            log('  [本地] %-34s %6dKB → %4dKB %dx%d' % (
                ref, len(raw) // 1024, len(small) // 1024, size[0], size[1]))
        except Exception as e:  # noqa: BLE001
            failed.append((ref, str(e)))
            log('  [本地] %s 失败：%s' % (ref, e))

    # ---- 3. 远程图（案例缩略图），带重试 ----
    def work(url):
        last = None
        for attempt in range(3):
            try:
                raw = _fetch(url, timeout=30 + attempt * 15)
                small, size = _to_jpeg_bytes(raw, case_width, case_quality)
                return url, _data_uri(small), len(raw), len(small), size, None
            except Exception as e:  # noqa: BLE001
                last = str(e)
                time.sleep(0.8 * (attempt + 1))
        return url, None, 0, 0, (0, 0), last

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for url, uri, rsz, ssz, size, err in pool.map(work, remote_refs):
            done += 1
            if uri:
                mapping[url] = uri
                if done <= 5 or done % 20 == 0:
                    log('  [远程] %d/%d …%s %5dKB → %4dKB' % (
                        done, len(remote_refs), url[-28:], rsz // 1024, ssz // 1024))
            else:
                failed.append((url, err))
                log('  [远程] 失败 %s → %s' % (url, err))

    # ---- 4. 替换 ----
    hit = {'local': 0, 'remote': 0}

    def repl(m):
        attr, q, val = m.group('attr'), m.group('q'), m.group('val')
        uri = mapping.get(val)
        if not uri:
            return m.group(0)
        hit['remote' if val.startswith('http') else 'local'] += 1
        return '%s=%s%s%s' % (attr, q, uri, q)

    new_html = ATTR_RE.sub(repl, html)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(new_html)

    out_size = os.path.getsize(out_path)
    stats = {
        'src': src_html, 'out': out_path,
        'localInlined': hit['local'], 'remoteInlined': hit['remote'],
        'failed': failed, 'origSize': orig_size, 'outSize': out_size,
        'seconds': round(time.time() - t0, 1),
    }
    log('')
    log('─' * 58)
    log('内联成功：本地 %d 处 / 远程 %d 处，失败 %d 张' % (
        hit['local'], hit['remote'], len(failed)))
    for u, e in failed[:10]:
        log('  ! %s → %s' % (u[:80], e))
    log('原文件：%8.0f KB' % (orig_size / 1024))
    log('分享版：%8.2f MB（图片已全部内嵌，可单独发送）' % (out_size / 1048576))
    log('输出：%s' % out_path)
    log('耗时：%.1fs' % stats['seconds'])
    if failed:
        log('\n提示：失败的图保留原地址，其余图片不受影响。')
    return stats


def main():
    ap = argparse.ArgumentParser(description='把报告 HTML 的图片全部内联，产出单文件分享版')
    ap.add_argument('html', help='原报告 HTML')
    ap.add_argument('--out', help='输出路径（默认 <原名>-单文件分享版.html）')
    ap.add_argument('--hotspot-width', type=int, default=1400, help='热点长图最大宽度（默认 1400）')
    ap.add_argument('--case-width', type=int, default=360, help='案例缩略图最大宽度（默认 360）')
    ap.add_argument('--hotspot-quality', type=int, default=82, help='热点长图 JPEG 质量（默认 82）')
    ap.add_argument('--case-quality', type=int, default=80, help='案例缩略图 JPEG 质量（默认 80）')
    ap.add_argument('--workers', type=int, default=8, help='远程图片并发数（默认 8）')
    args = ap.parse_args()

    if Image is None:
        sys.exit('缺少 Pillow，请先安装：python -m pip install pillow')

    try:
        st = inline_html(args.html, args.out, args.hotspot_width, args.case_width,
                         args.hotspot_quality, args.case_quality, args.workers)
    except FileNotFoundError:
        sys.exit('找不到文件：%s' % args.html)
    if st['failed']:
        sys.exit(0)


if __name__ == '__main__':
    main()
