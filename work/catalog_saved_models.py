"""Read-only model catalog with source pointers; no imports of training code."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
import csv
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output/model_catalog' / STAMP
OUT.mkdir(parents=True, exist_ok=False)
DOC = ROOT / '训练拟合模型与版本清单.md'
for name in ('训练拟合模型与版本清单.md', '训练拟合模型与版本清单_文字说明版.md'):
    (OUT / ('previous_' + name)).write_bytes((ROOT / name).read_bytes())
(OUT / 'work_log.md').write_text(f'# 模型版本清单\n\n开始：{STAMP}（北京时间）。用户要求列出全部已保存训练拟合模型及版本，通用公式置于下方。'
    '\n\n只读取参数与诊断文件，不训练、不覆盖模型、冻结预测或原件；同文件副本和诊断子版本分别登记。状态：进行中。\n', encoding='utf-8')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

patterns = ['output/cross_market/parameters_*.json', 'output/model_v2/*/demand*.json',
    'output/model_v2/*/context_fit_*.json', 'output/model_v2/*/mechanisms.json',
    'output/country_demand/*/model.json', 'output/operations_rho/*/model.json',
    'output/parameter_priority/*/demand_results.json', 'output/parameter_priority/*/results.json',
    'output/formal_update/*_training/models.json', 'output/formal_update/*_report/training/models.json',
    'output/unified-market/*/models.json', 'output/visible_coefficients/*/coefficients.json',
    'output/price_diagnostics/results.json', 'output/visible_coefficients/*joint/verification.json',
    'output/model_v2/materials_review/*/review.json', 'output/model_v2/*/materials_review.json',
    'output/interest_rate/*/model.json', 'output/interest_rate/*/validation.json',
    'output/material_unit_cost/*/model.json', 'output/material_unit_cost/*/validation.json',
    'output/t2v0-um/*/components.json', 'output/t2v0-um/*/component_validation.json',
    'output/formal_update/*_report/supporting/output/country_demand/*/model.json',
    'output/formal_update/*_report/supporting/output/operations_rho/*/model.json']
paths = sorted({p for pattern in patterns for p in ROOT.glob(pattern)} |
               {ROOT / '需求拟合与留出核验.json', ROOT / '分步模型拟合与验证.json'})
source_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in paths}
data = {p.relative_to(ROOT).as_posix(): json.loads(p.read_text(encoding='utf-8-sig')) for p in paths}

FAMILIES = {
    'ABS': ('绝对对数需求模型', 'D=exp(a_c−e_c ln(P/P0_c)+b_G ln(1+G/s)+b_H ln(1+H/s)+b_R z_R)'),
    'SHARE': ('双国竞争份额模型', 'u_i=−e_c ln(P_i/P0_i)+b_G ln(1+G_i/s)+b_H ln(1+H_i/s)+b_R ln f_R(R_i+ρ_R Rprev_i)；s_i=softmax_J(u_i)；D_i=T_c s_i'),
    'COUNTRY': ('国别独立竞争份额模型', '同份额公式，价格、一般营销、设计师营销、研发四项系数按国家独立；J仅含本市场本回合同国竞争队'),
    'RD': ('研发—需求乘数曲线', 'f_R(x)=a+b(x+c)^d'),
    'OPS': ('运营—效率乘数曲线', 'f_O(x)=a+b x/(c+x)'),
    'EFF': ('生产效率与运营延续模型', 'η=θ f_O(O+ρ_O Oprev)；θ的普通均值、策略等权均值和加权最小二乘版本分别保存'),
    'RISK_POWER': ('杠杆幂函数风险溢价模型', 'r_L=r_base+a[(L+L_short)/E]^b'),
    'RISK_EXP': ('权益比指数风险溢价模型', 'r_L=r_base+a exp(−b E/A)'),
    'MATERIAL': ('原材料单位差额校准', 'Δv由已保存样本校准；B=q(v+Δv)，属于经验残差参数'),
    'MATERIAL_PROP': ('原材料单位费用比例模型', 'unit_cost=published_price×(1+parameter)；B=q×unit_cost'),
}

VECTOR_KEYS = {'beta', 'coefficients', 'parameters', 'train_parameters', 'frozen_round1_beta',
    'all_practice_beta', 'frozen_beta', 'standardized_ridge_beta', 'indonesia_only_beta',
    'optimized_other_beta', 'selected_beta', 'low_penalty_beta', 'unpenalized_beta',
    'rd_curve_parameters', 'curve_parameters'}
SCALAR_KEYS = {'theta', 'technology_scale', 'strategy_balanced_scale', 'uplift_usd_per_unit', 'empirical_uplift_usd_per_unit', 'parameter'}
CONFIG_KEYS = {'rho', 'rd_persistence', 'penalty', 'selected_penalty', 'full_penalty', 'scale',
    'standardized', 'piecewise', 'loss', 'form', 'country', 'context_id', 'phase', 'round',
    'market_id', 'train_n', 'positive_fit_n', 'model_id', 'version', 'training_phase', 'training_round', 'training_n', 'target_phase', 'target_round'}
DIAG = re.compile(r'holdout|nested|/cv|fold|influence|resampl|bootstrap|sensitivity|penalty_path|/path|ablation|/profile|internal_team|support_ablations|nuisance_swaps|per_market|/rounds|leave_one|leave_team|expanded_training_cv|finance_diagnostics', re.I)

def is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)

def is_vector(v):
    return isinstance(v, list) and bool(v) and all(is_number(n) for n in v)

def family(source, pointer):
    pointer = pointer.replace('~1', '/')
    s = source + '/' + pointer
    if 'material_unit_cost' in s or 'material_market_holdout' in s or 'practice_selected' in s or 'all_data_refit' in s:
        return 'MATERIAL_PROP'
    if 'interest_rate/' in source or 'interest_nested' in s:
        return 'RISK_POWER'
    if 'uplift' in s or '/materials' in s:
        return 'MATERIAL'
    if 'solvency_exponential' in s:
        return 'RISK_EXP'
    if 'leverage_power' in s:
        return 'RISK_POWER'
    if '/risk_candidates/' in s or '/risk/' in s:
        return 'RISK_POWER'  # overridden by the node's explicit form below
    if '/curves/rd' in s or 'rd_curve_parameters' in s:
        return 'RD'
    if '/curves/operations' in s or ('curve_parameters' in s and ('operations' in s or 'efficiency' in s)):
        return 'OPS'
    if 'operations_rho' in source or 'efficiency' in s or 'operations_efficiency' in s or 'operations/rho' in s:
        return 'EFF'
    if 'country_demand' in source or 'parameter_priority' in s or '/country/' in s or ('unified-market' in source and '/demand/' in s):
        return 'COUNTRY'
    if source == '需求拟合与留出核验.json' or 'own_only' in s or 'fit_demand/absolute' in s:
        return 'ABS'
    return 'SHARE'

def run_name(source):
    if source == '需求拟合与留出核验.json':
        return 'ABS_PRACTICE_20261011T034722Z'
    if source == '分步模型拟合与验证.json':
        return 'STEPWISE_20261011T045441Z'
    parts = Path(source).parts
    if 'cross_market' in parts:
        return Path(source).stem.replace('parameters_', 'CROSS_')
    if 'price_diagnostics' in parts:
        return 'PRICE_DIAGNOSTICS_20261011T103555Z'
    return parts[-2]

def version_name(source, pointer):
    tag = data[source].get('model_id', data[source].get('version', '')) if isinstance(data[source], dict) else ''
    tag = tag + '/' if tag else ''
    readable = pointer.replace('~1', '/').replace('~0', '~') or '/'
    return tag + run_name(source) + '/' + Path(source).stem + '::' + readable

def pointer_token(k):
    return str(k).replace('~', '~0').replace('/', '~1')

records = []
def walk(node, source, pointer='', inherited=None):
    inherited = dict(inherited or {})
    if isinstance(node, dict):
        if isinstance(node.get('config'), dict):
            inherited.update({k:v for k,v in node['config'].items() if k in CONFIG_KEYS})
        inherited.update({k: v for k, v in node.items() if k in CONFIG_KEYS and
            (isinstance(v, (str, bool, int, float)) or k == 'scale' and is_vector(v))})
        params = {k: v for k, v in node.items() if k in VECTOR_KEYS and is_vector(v) or
                  k in SCALAR_KEYS and is_number(v)}
        if node.get('form') == 'published':
            params.pop('parameter', None)  # Published zero adjustment is a baseline, not a fitted coefficient.
        if params:
            fam = family(source, pointer)
            if inherited.get('form') == 'solvency_exponential': fam = 'RISK_EXP'
            if inherited.get('form') == 'leverage_power': fam = 'RISK_POWER'
            if inherited.get('form') == 'additive': fam = 'MATERIAL'
            # A parent efficiency node may also retain the curve coefficients it uses.
            if set(params) <= {'curve_parameters'}: fam = 'OPS'
            if set(params) <= {'rd_curve_parameters'}: fam = 'RD'
            diagnostic = bool(DIAG.search(pointer)) or Path(source).name in ('validation.json', 'component_validation.json')
            if '/baseline' in pointer and fam == 'EFF': diagnostic = False
            records.append(dict(model_code=fam, model_name=FAMILIES[fam][0],
                version_name=version_name(source, pointer),
                role='诊断子版本' if diagnostic else '保存参数版本',
                source=source, json_pointer=pointer, parameters=params, config=inherited,
                parameter_sha256=hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()))
        for k, v in node.items():
            child = pointer + '/' + pointer_token(k)
            if k in VECTOR_KEYS and isinstance(v, list) and v and all(is_vector(a) for a in v):
                for i, vector in enumerate(v):
                    records.append(dict(model_code=family(source, child), model_name=FAMILIES[family(source, child)][0],
                        version_name=version_name(source, child + '/' + str(i)), role='诊断子版本',
                        source=source, json_pointer=child + '/' + str(i), parameters={k: vector}, config=inherited,
                        parameter_sha256=hashlib.sha256(json.dumps({k: vector}, sort_keys=True).encode()).hexdigest()))
            elif isinstance(v, (dict, list)):
                walk(v, source, child, inherited)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, (dict, list)): walk(v, source, pointer + '/' + str(i), inherited)

for source, d in data.items():
    walk(d, source)

# Saved candidate selection scores often lack coefficient vectors; list separately.
score_records = []
def scores(node, source, pointer=''):
    if isinstance(node, dict):
        if ('penalty' in node or isinstance(node.get('config'), dict)) and any(k in node for k in ('cv_share_mae_pp', 'mae_pp', 'cv_share_mae', 'cv_mae')):
            score_records.append({'source': source, 'json_pointer': pointer,
                'version_name': version_name(source, pointer),
                'config': node.get('config', {k: v for k,v in node.items() if k in CONFIG_KEYS}),
                'scores': {k:v for k,v in node.items() if k in ('cv_share_mae_pp', 'mae_pp', 'cv_share_mae', 'cv_mae')}})
        for k,v in node.items():
            if isinstance(v, (dict,list)): scores(v, source, pointer+'/'+pointer_token(k))
    elif isinstance(node,list):
        for i,v in enumerate(node):
            if isinstance(v,(dict,list)): scores(v,source,pointer+'/'+str(i))
for source,d in data.items(): scores(d,source)

# Exact files copied into report bundles and latest are aliases, not new training runs.
canonical = {}
aliases = {}
ordered = sorted(source_hashes, key=lambda s: ('_report/' in s, 'latest' in s, 'context_fit_' in s or 'checkpoint' in s, s))
for source in ordered:
    aliases[source] = canonical.setdefault(source_hashes[source], source)

def resolve(source, pointer):
    value = data[source]
    for token in pointer.split('/')[1:]:
        token = token.replace('~1', '/').replace('~0', '~')
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value

for r in records:
    r['copy_of'] = aliases[r['source']] if aliases[r['source']] != r['source'] else ''
    value = resolve(r['source'],r['json_pointer'])
    for k,v in r['parameters'].items():
        assert (value[k] if isinstance(value,dict) else value) == v
assert len({(r['source'],r['json_pointer']) for r in records}) == len(records)
assert set(r['model_code'] for r in records) == set(FAMILIES)
assert all(r['model_code']=='COUNTRY' for r in records if '/country~1' in r['json_pointer'])
assert all(r['model_code']=='ABS' for r in records if 'fit_demand~1absolute' in r['json_pointer'])
assert all(r['role']=='诊断子版本' for r in records if '/leave_team_out/' in r['json_pointer'])
assert any(r['model_code']=='MATERIAL_PROP' and 'material_unit_cost/' in r['source'] for r in records)
assert {r['model_code'] for r in records if 't2v0-um/' in r['source'] and r['json_pointer'] in ('/interest_rate', '/material_unit_cost')} == {'RISK_EXP', 'MATERIAL_PROP'}

def link(source, label=None):
    return f'[{label or source}]({(ROOT/source).as_posix()})'

def clean(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')

def summary(r):
    items=[]
    for k,v in r['parameters'].items():
        if isinstance(v,list): items.append(k+'=['+', '.join(format(n,'.9g') for n in v)+']')
        else: items.append(k+'='+format(v,'.9g'))
    cfg = ', '.join(k+'='+str(v) for k,v in r['config'].items() if k in ('rho','penalty','loss','piecewise'))
    return '; '.join(items) + ('；'+cfg if cfg else '')

current_run='20261012T114145124558+0800'
lines=['# 训练拟合模型、全部保存版本与通用计算公式', '',
    '独立模型文档入口：'+link('模型说明/README.md','模型公式与变量说明')+'；'+link('模型版本重新统计.md','本次统计汇总')+'。', '',
    f'核对：{STAMP}（北京时间）。按已保存参数文件登记模型名称、版本名称、来源及JSON定位；原有模型ID保留，本文短码仅用于查阅。', '',
    '版本名称采用“运行/归档名称 :: JSON路径”。时间较新只表示较晚保存，不自动表示已部署或更可靠；最新组件训练为 t2v0-um 练习2利率与材料费用，最新整套假设训练仍为 unified-market 正式1版本。', '',
    '完整参数版本在正文逐项列出；留出、重采样、删队、正则路径等子拟合在附录逐项列出。报告内相同文件与latest登记为副本；不同运行即使参数相同也保留版本名。只保存评分而未保存系数的候选另列，不补造训练参数。', '',
    f'扫描{len(paths)}份参数档案，记录{len(records)}个参数位置，其中{sum(r["role"]=="诊断子版本" for r in records)}个诊断子版本；另有{len(score_records)}项保存的选参评分。计数包含明确登记的副本，不等于独立模型数量。', '',
    '## 模型名称与拟合公式', '', '| 名称代码 | 模型名称 | 拟合关系 |', '| --- | --- | --- |']
for fam,(name,formula) in FAMILIES.items():
    lines.append(f'| {fam} | {name} | `{formula}` |')
lines += ['', '共同变量：P价格（美元/单位），G/H一般与设计师营销、R研发、O运营投入（千美元），T行业需求、D公司需求（千单位），η效率（千单位/人）；A资产、E权益、L债务为千美元。投入尺度s及延续ρ以各版本记录为准。分段价格版本增加高于1.5倍初始价的惩罚项；研发特征有log1p投入与log曲线两种，绝对需求版本须按源码核对，不混用。', '',
    '## 当前最新独立训练与正式报告版本', '',
    '- t2v0-um 练习2组件：利率与材料费用已训练；正式2整体迁移仍关闭，需求/效率未重训。新增利率独立模型、材料比例模型和练习2截图近似参数已计入本次统计。截图身份及刻度存在不确定性，不能当平台精确参数。',
    f'- 最新独立假设版本：{link("output/unified-market/"+current_run+"/models.json", "unified-market / "+current_run)}。两国需求各一套，效率、两风险函数和材料差额重训；正式1/正式2曲线分回合登记。正式2需求系数未训练。',
    '- 正式2既有HTML采用 `20261011T230135216100+0800_training`；其报告副本不自动切换到 unified-market。旧 A/B、情境与国别模型仍保留。',
    '- 绝对需求和竞争份额均为研究候选；国别营销是公司合计代理，行业总量仍外生。风险验证给定期末状态，曲线验证只检验图形拟合。完整财务与六回合优化仍未完成。', '',
    '## 每个模型的全部保存参数版本', '',
    '表中列出非诊断参数位置；ρ不同、国别不同、情境不同、前向冻结与全样本重拟合分别命名。副本出处集中登记在后面的档案表，不重复同一整文件的模型行。']

main = [r for r in records if r['role']=='保存参数版本' and not r['copy_of']]
for fam,(name,_) in FAMILIES.items():
    lines += ['', f'### {fam} · {name}', '', '| 版本名称 | 参数与配置 | 来源 |', '| --- | --- | --- |']
    for r in main:
        if r['model_code'] != fam: continue
        lines.append('| '+clean(r['version_name'])+' | '+clean(summary(r))+' | '+link(r['source'],'参数原档')+' |')

lines += ['', '## 全部参数档案与副本对应', '',
    '| 档案/版本来源 | 参数位置数 | 副本对应 |', '| --- | ---: | --- |']
counts=Counter(r['source'] for r in records)
for source in data:
    lines.append('| '+link(source)+' | '+str(counts[source])+' | '+(link(aliases[source],'字节相同的原档') if aliases[source]!=source else '独立档案（不表示参数独立）')+' |')

lines += ['', '## 诊断子版本与候选评分', '',
    link(str((OUT/'全部参数位置.md').relative_to(ROOT)), '全部参数位置逐行清单')+'：含每一个JSON定位、模型名和版本名，覆盖正文与全部诊断子拟合。', '',
    link(str((OUT/'model_versions.json').relative_to(ROOT)), '完整精度参数与配置')+'；'+link(str((OUT/'candidate_scores.json').relative_to(ROOT)), '候选选参评分及配置')+'。源码运行中未保存的临时拟合没有可恢复系数，不记作已存版本。', '',
    '销售“相对重要性”条形图是已显示的图形读数，不能当作需求回归系数；行业增长外推、等份额基线、财务恒等式和候选搜索均列入下方通用计算。', '',
    '## 通用计算公式（无独立训练版本）', '',
    '以下按计算顺序排列。利率、税率、工资、运输和折旧率均读取对应回合参数；经验项另作标注。数量千单位乘美元/单位直接得到千美元。', '',
    '| 计算项目 | 公式 | 适用范围或参数来源 |', '| --- | --- | --- |',
    '| 行业总量与增长 | `T_t=Σ_i D_i,t`；`g_T=T_t/T_(t−1)−1`；情景 `T̂_t=T_(t−1)(1+g_T)`；历史外推 `T̂_t=T_(t−1)^2/T_(t−2)` | 实际需求汇总或显式情景；不是已拟合行业函数，分母为0时比例无定义 |',
    '| 等份额基线 | `s_i=1/组数`；`D_i=T_c s_i` | 对照基线；行业规模须另外给定 |',
    '| 下一回合公司需求增长 | `g_D=Σ_c D̂_(t+1),c/Σ_c D̂_t,c−1` | 下一回合情景传播，不能独立当增长回归 |',
    '| 有效投入代理 | `R_eff=R+ρ_R Rprev`；`O_eff=O+ρ_O Oprev` | ρ及特征函数取各模型版本；不是完整历史存量递推 |',
    '| 机器产能与投资 | `C_t=(1−δ_C)C_(t−1)+I_t`；`K_machine=p_I I_t` | 当前已核场景投资当回合生效；δ_C、p_I逐回合核验 |',
    '| 需求驱动生产 | `q=min(C_t a/100,Σ_c D̂_c)`；候选 `a=100 min(Σ_c D̂_c/C_t,1)` | 零期初库存、零大客户；候选需正边际贡献及合法产能 |',
    '| 交付与库存守恒 | 按优先级 `S_c=min(D_c,Q_remaining)`；`库存末=库存初+生产−普通销售−订单交付` | 零库存旧模型仅分配q；非零库存和订单优先级须按规则接入 |',
    '| 人数与三班产量 | `N=q/η`；`q1=min(q,C/3)`；`q2=min(max(q−C/3,0),C/3)`；`q3=max(q−2C/3,0)` | 连续人数近似，η由对应效率版本给定 |',
    '| 工资与解聘 | `W=(q1+κ2 q2+κ3 q3)w/η`；`F=max((1−δ_N)Nprev−N,0)wσ` | 班次倍数、工资、自然离职及补偿率取当期前景 |',
    '| 营业收入与运输 | `V=Σ_c P_c S_c`；`Z=Σ_c k_c S_c` | 用交付销量；汇率及币种按已核规则，不能把需求直接当销量 |',
    '| 材料与费用 | `B=q(v+Δv)`；`M=G+H+市场调研费`；`Overhead=管理费+F+R+O` | Δv来自上方校准版本；固定项逐回合读取 |',
    '| 经营利润 | `EBITDA=V−B−W−Z−M−Overhead`；`EBIT=EBITDA−Dep_machine−Dep_building` | 当前完整链未覆盖库存、订单等全部分支 |',
    '| 折旧与账面资产 | `Dep_machine=d_m(Book_machine,0+K_machine)`；`Dep_building=d_b Book_building,0`；`Book_end=Book_0+Capex−Dep` | 机器与厂房时序分开；厂房800和7%属于归档经验关系 |',
    '| 周转资金 | `AR=V d_AR/365`；`AP=B d_AP/365` | 30天为现有经验兼容关系，未证实跨期固定 |',
    '| 长贷与利息 | `L=L0+ΔL`；`J_L=(L0+L)r_L/2` | r_L来自当期预测或风险模型；风险拟合与本计算式分开 |',
    '| 税前现金 | `Cash_pre=Cash0+EBITDA−J_L+(AR0−AR)+(AP−AP0)−K_machine−K_building+ΔL` | 当前零库存/零订单/零短贷范围 |',
    '| 现金利息、所得税与利润 | `J_C=max((Cash0+Cash)/2,0)r_C`；`PBT=EBIT+J_C−J_L`；`Tax=max(PBT−Loss0,0)τ`；`Profit=PBT−Tax`；`Cash=Cash_pre+J_C−Tax` | Cash、J_C、Tax迭代联立；亏后转盈税亏仍需独立验证 |',
    '| 权益、税亏及最低现金 | `E=E0+Profit`；`Loss_end=max(Loss0−max(PBT,0),0)+max(−PBT,0)`；`Short_needed=max(Cash_min−Cash,0)` | 短贷缺口仅标记，不能当已包含短贷利息的最终利润 |',
    '| 资产负债平衡 | `A=Book_machine+Book_building+AR+Cash`；`A=L+AP+E` | 当前无库存、无短贷范围；扩展分支须加入相应余额 |',
    '| 累计收益与六回合期限 | `累计收益_t=累计收益_(t−1)+Profit_t`；候选剩余收益 `Σ_(k=t..6) Profit_k` | 剩余7−t回合；未知未来只给情景，期末终值须有规则 |',
    '| 误差评价 | `MAE=mean(abs(y−ŷ))`；`RMSE=sqrt(mean((y−ŷ)^2))`；`WAPE=Σabs(y−ŷ)/Σy` | WAPE分母为0时无定义；加权与份额百分点指标按版本口径 |',
    '', '来源：'+link('预测模型与变量说明.md','公式、符号及适用条件')+'、'+link('code/model_v2/finance.py','财务实现')+'、'+link('参数细化与六回合期限要求.md','逐回合参数与期限')+'。本次仅整理，未将经验公式升级为官方规则。', '']

DOC.write_text('\n'.join(lines),encoding='utf-8')
appendix=['# 全部保存参数位置：模型名称与版本名称', '',
    '每行是一个保存位置，副本保留并注明；参数采用完整精度JSON，表中仅给来源定位。正文先列完整参数版本，下方另列诊断；这里包含全部。', '',
    '| 模型名称 | 版本名称 | 类别 | 来源 | 副本原档 |', '| --- | --- | --- | --- | --- |']
for r in records:
    appendix.append('| '+r['model_code']+' '+r['model_name']+' | '+clean(r['version_name'])+' | '+r['role']+' | '+link(r['source'],'参数文件')+' | '+(link(r['copy_of'],'原档') if r['copy_of'] else '—')+' |')
(OUT/'全部参数位置.md').write_text('\n'.join(appendix)+'\n',encoding='utf-8')
(OUT/'model_versions.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'candidate_scores.json').write_text(json.dumps(score_records,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'model_versions.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['model_code','model_name','version_name','role','source','json_pointer','copy_of'])
    w.writeheader();w.writerows({k:r[k] for k in w.fieldnames} for r in records)

assert all(digest(ROOT/s)==h for s,h in source_hashes.items())
assert len(json.loads((OUT/'model_versions.json').read_text(encoding='utf-8'))) == len(records)
for file in (DOC,OUT/'全部参数位置.md'):
    text=file.read_text(encoding='utf-8')
    assert text.count('`')%2 == 0
    for target in re.findall(r'\]\(([^\n]+?)\)',text): assert Path(target).exists(),target
assert DOC.read_text(encoding='utf-8').index('## 通用计算公式') > DOC.read_text(encoding='utf-8').index('## 每个模型')
verification=dict(source_files=len(paths),parameter_locations=len(records),main_canonical_parameters=len(main),
    diagnostic_locations=sum(r['role']=='诊断子版本' for r in records),candidate_scores=len(score_records),
    source_hashes_unchanged=True,pointers_and_parameter_values_verified=True,links_valid=True,
    families={fam:sum(r['model_code']==fam for r in records) for fam in FAMILIES},source_hashes=source_hashes,
    scope='保存系数和校准参数；未保存系数的拟合不补造；候选评分单列。')
verification['canonical_parameter_locations'] = sum(not r['copy_of'] for r in records)
verification['copy_parameter_locations'] = sum(bool(r['copy_of']) for r in records)
verification['family_counts'] = {fam: dict(main=sum(r['model_code']==fam for r in main),
    diagnostic=sum(r['model_code']==fam and r['role']=='诊断子版本' and not r['copy_of'] for r in records),
    copies=sum(r['model_code']==fam and bool(r['copy_of']) for r in records)) for fam in FAMILIES}
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
    f.write(f'\n完成：{len(paths)}份参数档案，{len(records)}个参数位置，{len(main)}项非副本完整参数位置。'
            'JSON定位与数值逐项核验通过，原参数哈希未改，链接检查通过。通用计算公式已置于下方；未训练、未运行网页或更新Word。\n')
print(json.dumps({'directory':str(OUT),'families':verification['families'],'main':len(main),'records':len(records),'sources':len(paths)},ensure_ascii=False))
