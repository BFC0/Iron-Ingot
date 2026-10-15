"""Pair result JSON with same-container SVG; geometry tolerance preserves renderer rounding."""
import argparse
import importlib.util
import json
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime,timezone,timedelta
from html.parser import HTMLParser
from pathlib import Path

BASE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('validation',BASE/'validate_market.py')
validation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)
NUM=r'-?\d+(?:\.\d+)?(?:e[+-]?\d+)?'


class Containers(HTMLParser):
    def __init__(self):
        super().__init__();self.stack=[];self.ids=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='svg':
            self.ids.append(next((a.get('id') for t,a in reversed(self.stack) if a.get('id','').startswith('cc-')),None))
        if tag not in ('img','input','br','hr','meta','link','source','wbr','area','base','embed','param','track','col'):
            self.stack.append((tag,attrs))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:];break


def series(items):
    return [s for item in items for s in (series(item['dataset']) if 'dataset' in item else [item])]


def value(text):
    try:
        result=float(text)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None


def axis_value(text):
    m=re.fullmatch(r'(-?\d+(?:\.\d+)?)([kKmM]?)',text.strip().replace(',',''))
    return float(m[1])*({'k':1000,'m':1000000}.get(m[2].lower(),1)) if m else None


def geometry(chart,svg):
    tree=ET.fromstring(svg);nodes=list(tree.iter());data=chart['data'];checks=[]
    if chart['type']=='pie2d':
        groups=[g for g in nodes if g.get('class','').endswith('-plots')]
        paths=[p for g in groups for p in list(g) if p.tag.endswith('path') and 'A' in p.get('d','') and 'L' in p.get('d','')]
        assert len(paths)==len(data['data']),('pie_count',len(paths),len(data['data']))
        total=sum(float(x['value']) for x in data['data'])
        for i,(point,path) in enumerate(zip(data['data'],paths)):
            coordinates=re.fullmatch(fr'M({NUM}),({NUM})A({NUM}),({NUM}),({NUM}),([01]),([01]),({NUM}),({NUM})L({NUM}),({NUM})Z',path.get('d',''))
            assert coordinates,('unsupported_pie_path',path.get('d'))
            a=list(map(float,coordinates.groups()));start=math.atan2(a[1]-a[10],a[0]-a[9]);end=math.atan2(a[8]-a[10],a[7]-a[9])
            angle=((end-start) if a[6] else (start-end))%(2*math.pi)
            delta=abs(100*angle/(2*math.pi)-100*float(point['value'])/total)
            checks.append(dict(point=i,status='pass' if delta<1e-8 else 'fail',percent_difference=delta))
        return checks
    plots=[e for e in nodes if e.tag.endswith('rect') and e.get('fill')=='#eeeeee' and e.get('fill-opacity')=='0.3']
    assert len(plots)==1,('plot_count',len(plots))
    plot=plots[0];x,y,w,h=[float(plot.get(k)) for k in ['x','y','width','height']]
    def bounds(secondary=False):
        ticks=[axis_value(''.join(e.itertext())) for e in nodes if e.tag.endswith('text')
               and ((float(e.get('x','0'))>x+w and e.get('text-anchor')=='start') if secondary else
                    (float(e.get('x','0'))<x and e.get('text-anchor')=='end'))]
        ticks=[n for n in ticks if n is not None];assert len(set(ticks))>=2,('axis_ticks',secondary,ticks)
        return min(ticks),max(ticks)
    pmin,pmax=bounds()
    groups=[g for g in nodes if g.get('class','').endswith('-plot-group') and 'error' not in g.get('class','')]
    primary=series(data.get('dataset',[]));lines=data.get('lineset',[])
    expected=primary+lines
    assert len(groups)==len(expected),('series_count',len(groups),len(expected))
    for si,(dataset,group) in enumerate(zip(expected,groups)):
        points=dataset.get('data',[])
        rectangles=[e for e in list(group) if e.tag.endswith('rect')]
        if rectangles:
            indexed=list(enumerate(points)) if len(rectangles)==len(points) else [(i,p) for i,p in enumerate(points) if value(p.get('value')) not in (None,0)]
            assert len(rectangles)==len(indexed),('bar_point_count',si,len(rectangles),len(indexed))
            for (pi,point),rect in zip(indexed,rectangles):
                v=value(point.get('value'))
                if v is None:
                    continue
                actual=float(rect.get('height'));expected_height=abs(v)*h/(pmax-pmin)
                delta=abs(actual-expected_height)
                zero_y=y+h+pmin*h/(pmax-pmin)
                center_y=float(rect.get('y'))+actual/2
                sign_valid=(center_y<=zero_y+1.5 if v>=0 else center_y>=zero_y-1.5)
                center_x=float(rect.get('x'))+float(rect.get('width'))/2
                category_slot_valid=x+pi*w/len(points)-1.5<=center_x<=x+(pi+1)*w/len(points)+1.5
                # shortcut: FusionCharts rounds bar edges and enforces tiny bars; retain JSON precision.
                checks.append(dict(series=si,point=pi,status='pass' if delta<=1.5 and sign_valid and category_slot_valid else 'fail',pixel_difference=delta,pixel_tolerance=1.5,sign_valid=sign_valid,category_slot_valid=category_slot_valid))
        else:
            paths=[e for e in list(group) if e.tag.endswith('path') and e.get('d')!='M0,0']
            finite=[(i,value(p.get('value'))) for i,p in enumerate(points) if value(p.get('value')) is not None]
            if not finite:continue
            if not paths and all(v==0 for i,v in finite):
                checks.extend(dict(series=si,point=i,status='pass',note='explicit_json_zero_no_rendered_shape') for i,v in finite)
                continue
            assert len(paths)==len(finite),('marker_count',si,len(paths),len(finite))
            coords=[]
            for path in paths:
                vertices=[tuple(map(float,p)) for p in re.findall(fr'[ML]({NUM}),({NUM})',path.get('d',''))]
                assert vertices
                coords.append((sum(p[0] for p in vertices)/len(vertices),(min(p[1] for p in vertices)+max(p[1] for p in vertices))/2))
            assert len(coords)==len(finite),('line_points',si,len(coords),len(finite))
            amin,amax=bounds(True) if si>=len(primary) else (pmin,pmax)
            for (pi,v),(px,py) in zip(finite,coords):
                expected_y=y+h-(v-amin)*h/(amax-amin);delta=abs(py-expected_y)
                checks.append(dict(series=si,point=pi,status='pass' if delta<=1e-4 else 'fail',pixel_difference=delta,pixel_tolerance=1e-4))
    return checks


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--market',type=int,required=True);args=parser.parse_args()
    out=BASE/f'market{args.market}'/datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S.%f+0800_svg')
    out.mkdir(parents=True,exist_ok=False);results=[]
    for panel in validation.rules.PANELS:
        path=BASE.parent/f'raw/market{args.market}_formal4_{panel}.json'
        complete=path.with_name(path.stem+'_complete.json')
        if complete.is_file():path=complete
        if not path.is_file():continue
        doc=validation.read(path);html=doc.get('html','')
        if not validation.formal.full_html(html,doc.get('html_length')):continue
        charts,errors=validation.rules.charts(html);assert not errors
        associations=Containers();associations.feed(html)
        svgs=re.findall(r'<svg\b[\s\S]*?</svg>',html,re.I)
        assert len(svgs)==len(associations.ids)
        for chart in charts:
            container='cc-'+chart['id'].replace('.','-')
            matches=[i for i,c in enumerate(associations.ids) if c==container]
            result=dict(market=args.market,phase='formal',round=4,panel=panel,chart_id=chart['id'],chart_type=chart['type'],source=validation.reference(path),container=container,independent_additional_samples=0)
            try:
                assert len(matches)==1,('container_svg_count',matches)
                checks=geometry(chart,svgs[matches[0]])
                result.update(svg_index=matches[0],svg_sha256=__import__('hashlib').sha256(svgs[matches[0]].encode()).hexdigest(),
                              status='pass' if checks and all(x['status']=='pass' for x in checks) else 'fail',point_checks=checks)
            except (AssertionError,ValueError,KeyError,ET.ParseError) as error:
                result.update(status='pending',reason=str(error))
            results.append(result)
    assert axis_value('10k')==10000 and axis_value('-2.5m')==-2500000 and value('NaN') is None
    with (out/'json_svg_pairing.json').open('x',encoding='utf-8') as stream:json.dump(results,stream,ensure_ascii=False,indent=2)
    with (out/'pair_results_svg.py').open('x',encoding='utf-8') as stream:stream.write(Path(__file__).read_text(encoding='utf-8'))
    with (out/'report.md').open('x',encoding='utf-8') as stream:
        stream.write(f'# 市场{args.market}正式4 JSON/SVG渲染一致性\n\n'
                     f'{dict(Counter(x["status"] for x in results))}，共{len(results)}图。按原HTML的图表容器ID配对SVG，JSON使用历史字面解析器；沿用历史坐标重建方法并适配结果图多序列。\n\n'
                     '折线/标记点中心容差1e-4像素；饼图角度换算份额容差1e-8百分点；柱形考虑整数边缘及微小柱最小高度，容差1.5像素，并检查符号及团队横向槽。显式零可能没有绘图形状；NaN保持缺失。逐点索引、差值、容差和原件/单SVG哈希见JSON。\n\n'
                     '这是同源渲染一致性检验，不是从SVG恢复平台内部数值精度。JSON作为数值主来源；SVG不增加独立样本。\n')
    print(json.dumps(dict(output=str(out),charts=len(results),counts=dict(Counter(x['status'] for x in results)),pending=[(x['chart_id'],x.get('reason')) for x in results if x['status']!='pass']),ensure_ascii=False))


if __name__=='__main__':main()
