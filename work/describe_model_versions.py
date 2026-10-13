"""Describe saved versions and attributable errors without fitting any model."""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = max((ROOT / 'output/model_catalog').glob('*/verification.json')).parent
STAMP = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S%f+0800')
OUT = ROOT / 'output/model_descriptions' / STAMP
OUT.mkdir(parents=True, exist_ok=False)
DOC = ROOT / '训练拟合模型与版本清单_文字说明版.md'
records = json.loads((BASE/'model_versions.json').read_text(encoding='utf-8'))
old_verify = json.loads((BASE/'verification.json').read_text(encoding='utf-8'))
data = {}
hashes = {}
def read(source):
    if source not in data:
        path=ROOT/source
        hashes[source]=hashlib.sha256(path.read_bytes()).hexdigest()
        data[source]=json.loads(path.read_text(encoding='utf-8-sig'))
    return data[source]
for source,expected in old_verify['source_hashes'].items():
    read(source)
    assert hashes[source]==expected, ('source changed since catalog',source)
(OUT/'work_log.md').write_text(f'# 模型版本文字说明\n\n开始：{STAMP}（北京时间）。'
    '依据原版本清单额外编写文字说明，逐版本说明训练范围、改动、国家、误差和测试集。'
    '不训练，不覆盖原清单或模型。误差只取可定位的已保存记录，缺失明确标注。状态：进行中。\n',encoding='utf-8')

def tokens(pointer):
    return [p.replace('~1','/').replace('~0','~') for p in pointer.split('/')[1:]]

def chain(source,pointer):
    node=read(source); result=[('',node)]
    parts=[]
    for token in pointer.split('/')[1:]:
        parts.append(token)
        key=token.replace('~1','/').replace('~0','~')
        node=node[int(key)] if isinstance(node,list) else node[key]
        result.append(('/'+'/'.join(parts),node))
    return result

def fmt(v): return format(v,'.6g')
def encode(s): return str(s).replace('~','~0').replace('/','~1')
def cell(s): return str(s).replace('|','\\|').replace('\n',' ')
def link(source,label='原档'): return f'[{label}]({(ROOT/source).as_posix()})'

training_runs=sorted({Path(r['source']).parent.name for r in records if '_training/' in r['source']})
cross_runs=sorted({Path(r['source']).stem for r in records if 'cross_market/parameters_' in r['source'] and 'latest' not in r['source']})
v2_runs=sorted({Path(r['source']).parent.name for r in records if 'model_v2/' in r['source'] and re.match(r'\d+T\d+\+0800$',Path(r['source']).parent.name)})

def country(r,key):
    p=r['json_pointer'].replace('~1','/')
    if key=='indonesia_only_beta':return '印尼'
    for c in ('泰国','印尼'):
        if c in p:return c
    c=r['config'].get('country')
    if c in ('泰国','印尼'):return c
    return '泰国、印尼（联合）' if r['model_code'] in ('ABS','SHARE') else '公司整体（泰国生产）' if r['model_code'] in ('EFF','OPS') else '两国共用' if r['model_code']=='RD' else '公司整体'

def nearest_keys(nodes):
    for _,node in reversed(nodes):
        if not isinstance(node,dict):continue
        for k in ('training_keys','train_keys','train_markets'):
            if isinstance(node.get(k),list) and node[k]:return k,node[k]
    return None,None

def market_text(markets):
    markets=sorted(set(markets))
    if markets==list(range(1,11)):return '全部10个市场'
    if markets==[5]:return '仅市场5'
    if len(markets)==9 and set(markets)<set(range(1,11)):
        return '全部市场，去除市场'+str(next(iter(set(range(1,11))-set(markets))))
    return '市场'+ '、'.join(str(x) for x in markets)

def phase_text(keys):
    periods=sorted({(k[1],k[2]) for k in keys if isinstance(k,list) and len(k)>=3})
    names=[]
    for phase,rnd in periods:
        names.append(('正式' if phase=='formal' else '练习' if phase=='practice' else '初始')+str(rnd))
    return '、'.join(names)

def scope(r,key,nodes,c):
    s=r['copy_of'] or r['source'];p=r['json_pointer'].replace('~1','/');root=read(s)
    if any(part in s for part in ('interest_rate/', 'material_unit_cost/', 't2v0-um/')):
        if 't2v0-um/' in s:
            period='练习2'
        elif 'interest_rate/' in s:
            period='正式1'
        else:
            period='练习1、练习2、正式1' if key=='parameter' and Path(s).name=='model.json' else '原档指定的练习/正式回合'
        desc='全部10个市场，'+period+'实际数据；同回合跨市场共享为假设'
        if r['role']=='诊断子版本':desc+='；选型或留出参数，具体训练/留出键见原档'
        return desc
    k,ks=nearest_keys(nodes)
    if k in ('training_keys','train_keys'):
        markets=[v[0] for v in ks if isinstance(v,list) and v and isinstance(v[0],int)]
        desc=market_text(markets)+'，'+phase_text(ks)+'实际数据' if markets else '训练范围按原档训练键'
    elif k=='train_markets':
        desc=market_text(ks)+'，练习1、练习2实际数据'
    elif 'formal_update/' in s:
        if '/cross_market/B/' in p:desc='全部10个市场，正式1实际数据'
        elif '/country/market' in p:desc='仅市场'+re.search(r'/country/market(\d+)',p)[1]+'，正式1实际数据'
        elif any(x in p for x in ('finance/','operations/','efficiency')):desc='仅市场5，正式1实际数据'
        else:desc='仅市场5，正式1实际需求'
    elif 'unified-market/' in s:
        desc='全部10个市场，正式1实际数据；按unified-market同期共享假设合并'
    elif 'cross_market/' in s:
        desc='仅市场5' if '/A/' in p else '市场范围未在该参数位置单独保存'
        desc+='，练习1、练习2实际数据'
    elif 'country_demand/' in s or 'parameter_priority/' in s or 'model_v2/' in s:
        desc='仅市场5，'+('练习2' if 'M5_P2_' in p else '练习1')+'实际数据'
        if 'demand' in s and '/pools/B/' in p:desc='全部10个市场，练习1训练或两练习回合重拟合，按版本区分'
    elif 'operations_rho/' in s:desc='仅市场5，练习1实际效率；按不同运营策略等权'
    elif 'price_diagnostics/' in s:desc=('仅市场5' if '/A' in p else '全部10个市场')+'，练习1、练习2实际需求'
    else:desc='仅市场5，练习1、练习2实际数据'
    if r['model_code'] in ('RD','OPS'):
        if 'practice2_screenshot' in s:
            n=len(nodes[-1][1].get('points',[]))
            return f'用户提供练习2截图，{n}个提取点；'+('交错点训练' if key=='train_parameters' else '全部提取点拟合')+'；市场身份未核验，坐标敏感性不等于置信区间'
        round2='round2' in s or '/formal/2/' in p
        if 'curve_parameters'==key or 'rd_curve_parameters'==key:
            return '沿用正式1市场5可见图表曲线参数；该位置没有新训练集'
        return ('正式2' if round2 else '正式1')+'市场5可见图表，每条200个点；'+('交错100点训练' if key=='train_parameters' else '全部200点拟合')
    if s=='分步模型拟合与验证.json' and r['model_code'] in ('SHARE','EFF','RISK_POWER','RISK_EXP','MATERIAL'):
        desc='仅市场5，练习1实际数据' if key!='all_practice_beta' else '仅市场5，练习1、练习2实际需求'
    if s=='需求拟合与留出核验.json' and '/round_holdout/' in p:
        node=nodes[-1][1]; desc='仅市场5，'+('练习2' if '练习2训练' in node.get('fold','') else '练习1')+'实际需求'
    if 'nested_forward_holdout' in p or key=='frozen_round1_beta':desc='仅市场5，练习1实际需求；冻结前向候选'
    if 'round2_separate_fit' in p:desc='仅市场5，练习2实际效率；本回合另行重拟合'
    if 'rounds/' in p and 'price_diagnostics' in s:
        n=nodes[-1][1];desc=('仅市场5' if '/A/' in p else '全部10个市场')+'，练习'+str(n.get('round','未记录'))+'实际需求'
    if 'leave_one_cluster_out' in p:
        removed=nodes[-1][1].get('removed')
        if isinstance(removed,int) and '/B/' in p:desc='全部市场，去除市场'+str(removed)+'；练习1、练习2实际需求'
        else:desc+='；去除原档指定的一组（影响诊断）'
    if '/influence/' in p:desc+='；去除'+removed_text(nodes[-1][1],p)+'（影响诊断）'
    if 'resampling' in p or 'bootstrap' in p:desc+='；按原档的市场/团队簇重采样'
    if 'support_ablations' in p:desc+='；排除原档指定的高价样本（敏感性分析）'
    if 'support_ablations' in p:
        label=nodes[-1][1].get('label','')
        if '四条' in label:desc='全部10个市场，练习1、练习2；去除四条印尼极端高价记录'
        elif '1888' in label:desc='全部10个市场，练习1、练习2；印尼仅保留价格1888–2900，泰国全留'
    if '/per_market/' in p and isinstance(nodes[-1][1],dict):
        desc='仅市场'+str(nodes[-1][1].get('market','原档指定'))+'，练习1、练习2实际需求'
    if 'COUNTRY'==r['model_code'] or key=='indonesia_only_beta':desc+='；仅'+c+'的需求标签'
    if any(t in p for t in ('holdout','leave_team_out','outer_folds','market_holdouts','strategy_cv')):
        desc+='；该折留出的市场/组/策略不参与训练'
    # Record only configuration changes, not fitted vectors.
    cfg=r['config']
    tweaks=[]
    if isinstance(cfg.get('penalty'),(int,float)):tweaks.append('惩罚系数λ='+fmt(cfg['penalty']))
    if cfg.get('standardized') is True:tweaks.append('惩罚前标准化')
    if cfg.get('piecewise') is True:tweaks.append('加入高价分段')
    if isinstance(cfg.get('rho'),(int,float)):tweaks.append('延续ρ='+fmt(cfg['rho']))
    if cfg.get('loss') in ('log','share'):tweaks.append('对数损失' if cfg['loss']=='log' else '份额损失')
    if isinstance(cfg.get('scale'),(int,float)):tweaks.append('营销响应尺度s='+fmt(cfg['scale']))
    return desc+('；'+'，'.join(tweaks) if tweaks else '')

def removed_text(node,pointer):
    if not isinstance(node,dict):return '原档指定组'
    tag=node.get('removed_team',node.get('removed',''))
    m=re.match(r'(\d+):(\d+):',str(tag))
    if m:return '市场'+m[1]+'第'+m[2]+'组'
    # Do not reproduce names from the raw record.
    match=re.search(r'/(\d+)$',pointer)
    return '第'+str(int(match[1])+1)+'组（按原档顺序）' if match else '原档指定组'

def title(r,key,c,nodes):
    s=r['copy_of'] or r['source'];p=r['json_pointer'].replace('~1','/');parent=Path(s).parent.name
    is_b=any(x in p for x in ('/models/B','/pools/B','/cross_market/B'))
    hypothesis='B假设' if is_b else 'A假设' if any(x in p for x in ('/models/A','/pools/A','/cross_market/A')) else ''
    methods=[
        ('/model_v2/verified_context','沿用20261011T210536情境隔离配置'),
        ('/parameter_priority/','沿用PARAMETER_PRIORITY_V1对应国家和分支配置'),
        ('/country/','沿用COUNTRY_DEMAND_V1国别建模方法，重新选参'),
        ('/fit_demand/absolute','沿用首版绝对需求模型配置（λ=1、研发ρ=0.5）'),
        ('/stepwise/share','沿用首版分步份额模型配置（λ=0.01）'),
        ('/operations/rho','沿用OPERATIONS_RHO_V1延续估计方法，重新估计ρ和技术尺度'),
        ('/stepwise/efficiency_and_v2_sensitivity','沿用首版/重审版固定ρ效率对照方法'),
        ('/finance/risk/leverage_power','沿用杠杆幂风险函数，重新拟合系数'),
        ('/finance/risk/solvency_exponential','沿用权益比指数风险函数，重新拟合系数'),
        ('/finance/material_uplift','沿用材料单位差额校准方法，重新校准差额')]
    inherited_method=next((name for marker,name in methods if marker in p),'按本行模型方法重新拟合')
    if 't2v0-um/' in s:base='t2v0-um，练习2组件训练，正式2整体迁移关闭'
    elif 'interest_rate/' in s:base='实际贷款利率独立模型，正式1训练'
    elif 'material_unit_cost/' in s:base='原材料单位费用比例模型，跨已观察回合校准'
    elif 'practice2_screenshot' in s:base='练习2截图曲线近似，非平台精确参数'
    elif 'unified-market/' in s:base='unified-market假设，正式1合并训练'
    elif '_training/' in s:base=(hypothesis or inherited_method)+'，正式1第'+str(training_runs.index(parent)+1)+'次重训'
    elif '_report/' in s:base=(hypothesis or inherited_method)+'，正式1重训结果的报告保存副本'
    elif 'cross_market/' in s:
        stem=Path(s).stem
        base=hypothesis+'，两练习回合训练，'+('latest快捷副本' if 'latest' in s else '第'+str(cross_runs.index(stem)+1)+'次参数保存')
    elif 'country_demand/' in s:base='国别独立假设，'+('练习2情境' if 'M5_P2_' in p else '练习1/正式1可见情境')+'训练'
    elif 'parameter_priority/' in s:
        base='参数细化假设，'+('练习2' if 'M5_P2_' in p else '练习1')+'训练，'+('第2次保存' if '215006' in s else '第1次保存')
    elif 'model_v2/' in s:
        base=(hypothesis+'，' if hypothesis else '')+('情境隔离假设，' if 'M5_P' in p or 'context_fit' in s else '重审版本，')
        base+=('第'+str(v2_runs.index(parent)+1)+'次重审保存' if parent in v2_runs else '材料差额区间重审')
        if 'M5_P2_' in p or 'M5_P2_' in s:base+='，练习2情境'
        elif 'M5_P1_' in p or 'M5_P1_' in s:base+='，练习1/正式1可见情境'
        if 'forward_model' in p:base+='，练习1前向冻结'
        if 'refit_model' in p:base+='，对应范围重拟合'
        if 'checkpoint' in s:base+='，训练过程检查点'
    elif 'operations_rho/' in s:base='运营延续ρ细化假设，练习1训练，'+('第2次保存' if '213209' in s else '第1次保存')
    elif 'visible_coefficients/' in s:base=('正式2' if 'round2' in s else '正式1')+'图表曲线，'+('JSON与SVG配对核验保存' if 'joint' in s else 'JSON点拟合' if 'json' in s else 'SVG点重拟合')
    elif 'price_diagnostics/' in s:base=(hypothesis or '价格系数')+'，价格覆盖/惩罚诊断'
    elif s=='需求拟合与留出核验.json':base='首版绝对需求假设，练习数据训练'
    else:base='首版分步模型，练习数据训练'
    variant={'frozen_round1_beta':'练习1冻结候选','all_practice_beta':'两练习回合合并重拟合',
        'train_parameters':'交错训练点版本','frozen_beta':'原冻结参数对照','standardized_ridge_beta':'标准化惩罚版本',
        'indonesia_only_beta':'仅印尼重拟合','low_penalty_beta':'降低惩罚版本','unpenalized_beta':'无惩罚版本',
        'strategy_balanced_scale':'策略等权技术尺度','technology_scale':'普通均值技术尺度'}.get(key)
    modes={'baseline':'固定基准','rd_rho':'研发延续ρ细化','marketing_scale':'营销响应尺度调整','own_only':'自身策略对照','competitive':'竞争份额版本'}
    for term,label in modes.items():
        if re.search(r'[/]'+term+r'([/]|$)',p):base+='，'+label
    if variant:base+='，'+variant
    if '/country/market' in p:
        base+='，市场'+re.search(r'/country/market(\d+)',p)[1]+'独立训练'
    if '/model_v2/verified_context' in p:base+='，市场5已核情境版本'
    if 'round2_separate_fit' in p:base+='，练习2独立重拟合'
    diag={'outer_folds':'嵌套整市场留出','market_holdouts':'整市场留出','nested_team_holdout':'嵌套留队',
        'team_holdout':'团队留出','round_holdout':'跨回合留出','strategy_cv':'运营策略留出',
        'leave_team_out':'留出一组','leave_one_cluster_out':'删除市场/团队簇','influence':'删组影响分析',
        'resampling':'簇重采样','cluster_resampling':'簇重采样','penalty_path':'惩罚路径','profile':'价格系数剖面',
        'sensitivity':'延续/惩罚敏感性','internal_team_holdout':'内部留队','support_ablations':'高价样本排除',
        'nuisance_swaps':'其他特征替换'}
    for term,label in diag.items():
        if term in p:
            m=re.search(re.escape(term)+r'/(\d+)',p)
            base+='，'+label+('第'+str(int(m[1])+1)+'次' if m else '')
            break
    if key=='indonesia_only_beta' or r['model_code']=='COUNTRY':base+='（'+c+'）'
    return base

# Add formal1 before-fit evaluation only for the exact frozen source or an equal fitted object.
eval_source='output/formal_update/20261011T230135216100+0800_training/frozen_evaluation.json'
evaluations=read(eval_source)
external=[]
def bind(source,pointer,parameter_key,eval_key,test):
    node=chain(source,pointer)[-1][1]
    val=node[parameter_key]
    config={k:node[k] for k in ('rho','penalty','standardized','piecewise','loss') if k in node}
    external.append((val,config,eval_key,test,source,pointer,parameter_key))
frozen_source='output/cross_market/parameters_20261011T081705179804Z.json'
for pool in ('A','B'):
    for mode in ('competitive','own_only'):
        bind(frozen_source,'/models/'+pool+'/'+mode,'coefficients','cross_market/'+pool+'/'+mode,
            ('仅市场5' if pool=='A' else '全部10个市场')+'，正式1实际需求；给定已实现对手策略'+('及实际行业总量的份额条件回溯' if mode=='competitive' else '的数量条件回溯'))
bind('需求拟合与留出核验.json','','coefficients','fit_demand/absolute','仅市场5，正式1实际需求；训练截止于练习期')
bind('分步模型拟合与验证.json','/demand','frozen_round1_beta','stepwise/share','仅市场5，正式1实际需求；给定已实现对手与行业总量的份额条件回溯')
bind('output/model_v2/20261011T210536542951+0800/demand.json','/pools/A~1M5_P1_FORMAL1_VISIBLE/refit_model','beta',
    'model_v2/verified_context','仅市场5，正式1实际需求；给定已实现对手与行业总量的份额条件回溯')
country_source='output/country_demand/20261011T205528470485+0800/model.json'
priority_source='output/parameter_priority/20261011T215006575364+0800/results.json'
for c in ('泰国','印尼'):
    bind(country_source,'/models/'+encode('M5_P1_FORMAL1_VISIBLE/'+c),'beta','country/'+c,
        '仅市场5，正式1'+c+'实际需求；已实现对手与实际行业总量条件回溯')
    for mode in ('baseline','rd_rho','marketing_scale'):
        bind(priority_source,'/models/'+encode('M5_P1_FORMAL1_VISIBLE/'+c)+'/models/'+mode+'/fitted','beta',
            'parameter_priority/'+c+'/'+mode,'仅市场5，正式1'+c+'实际需求；给定已实现对手的份额条件回溯')

def metrics(r,key,nodes,c):
    evidence=[]
    node=nodes[-1][1] if isinstance(nodes[-1][1],dict) else {}
    parent=next((n for _,n in reversed(nodes[:-1]) if isinstance(n,dict)),{})
    s=r['source'];p=r['json_pointer'].replace('~1','/');root=read(s)
    def add(obj,k,label,test,source=None,pointer=None,factor=1):
        if isinstance(obj,dict) and isinstance(obj.get(k),(int,float)):
            evidence.append({'source':source or s,'json_pointer':(pointer if pointer is not None else nodes[-1][0])+'/'+encode(k),
                'value':obj[k],'factor':factor,'label':label,'test':test})
    def score(obj,test,source=None,pointer=None):
        for k,label,factor in [('share_mae_pp','份额MAE（百分点）',1),('MAE','需求MAE（千单位）',1),
                ('WAPE','需求WAPE（%）',100),('strategy_weighted_rmse','策略等权效率RMSE（千单位/人）',1),
                ('strategy_weighted_mae','策略等权效率MAE（千单位/人）',1),('mae_kusd','材料总额MAE（千美元）',1),
                ('conditional_end_state_mae_basis_points','风险利率MAE（基点）',1)]:
            add(obj,k,label,test,source,pointer,factor)
    def aggregate(obj,list_key,metric_path,label,test,pointer):
        rows=obj.get(list_key) if isinstance(obj,dict) else None
        if not isinstance(rows,list) or not rows:return
        values=[]
        for entry in rows:
            value=entry
            for token in metric_path.split('/'):
                value=value.get(token) if isinstance(value,dict) else None
            if not isinstance(value,(int,float)):return
            values.append(value)
        evidence.append({'source':s,'json_pointer':pointer+'/'+encode(list_key),'value':sum(values)/len(values),
            'factor':1,'label':label,'test':test,'aggregation':'mean','metric_path':metric_path,'components':values})
    test_base=scope(r,key,nodes,c).split('；')[0]
    if 'nested_market_holdout_mae_basis_points' in node:
        add(node,'nested_market_holdout_mae_basis_points','风险利率MAE（基点）',test_base+'；嵌套整市场留出，给定实际期末状态；选型流程成绩')
        return evidence
    if 't2v0-um/' in s and r['model_code']=='MATERIAL_PROP':
        add(node,'market_holdout_mae_kusd','材料总额MAE（千美元）',test_base+'；整市场留出，给定实际产量')
        return evidence
    if 'material_unit_cost/' in s and Path(s).name=='model.json':
        validation_source=str(Path(s).with_name('validation.json')).replace('\\','/')
        validation=read(validation_source)
        add(validation['all_data_fit'],'mae_kusd','材料总额MAE（千美元）','练习1、练习2、正式1全部300条，样本内；给定实际产量',validation_source,'/all_data_fit')
        return evidence
    if c in ('泰国','印尼'):test_base+='，'+c
    # Cross-period errors apply only to matching saved frozen parameters/configuration.
    if '_training/' not in s and '_report/' not in s and r['role']=='保存参数版本':
        for val,cfg,ev,test,src,ptr,pk in external:
            expected_family='COUNTRY' if ev.startswith(('country/','parameter_priority/')) else 'ABS' if ev=='fit_demand/absolute' or ev.endswith('/own_only') else 'SHARE'
            if r['model_code']==expected_family and r['parameters'][key]==val and all(r['config'].get(k)==v for k,v in cfg.items()):
                score(evaluations[ev],test,eval_source,'/'+encode(ev))
                break
    if evidence:return evidence
    if 'unified-market/' in s and r['model_code']=='EFF' and '/chosen' in p:
        aggregate(parent,'market_holdouts','metrics/strategy_weighted_rmse','平均逐市场效率RMSE（千单位/人）',
            '全部10个市场正式1；逐一留出1市场，策略等权效率误差',nodes[-2][0])
        return evidence
    if 'unified-market/' in s and r['model_code']=='MATERIAL':
        aggregate(node,'market_holdouts','mae_kusd','逐市场留出材料MAE（千美元）',
            '全部10个市场正式1；逐一留出1市场，其他9市场校准',nodes[-1][0])
        return evidence
    if r['model_code'] in ('RD','OPS') and key in ('parameters','train_parameters'):
        if 'practice2_screenshot' in s:
            test='练习2同一截图'+('交错留点' if key=='train_parameters' else '全部提取点样本内')+'；只检验图形近似'
            add(node,'held_mae' if key=='train_parameters' else 'full_mae','曲线MAE（乘数）',test)
            return evidence
        if key=='train_parameters':
            test='同回合'+('正式2' if 'round2' in s or '/formal/2/' in p else '正式1')+'图表其余交错100点；只检验曲线近似'
            add(node,'held_mae','曲线MAE（乘数）',test)
            add(node,'held_max_error','曲线最大误差（乘数）',test)
        else:
            test='同回合图表全部200点（样本内），只检验曲线近似'
            add(node,'full_mae','曲线MAE（乘数）',test)
            add(node,'full_max_error','曲线最大误差（乘数）',test)
            add(node,'full_vertex_max_error','曲线最大误差（乘数）',test)
        return evidence
    if 'outer_folds' in p:
        held=parent.get('held_markets',[]);test='正式1'+c+'，留出市场'+'、'.join(map(str,held))+'；给定已实现竞争决策'
        add(parent,'share_mae_pp','份额MAE（百分点）',test,pointer=nodes[-2][0])
        return evidence
    if 'nested_market_holdout_share_mae_pp' in node:
        add(node,'nested_market_holdout_share_mae_pp','份额MAE（百分点）','全部10个市场正式1'+c+'；嵌套整市场留出，每次留出2市场')
        return evidence
    if 'market_holdouts' in p or 'held_market' in parent or 'held_market' in node:
        holder=node if 'held_market' in node else parent
        location=nodes[-1][0] if holder is node else nodes[-2][0]
        test='正式1，留出市场'+str(holder.get('held_market','原档指定'))+'；训练为其余9市场'+('；'+c if c in ('泰国','印尼') else '')
        add(holder,'mae_basis_points','风险利率MAE（基点）',test,pointer=location)
        add(holder,'mae_kusd','材料总额MAE（千美元）',test,pointer=location)
        if isinstance(holder.get('metrics'),dict):score(holder['metrics'],test,pointer=location+'/metrics')
        return evidence
    if 'holdout_mae_basis_points' in node:
        add(node,'holdout_mae_basis_points','风险利率MAE（基点）','正式1，全部10市场逐一留出；给定实际期末状态')
        return evidence
    if 'leave_team_out' in p:
        test='练习1，留出'+removed_text(node,p)+'；给定实际期末状态'
        add(node,'heldout_error_bp','该组风险利率绝对误差（基点）',test)
        return evidence
    if r['model_code']=='EFF' and 'operations_rho/' in s:
        if '/chosen' in p or '/baseline' in p:
            fixed='/baseline' in p
            add(root,'cv_fixed_05_rmse' if fixed else 'cv_optimized_rmse','策略等权效率RMSE（千单位/人）',
                '市场5练习1；4种运营策略逐一留出，其他策略训练',pointer='')
            return evidence
        if '/strategy_cv/' in p:
            obj=parent.get('fixed_05' if '/baseline' in p else 'optimized',{})
            score(obj,'市场5练习1；留出原档指定运营策略',pointer=nodes[-2][0]+('/fixed_05' if '/baseline' in p else '/optimized'))
            return evidence
        if 'round2_separate_fit' in p:
            add(node,'weighted_rmse','效率RMSE（千单位/人）','仅市场5练习2（样本内）')
            return evidence
    if r['model_code']=='EFF' and '/operations/rho/chosen' in p:
        aggregate(parent,'strategy_cv','optimized/strategy_weighted_rmse','平均留策略效率RMSE（千单位/人）',
            '仅市场5正式1；每次留出一种运营策略，其余策略训练',nodes[-2][0])
        return evidence
    if r['model_code']=='EFF' and '/strategy_cv/' in p and 'formal_update/' in s:
        score(parent.get('optimized',{}),'仅市场5正式1；留出原档指定运营策略，其余策略训练',pointer=nodes[-2][0]+'/optimized')
        return evidence
    if r['model_code']=='ABS' and isinstance(node.get('model'),dict) and 'formal_update/' in s:
        score(node['model'],'仅市场5正式1；该折留出的1组，两国需求均留出',pointer=nodes[-1][0]+'/model')
        return evidence
    if 'internal_fixed_configuration_holdout_share_mae_pp' in parent:
        add(parent,'internal_fixed_configuration_holdout_share_mae_pp','份额MAE（百分点）',
            '仅市场5正式1'+c+'；固定原配置，内部逐组留出',pointer=nodes[-2][0])
        return evidence
    if 'internal_fixed_penalty_holdout_share_mae_pp' in node:
        add(node,'internal_fixed_penalty_holdout_share_mae_pp','份额MAE（百分点）','仅市场5正式1；固定惩罚，内部逐组留出')
        return evidence
    if 'internal_team_holdout_share_mae_pp' in node:
        add(node,'internal_team_holdout_share_mae_pp','份额MAE（百分点）',test_base+'；内部逐组留出')
        return evidence
    if 'internal_team_holdout' in node:
        held=node['internal_team_holdout']
        if isinstance(held,dict):score(held,'正式1；内部留队（给定实际期末状态或已实现竞争策略）',pointer=nodes[-1][0]+'/internal_team_holdout')
        if isinstance(held,list):
            if r['model_code'] in ('RISK_POWER','RISK_EXP'):
                aggregate(node,'internal_team_holdout','error_basis_points','平均留队风险绝对误差（基点）',
                    test_base+'；逐组留出，给定实际期末状态',nodes[-1][0])
            elif r['model_code']=='ABS':
                aggregate(node,'internal_team_holdout','model/MAE','平均留队需求MAE（千单位）',
                    test_base+'；逐组留出',nodes[-1][0])
        if evidence:return evidence
    if 'selected_cv_share_mae_pp' in node:
        add(node,'selected_cv_share_mae_pp','份额MAE（百分点）',test_base+'；内部留队选参，非独立测试')
        return evidence
    if 'cv_share_mae_pp' in parent and 'refit_model' in p:
        add(parent,'cv_share_mae_pp','份额MAE（百分点）','市场5'+('练习2' if 'M5_P2_' in p else '练习1')+'；内部逐组留出选参',pointer=nodes[-2][0])
        return evidence
    if '/forward_model' in p and isinstance(parent.get('forward_share_mae_pp'),(int,float)):
        add(parent,'forward_share_mae_pp','份额MAE（百分点）','练习1训练，练习2同范围数据；已实现对手条件回溯',pointer=nodes[-2][0])
        return evidence
    if s=='需求拟合与留出核验.json':
        if isinstance(node.get('model'),dict):
            test=node.get('fold','内部留队')
            if not ('练习' in str(test)):test='两练习回合，留出第'+str(int(tokens(r['json_pointer'])[-1])+1)+'组（按原档顺序）'
            score(node['model'],test,pointer=nodes[-1][0]+'/model')
        elif r['json_pointer']=='':score(root['training'],'市场5练习1、练习2（样本内）',pointer='/training')
        return evidence
    if s=='分步模型拟合与验证.json' and key=='frozen_round1_beta':
        score(root['demand']['forward']['model'],'市场5练习2；练习1训练，已实现对手策略条件回溯',pointer='/demand/forward/model')
        return evidence
    if key=='technology_scale':
        add(node,'forward_mae','效率MAE（千单位/人）','市场5练习2；练习1训练，跨情境回溯')
        add(node,'training_mae','效率MAE（千单位/人）','市场5练习1（样本内）')
        return evidence
    if key=='strategy_balanced_scale':return evidence  # ordinary estimator's error cannot be reused
    if r['model_code'] in ('RISK_POWER','RISK_EXP'):
        add(node,'forward_mae_basis_points','风险利率MAE（基点）','市场5练习2；练习1训练，给定实际期末状态')
        add(node,'training_mae_basis_points','风险利率MAE（基点）','市场5练习1（样本内），给定实际期末状态')
        return evidence
    if r['model_code']=='MATERIAL':
        add(node,'forward_mae_kusd','材料总额MAE（千美元）','市场5练习2；练习1校准单位差额')
        return evidence
    if isinstance(node.get('training_score'),dict):
        score(node['training_score'],test_base+'（样本内，未留出测试）',pointer=nodes[-1][0]+'/training_score')
    if 'training_share_mae_pp' in node:
        add(node,'training_share_mae_pp','份额MAE（百分点）','对应训练集（样本内）')
    if isinstance(node.get('training_metrics'),dict):
        score(node['training_metrics'],'对应训练集（样本内）',pointer=nodes[-1][0]+'/training_metrics')
    if 'selected' in p and '/efficiency/' in p:
        add(node,'forward_mae','效率MAE（千单位/人）','市场5练习2；练习1训练，跨情境回溯')
    return evidence

descriptions=[]
for r in records:
    # Curve coefficients inherited inside a country-model package remain curves.
    r=dict(r)
    decoded=r['json_pointer'].replace('~1','/')
    if '/curve_scope/rd' in decoded:
        r.update(model_code='RD',model_name='研发—需求乘数曲线')
    elif '/curve_scope/operations' in decoded:
        r.update(model_code='OPS',model_name='运营—效率乘数曲线')
    if '/parameter_change' in decoded:r['role']='参数差异参考（非模型版本）'
    if '/strategy_cv/' in decoded:r['role']='诊断子版本'
    nodes=chain(r['source'],r['json_pointer'])
    for key,value in r['parameters'].items():
        if key=='coefficients' and 'beta' in r['parameters'] and value==r['parameters']['beta']:continue
        c=country(r,key)
        errors=metrics(r,key,nodes,c)
        if '/parameter_change' in decoded:errors=[]
        errors=errors[:2]
        role=r['role']
        if key=='train_parameters':role='诊断子版本'
        if key in ('rd_curve_parameters','curve_parameters'):role='沿用参数位置'
        family=r['model_code'];name=r['model_name']
        if key=='indonesia_only_beta':family='COUNTRY';name='国别独立竞争份额模型'
        desc=dict(model_code=family,model_name=name,country=c,
            version_title=title(r,key,c,nodes),training=scope(r,key,nodes,c),role=role,
            error='；'.join(x['label']+'='+fmt(x['value']*x['factor']) for x in errors) if errors else '未单独保存此版本的测试误差',
            test='；'.join(dict.fromkeys(x['test'] for x in errors)) if errors else '无可归属的单独测试记录；不借用其他版本成绩',
            source=r['source'],json_pointer=r['json_pointer'],parameter_key=key,
            original_version=r['version_name'],copy_of=r['copy_of'],error_evidence=errors)
        descriptions.append(desc)

# Validate every metric against its precise source field, including unit conversion.
for i,row in enumerate(descriptions,1):
    row['id']='V'+str(i).zfill(5)
    if row['model_code']=='COUNTRY':assert row['country'] in ('泰国','印尼'),row
    assert not any(x in row['training'] for x in ('beta=[','parameters=[','coefficients=['))
    for e in row['error_evidence']:
        value=chain(e['source'],e['json_pointer'])[-1][1]
        if e.get('aggregation')=='mean':
            actual=[]
            for item in value:
                for token in e['metric_path'].split('/'):item=item[token]
                actual.append(item)
            assert actual==e['components'] and sum(actual)/len(actual)==e['value'],e
        else:assert value==e['value'],e
assert len({(r['source'],r['json_pointer']) for r in records})==len(records)
assert {(x['source'],x['json_pointer']) for x in descriptions} == {(x['source'],x['json_pointer']) for x in records}
for nation,expected in [('泰国',0.3005398796227516),('印尼',0.18341679792394405)]:
    sample=next(x for x in descriptions if 'unified-market/' in x['source'] and x['json_pointer']=='/demand/'+nation)
    assert sample['country']==nation and nation in sample['test']
    if nation=='泰国':assert sample['error_evidence'][0]['value']==expected
    else:assert abs(sample['error_evidence'][0]['value']-0.183417)<1e-6

def table(rows,with_pointer=False):
    heads=['编号','模型名称','国家','版本文字说明','训练集来源与主要调整','模型误差','测试集与检验方式','来源']
    output=['| '+' | '.join(heads)+' |','| '+' | '.join(['---']*len(heads))+' |']
    for r in rows:
        tail=link(r['source'])
        if with_pointer:tail+='；`'+r['json_pointer']+'/'+encode(r['parameter_key'])+'`'
        if r['copy_of']:tail+='（保存副本）'
        output.append('| '+' | '.join(cell(x) for x in [r['id'],r['model_name'],r['country'],r['version_title'],r['training'],r['error'],r['test'],tail])+' |')
    return output

main=[r for r in descriptions if r['role']=='保存参数版本' and not r['copy_of']]
families={r['model_code']:r['model_name'] for r in descriptions}
intro=['# 训练拟合模型与版本清单 · 文字说明版','',
    '独立模型文档入口：'+link('模型说明/README.md','模型公式与变量说明')+'。最新统计见'+link('模型版本重新统计.md','本次统计汇总')+'；文字编号按本次清单重新生成，请以源文件与JSON定位追溯历史编号。','',
    '核对日期：2026-10-12（北京时间）。本页与原清单对应，版本改用文字描述；拟合系数向量省略，训练范围与主要配置调整保留。分国家模型逐行注明国家。','',
    '“第几次重训”只用于三次正式1重训；其他时间戳写作第几次保存或重审，文件副本不当作新训练。每行编号关联完整参数位置，参数重合也保留其保存版本。','',
    '误差列区分独立/外层留出、内部选参、跨回合条件回溯和样本内回算；测试集列说明市场、回合、国家与切分方式。缺少可归属误差时明确标注，未把另一版本或另一国家的成绩填入。曲线误差是乘数误差，不能与需求误差比较。','',
    '冻结模型在正式1的后续回溯成绩只关联相同系数与配置的版本。表中“平均逐市场/逐策略”是已有各折误差的算术平均，来源与汇总方法保存在验收明细；不表示新增训练或新的事前检验。','',
    '国家含义：泰国/印尼为国别需求模型；双国联合模型标明两国，生产效率为公司整体的泰国生产模型，风险及材料为公司整体。训练中的“市场”指编号市场，不指国家。','',
    f'对应原清单{len(records)}个参数位置；将同位置的不同参数版本拆开后共{len(descriptions)}行。正文列{len(main)}行非副本主版本；全部诊断、沿用参数及保存副本见文末完整文字附录。','',
    '## 最新版本示例','']
latest=[r for r in main if ('unified-market/' in r['source'] and r['model_code'] in ('COUNTRY','EFF','RISK_POWER','RISK_EXP','MATERIAL')) or any(x in r['source'] for x in ('interest_rate/', 'material_unit_cost/', 't2v0-um/'))]
intro+=table(latest)
intro+=['','## 全部主版本的文字说明','']
for fam in ('ABS','SHARE','COUNTRY','RD','OPS','EFF','RISK_POWER','RISK_EXP','MATERIAL','MATERIAL_PROP'):
    intro+=['','### '+families[fam],'']+table([r for r in main if r['model_code']==fam])
intro+=['','## 完整文字附录与原参数对应','',
    link((OUT/'全部版本文字说明.md').relative_to(ROOT).as_posix(),'每一个主版本、诊断子版本、沿用位置及副本的文字说明')+'：共'+str(len(descriptions))+'行，列结构与正文相同，额外给出JSON定位。','',
    link((OUT/'descriptions.json').relative_to(ROOT).as_posix(),'逐版本说明及误差来源定位')+'；'+link('训练拟合模型与版本清单.md','原技术版本清单')+'。','']
original=(ROOT/'训练拟合模型与版本清单.md').read_text(encoding='utf-8')
formula=original[original.index('## 通用计算公式'):]
DOC.write_text('\n'.join(intro)+'\n'+formula,encoding='utf-8')
appendix=['# 全部版本文字说明（包括诊断与副本）','',
    '逐行与原技术清单对应；每个参数位置中的不同估计版本拆开列出。副本误差取同一保存记录，不表示新增检验；未知误差保持未知。','']+table(descriptions,True)
(OUT/'全部版本文字说明.md').write_text('\n'.join(appendix)+'\n',encoding='utf-8')
(OUT/'descriptions.json').write_text(json.dumps(descriptions,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(hashlib.sha256((ROOT/s).read_bytes()).hexdigest()==h for s,h in hashes.items())
for path in (DOC,OUT/'全部版本文字说明.md'):
    text=path.read_text(encoding='utf-8')
    for target in re.findall(r'\]\(([^\n]+?)\)',text):assert Path(target).exists(),target
assert DOC.read_text(encoding='utf-8').endswith(formula)
verification=dict(original_parameter_locations=len(records),described_parameter_locations=len({(x['source'],x['json_pointer']) for x in descriptions}),
    description_rows=len(descriptions),main_rows=len(main),country_rows=sum(x['model_code']=='COUNTRY' for x in descriptions),
    country_labels_verified=True,metrics_checked_against_source_fields=True,
    rows_with_attributable_error=sum(bool(x['error_evidence']) for x in descriptions),sources_unchanged=True,
    general_formulas_identical=True,source_hashes=hashes)
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
counts = {fam: Counter('副本' if row['copy_of'] else row['role'] for row in descriptions if row['model_code']==fam) for fam in families}
report=['# 模型版本重新统计', '', f'核对时间：{STAMP}（北京时间）。', '',
    f'扫描{old_verify["source_files"]}份参数/诊断档案，共{len(families)}类已保存拟合模型。登记{len(records)}个JSON参数位置，展开为{len(descriptions)}条参数说明；同位置的不同估计向量分列。', '',
    f'非副本主版本说明：**{len(main)}条**。该数按保存的估计参数与配置登记，不表示同等数量的独立训练运行；相同参数的不同运行仍保留，字节相同文件按副本单列。', '',
    '| 模型类别 | 非副本主版本 | 非副本诊断子版本 | 沿用参数位置 | 参数差异参考 | 副本 |',
    '| --- | ---: | ---: | ---: | ---: | ---: |']
for fam, name in families.items():
    count=counts[fam]
    report.append('| '+name+' | '+' | '.join(str(count[role]) for role in ('保存参数版本','诊断子版本','沿用参数位置','参数差异参考（非模型版本）','副本'))+' |')
totals=Counter('副本' if row['copy_of'] else row['role'] for row in descriptions)
assert sum(totals.values()) == len(descriptions)
report += ['| 合计 | '+' | '.join(str(totals[role]) for role in ('保存参数版本','诊断子版本','沿用参数位置','参数差异参考（非模型版本）','副本'))+' |', '',
    '上表按文字说明行计数；技术清单按JSON位置计数，可能在同一位置同时保存全点与交错训练参数。技术清单的诊断位置计数含副本，因此不能与上表非副本诊断行直接相减。', '',
    f'选参评分单列{old_verify["candidate_scores"]}项；评分条数不计作系数版本。未保存系数的临时拟合、合成测试、平台给定值、财务恒等式和搜索情景均不计作实际拟合版本。', '',
    '本次补入独立利率模型、材料比例模型、t2v0-um练习2组件及留出参数；练习2截图拟合已纳入，但标记为图形近似。报告包内国别需求与运营延续参数副本也已补登记。旧统计为61档案、6195位置；本次范围扩大，新增记录不全代表新训练。', '',
    '最新组件训练：t2v0-um练习2利率与材料费用；最新整套假设训练：unified-market正式1。t2v0-um需求/效率未重训，正式2整体迁移关闭。当前正式3规则仍有未接入分支，已有历史版本不等同于当前完整预测。', '',
    '原参数哈希、JSON定位与参数值、误差源字段及文档链接检查通过。本次只重新统计，不训练或变更网页决策。', '',
    '详细入口：'+link('训练拟合模型与版本清单.md','技术清单')+'；'+link('训练拟合模型与版本清单_文字说明版.md','文字清单')+'；'+link((BASE/'verification.json').relative_to(ROOT).as_posix(),'参数统计核验')+'；'+link((OUT/'verification.json').relative_to(ROOT).as_posix(),'文字说明核验')+'。', '']
(ROOT/'模型版本重新统计.md').write_text('\n'.join(report),encoding='utf-8')
with (OUT/'work_log.md').open('a',encoding='utf-8') as f:
    f.write(f'\n完成：{len(main)}行主版本，附录{len(descriptions)}行全部文字版本；原{len(records)}个参数位置全覆盖。'
        '分国家标签、误差源字段、链接及公式一致性核验通过。没有可归属测试误差的记录明确标注。原清单与所有模型未改，未训练或修改网页。\n')
print(json.dumps({'directory':str(OUT),'main_rows':len(main),'all_rows':len(descriptions),
    'country_rows':verification['country_rows'],'rows_with_error':verification['rows_with_attributable_error']},ensure_ascii=False))
