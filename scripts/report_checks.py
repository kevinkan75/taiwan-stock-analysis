"""Conservative lexical checks for current reports; not general semantic proof."""
import re
import unicodedata

PROFILE_RULE = '1.14.0'
PROFILE_RULES = {'1.11.0', '1.12.0', '1.13.0', PROFILE_RULE}


def report_errors(report, action=None, confidence=None):
    text = unicodedata.normalize('NFKC', report).replace('**', '')
    errors = []
    # Check asserted reliability/confidence, not EPS growth, prices, coverage or a
    # quoted analyst forecast. A prohibition is allowed, an asserted exception is not.
    number = r'(?:\d+(?:\.\d+)?\s*(?:%|/\s*100|分)|百分之\s*\d+)'
    confidence_claim = re.compile(r'(?:信心(?:指數|程度)?|可信度|可靠度|可採信程度|確定性|勝率|上漲機率)\s*(?:約|為|是|達|[:：=])?\s*'+number)
    prohibited = re.compile(r'不得|不可|不能|禁止|不應|未經校準.*不|無法提供|不提供|不宣稱|不代表')
    negative = re.compile(r'不(?:建議|應|宜|可)|尚不|尚無|不足以|勿|避免|禁止|不能|不可|不要|未建議|不代表|不得')
    conditional = re.compile(r'若|如果|假如|倘|待.+(?:後|再)|條件(?:符合|成立|滿足|解除)|條件式')
    buy = re.compile(r'(?:(?:本次|目前|現在|操作說明|我|我們).{0,12})?(?:建議|應該|可以|可|請|立即|直接|現在|適合).{0,12}(?:買進|買入|進場|加碼)|必買')
    uncertain_high = re.compile(r'(?:本次|目前|整體|研究)?(?:研究)?(?:信心|確定性)\s*(?:為|是|[:：])?\s*(?:高|極高|高度確定)')
    for line_no, raw in enumerate(text.splitlines(), 1):
        # Block quotes/fenced examples are deliberately not exempt: they must
        # explicitly identify a quote/example to avoid becoming a bypass.
        quote = bool(re.search(r'^(?:>\s*)?(?:引用|引述|範例|錯誤示例)[:：]', raw.strip()))
        for clause in re.split(r'[。；;！？!?]|(?<!\d)\.(?!\d)', raw):
            if not clause.strip() or quote:
                continue
            for match in confidence_claim.finditer(clause):
                prefix = clause[max(0, match.start()-24):match.start()]
                # "不是85分" is a denial; "85分不代表勝率" still asserts a score.
                if not prohibited.search(prefix) and not re.match(r'\s*(?:並非|不是)', prefix[-3:]):
                    errors.append('report: unsupported confidence/probability number at line %d' % line_no)
            if confidence in (None, 'low', 'medium') and uncertain_high.search(clause):
                if not negative.search(clause) and not quote:
                    errors.append('report: confidence assertion contradicts research at line %d' % line_no)
            if action in ('wait', 'abandon', 'staged'):
                for match in buy.finditer(clause):
                    prefix = clause[:match.start()]
                    nearby = clause[max(0, match.start()-16):match.start()]
                    action_segment=re.split(r'[，,]|但是|然而|不過|但|卻',nearby+match.group())[-1]
                    if negative.search(action_segment) or conditional.search(prefix+match.group()):
                        continue
                    # A future conditional clause must precede its action. Merely
                    # saying "仍有條件" after "現在買入" does not exempt it.
                    errors.append('report: unconditional entry contradicts '+action+' at line %d' % line_no)
    return list(dict.fromkeys(errors))
