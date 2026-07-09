#!/usr/bin/env python3
"""
Document Release-Date Fallback engine (core/automation/release_doc_fallback.py).

Jira is the PRIMARY release authority. This module is the documented FALLBACK
(release-filter-policy.md § "Document Release-Date Fallback"): when an in-scope
fixVersion is unreleased / date-less in Jira, consult the enterprise release-notes
.docx.

Two levels:
  * VERSION-level (reliable, exact): version number -> release date, parsed from
    headings like "8.1.1 (2026-06-02)". Used to confirm a version's release.
  * STORY-level (fuzzy, gated): for a Jira story that has NO fixVersion, match its
    summary+description keywords to the doc's per-version feature lines. Score is
    keyword-containment. score >= APPLY_THRESHOLD -> apply (source=doc, score logged);
    below -> WARNING only, never a silent write.

Public API:
  parse(docx_path) -> ReleaseDoc
  ReleaseDoc.version_date(version) -> "YYYY-MM-DD" | None   (None if placeholder/absent)
  ReleaseDoc.match_story(summary, description="") -> dict    (best match + score + verdict)
"""
import re, sys, zipfile, json
from datetime import date

APPLY_THRESHOLD = 0.75   # >= -> apply with source=doc
STRONG_THRESHOLD = 0.90  # >= -> high-confidence (still logged)

STOP = set("""a an the of to for and or in on at by with from into as is are be was were
this that these those it its your you our their his her they we i will shall should would
can could may might must not no yes if then else when while per via using use used based
system should able allow allows display displayed show shown view views user users new add
added when a an of on to the option feature support enhancement improvement""".split())

DATE_RE = re.compile(r'^(?P<ver>\d+\.\d+(?:\.\d+)?)\s*\((?P<date>[^)]*)\)\s*$')
ISO_RE  = re.compile(r'^\d{4}-\d{2}-\d{2}$')

def _clean(s):
    for a, b in (('&amp;','&'),('&lt;','<'),('&gt;','>'),('&quot;','"'),
                 ('&#39;',"'"),('→','->'),('–','-'),('’',"'")):
        s = s.replace(a, b)
    return s.strip()

def _blocks(docx_path):
    z = zipfile.ZipFile(docx_path)
    xml = z.read('word/document.xml').decode('utf-8', 'replace')
    body = re.search(r'<w:body>(.*)</w:body>', xml, re.S).group(1)
    out = []
    for m in re.finditer(r'<w:p\b[^>]*>.*?</w:p>|<w:tbl\b.*?</w:tbl>', body, re.S):
        c = m.group(0)
        if c.startswith('<w:tbl'):
            for tr in re.findall(r'<w:tr\b.*?</w:tr>', c, re.S):
                cells = [_clean(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', tc, re.S)))
                         for tc in re.findall(r'<w:tc\b.*?</w:tc>', tr, re.S)]
                if any(cells): out.append(' | '.join(cells))
        else:
            t = _clean(''.join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', c, re.S)))
            if t and not t.startswith('<w:'):
                out.append(t)
    return out

def _kw(text):
    toks = re.findall(r'[a-z0-9]+', (text or '').lower())
    return {t for t in toks if len(t) > 2 and t not in STOP}

class ReleaseDoc:
    def __init__(self, version_dates, version_features):
        self.version_dates = version_dates          # {ver: "YYYY-MM-DD" or None(placeholder)}
        self.version_features = version_features      # {ver: [feature_line, ...]}

    def version_date(self, version):
        d = self.version_dates.get(version)
        return d if (d and ISO_RE.match(d)) else None

    def is_released_by_doc(self, version, today=None):
        d = self.version_date(version)
        if not d: return (False, None, "no firm date in doc")
        today = today or date.today().isoformat()
        return (d <= today, d, "doc-confirmed" if d <= today else "future date in doc")

    def match_story(self, summary, description="", today=None):
        skw = _kw(summary) | _kw(description)
        if not skw:
            return {"verdict": "warning", "reason": "no story keywords", "score": 0.0}
        best = None
        for ver, feats in self.version_features.items():
            for feat in feats:
                fkw = _kw(feat)
                if not fkw: continue
                inter = len(skw & fkw)
                score = inter / len(skw)                    # containment of story kw in feature
                if best is None or score > best["score"]:
                    best = {"version": ver, "feature": feat, "score": round(score, 3)}
        if not best:
            return {"verdict": "warning", "reason": "no candidate features", "score": 0.0}
        d = self.version_date(best["version"])
        rel, dd, why = self.is_released_by_doc(best["version"], today)
        best["release_date"] = d
        if best["score"] >= APPLY_THRESHOLD and rel:
            best["verdict"] = "apply"
            best["confidence"] = "strong" if best["score"] >= STRONG_THRESHOLD else "match"
        else:
            best["verdict"] = "warning"
            best["reason"] = ("score below %.2f" % APPLY_THRESHOLD) if best["score"] < APPLY_THRESHOLD else why
        return best

def parse(docx_path):
    lines = _blocks(docx_path)
    version_dates, version_features = {}, {}
    cur = None
    for ln in lines:
        m = DATE_RE.match(ln)
        if m:
            cur = m.group('ver')
            dt = m.group('date').strip()
            version_dates[cur] = dt if ISO_RE.match(dt) else None
            version_features.setdefault(cur, [])
            continue
        if cur:
            # skip section scaffolding lines
            if ln.lower() in ("new features / changes", "improvements", "bug fixes",
                              "what's new in " + cur.lower()) or ln.lower().startswith("what's new in"):
                continue
            if len(ln) > 8 and not ln.startswith('|'):
                version_features[cur].append(ln)
    return ReleaseDoc(version_dates, version_features)

if __name__ == "__main__":
    doc = parse(sys.argv[1])
    print("versions parsed:", len(doc.version_dates))
    print("firm-dated:", sum(1 for v in doc.version_dates.values() if v and ISO_RE.match(v)))
    for v in ("8.1.1","8.1.2","8.2"):
        print(f"  {v}: date={doc.version_dates.get(v)!r} released={doc.is_released_by_doc(v)}")
